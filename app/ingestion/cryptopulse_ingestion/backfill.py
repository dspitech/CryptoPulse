"""Backfill de l'historique de prix (endpoint market_chart de CoinGecko).

Pour days entre 2 et 90 l'API fournit des points horaires ; au-dela de 90 jours elle
fournit des points quotidiens. Les lignes sont inserees avec ON CONFLICT DO NOTHING : un
snapshot reel existant n'est jamais ecrase.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime

from . import http
from .clients import pg_connect, put_blob
from .config import CHART_URL, VS_CURRENCY, Settings
from .db import ensure_schema
from .ingest import partition
from .load import insert_rows

log = logging.getLogger(__name__)

MAX_DAYS = 365


def _hour(ts_ms: float) -> datetime:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).replace(minute=0, second=0, microsecond=0)


def chart_to_rows(coin_id: str, chart: dict, source_file: str, cutoff: datetime) -> list[tuple]:
    """Convertit une reponse market_chart en lignes pour raw.prices.

    - un seul point par heure (le dernier), aligne sur l'heure pleine ;
    - les heures posterieures ou egales a cutoff sont ignorees, car elles sont couvertes
      par les snapshots reels.
    """
    caps = {_hour(ts): v for ts, v in chart.get("market_caps") or []}
    vols = {_hour(ts): v for ts, v in chart.get("total_volumes") or []}

    by_hour: dict[datetime, float] = {}
    for ts, price in chart.get("prices") or []:
        hour = _hour(ts)
        if hour < cutoff and price is not None and price > 0:
            by_hour[hour] = price

    return [
        (coin_id, None, None, hour.isoformat(), price, caps.get(hour), vols.get(hour),
         None, None, None, source_file)
        for hour, price in sorted(by_hour.items())
    ]


def fetch_chart(coin_id: str, days: int) -> dict:
    response = http.get(
        CHART_URL.format(coin=coin_id),
        params={"vs_currency": VS_CURRENCY, "days": days},
    )
    chart = response.json()
    if not isinstance(chart, dict) or not chart.get("prices"):
        raise ValueError(f"Historique vide pour {coin_id}")
    return chart


def run(settings: Settings, days: int, now: datetime | None = None, fetch=fetch_chart) -> int:
    days = max(2, min(int(days), MAX_DAYS))
    now = now or datetime.now(UTC)
    cutoff = now.replace(minute=0, second=0, microsecond=0)
    total = 0

    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        for index, coin in enumerate(settings.coins):
            if index and settings.backfill_pause_seconds:
                time.sleep(settings.backfill_pause_seconds)  # respecte la limite de debit de l'API
            chart = fetch(coin, days)
            path = f"{partition('coingecko/market_chart', now)}/{coin}_{days}d_{now:%Y%m%dT%H%M%SZ}.json"
            put_blob(settings, settings.bronze_container, path, json.dumps(chart).encode("utf-8"))
            rows = chart_to_rows(coin, chart, path, cutoff)
            inserted = insert_rows(cur, rows)
            conn.commit()
            log.info("Backfill %s : %d lignes inserees sur %d (%d jours)", coin, inserted, len(rows), days)
            total += inserted
    return total
