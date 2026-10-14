"""Sources complementaires : actualites crypto (flux RSS, score VADER) et Fear & Greed Index.

Seuls le titre, le lien, la source et le score sont conserves : le contenu des articles
n'est pas stocke.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from . import http
from .clients import pg_connect, put_blob
from .config import FEAR_GREED_URL, Settings
from .db import ensure_schema
from .ingest import partition

log = logging.getLogger(__name__)

# Alias sans ambiguite : on evite volontairement "ada", "dot" ou "sol", trop courants.
ALIASES = {
    "bitcoin": ["btc"],
    "ethereum": ["ether", "eth"],
    "ripple": ["xrp"],
    "dogecoin": ["doge"],
}

POSITIVE, NEGATIVE = 0.05, -0.05
_analyzer = None


def build_patterns(coins) -> dict[str, re.Pattern]:
    patterns = {}
    for coin in coins:
        words = [coin.replace("-", " "), *ALIASES.get(coin, [])]
        alternation = "|".join(re.escape(w) for w in words)
        patterns[coin] = re.compile(rf"(?<![a-z0-9])(?:{alternation})(?![a-z0-9])", re.IGNORECASE)
    return patterns


def match_coins(text: str, patterns: dict[str, re.Pattern]) -> list[str]:
    return [coin for coin, pattern in patterns.items() if pattern.search(text)]


def score(text: str) -> float:
    global _analyzer
    if _analyzer is None:
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

        _analyzer = SentimentIntensityAnalyzer()
    return round(_analyzer.polarity_scores(text)["compound"], 4)


def label(compound: float) -> str:
    if compound >= POSITIVE:
        return "positive"
    if compound <= NEGATIVE:
        return "negative"
    return "neutral"


def _parse_date(value: str | None, default: datetime) -> datetime:
    if not value:
        return default
    value = value.strip()
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return default
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _first(fields: dict, *names: str):
    """Premier element present. Attention : un Element sans enfant est evalue comme faux,
    d'ou les tests explicites `is not None` plutot qu'un `or`."""
    for name in names:
        if fields.get(name) is not None:
            return fields[name]
    return None


def parse_feed(xml: bytes, source: str, now: datetime) -> list[dict]:
    """Analyse un flux RSS 2.0 ou Atom. Utilise defusedxml contre les XML malveillants."""
    from defusedxml import ElementTree

    root = ElementTree.fromstring(xml)
    items = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        fields = {_local(child.tag): child for child in node}
        title = (fields["title"].text or "").strip() if "title" in fields else ""
        link = ""
        if "link" in fields:
            link = (fields["link"].text or fields["link"].attrib.get("href", "")).strip()
        summary_node = _first(fields, "description", "summary")
        summary = re.sub(r"<[^>]+>", " ", summary_node.text or "") if summary_node is not None else ""
        published = _first(fields, "pubDate", "published", "updated")
        if title and link:
            items.append({
                "source": source,
                "title": title,
                "link": link,
                "summary": summary.strip(),
                "published_at": _parse_date(published.text if published is not None else None, now),
            })
    return items


def source_name(url: str) -> str:
    match = re.search(r"https?://(?:www\.)?([^/]+)", url)
    return match.group(1) if match else url


def collect(settings: Settings, now: datetime, fetch=lambda url: http.get(url, timeout=20).content) -> list[dict]:
    """Recupere les flux, associe chaque article aux cryptos suivies et calcule le sentiment."""
    patterns = build_patterns(settings.coins)
    oldest = now - timedelta(days=settings.news_max_age_days)
    rows, failures = [], 0

    for url in settings.news_feeds:
        try:
            items = parse_feed(fetch(url), source_name(url), now)
        except Exception:  # un flux en panne ne doit pas bloquer les autres
            log.exception("Flux inaccessible : %s", url)
            failures += 1
            continue
        for item in items:
            if item["published_at"] < oldest:
                continue
            text = f"{item['title']}. {item['summary']}"
            coins = match_coins(text, patterns)
            if not coins:
                continue
            compound = score(text)
            for coin in coins:
                rows.append({
                    "link": item["link"], "coin_id": coin, "source": item["source"],
                    "title": item["title"][:300], "published_at": item["published_at"],
                    "sentiment": compound, "label": label(compound),
                })
    if failures == len(settings.news_feeds):
        raise RuntimeError("Aucun flux d'actualites n'est accessible")
    return rows


def run_news(ts: datetime, settings: Settings, fetch=None) -> int:
    kwargs = {"fetch": fetch} if fetch else {}
    rows = collect(settings, ts, **kwargs)
    payload = [{**r, "published_at": r["published_at"].isoformat()} for r in rows]
    path = f"{partition('news/rss', ts)}/news_{ts:%Y%m%dT%H0000Z}.json"
    put_blob(settings, settings.bronze_container, path, json.dumps(payload).encode("utf-8"))

    from psycopg2.extras import execute_values

    values = [(r["link"], r["coin_id"], r["published_at"], r["source"], r["title"], r["sentiment"], r["label"])
              for r in rows]
    inserted = 0
    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        if values:
            execute_values(
                cur,
                "INSERT INTO raw.news_sentiment (link, coin_id, published_at, source, title, sentiment, label) "
                "VALUES %s ON CONFLICT (link, coin_id) DO NOTHING",
                values,
            )
            inserted = cur.rowcount
    log.info("Actualites : %d nouveaux articles (%d associations)", inserted, len(rows))
    return inserted


def parse_fear_greed(payload: dict) -> list[tuple]:
    rows = []
    for entry in payload.get("data", []):
        day = datetime.fromtimestamp(int(entry["timestamp"]), tz=UTC).date()
        value = int(entry["value"])
        if not 0 <= value <= 100:
            raise ValueError(f"Valeur Fear & Greed hors bornes : {value}")
        rows.append((day, value, entry["value_classification"]))
    if not rows:
        raise ValueError("Reponse Fear & Greed vide")
    return rows


def run_fear_greed(ts: datetime, settings: Settings, limit: int = 30, fetch=None) -> int:
    fetch = fetch or (lambda: http.get(FEAR_GREED_URL, params={"limit": limit, "format": "json"}).json())
    payload = fetch()
    rows = parse_fear_greed(payload)
    path = f"{partition('fear_greed', ts)}/fng_{ts:%Y%m%dT%H0000Z}.json"
    put_blob(settings, settings.bronze_container, path, json.dumps(payload).encode("utf-8"))

    from psycopg2.extras import execute_values

    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        execute_values(
            cur,
            "INSERT INTO raw.fear_greed (fng_date, value, classification) VALUES %s "
            "ON CONFLICT (fng_date) DO UPDATE SET value = EXCLUDED.value, "
            "classification = EXCLUDED.classification, loaded_at = now()",
            rows,
        )
    log.info("Fear & Greed : %d jours charges", len(rows))
    return len(rows)
