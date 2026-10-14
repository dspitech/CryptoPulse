"""Etape 1 : appel de l'API CoinGecko et depot du JSON brut dans la zone bronze."""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from . import http
from .clients import put_blob
from .config import API_URL, VS_CURRENCY, Settings

log = logging.getLogger(__name__)


def partition(prefix: str, ts: datetime) -> str:
    return f"{prefix}/year={ts:%Y}/month={ts:%m}/day={ts:%d}"


def build_blob_path(ts: datetime) -> str:
    """Chemin partitionne year/month/day, identique pour une meme heure (idempotence)."""
    return f"{partition('coingecko/markets', ts)}/markets_{ts:%Y%m%dT%H0000Z}.json"


def fetch_markets(settings: Settings) -> list[dict]:
    response = http.get(
        API_URL,
        params={"vs_currency": VS_CURRENCY, "ids": ",".join(settings.coins)},
    )
    records = response.json()
    if not isinstance(records, list) or not records:
        raise ValueError("Reponse CoinGecko vide ou inattendue")
    return records


def build_payload(ts: datetime, records: list[dict]) -> dict:
    return {
        "source": "coingecko",
        "snapshot_ts": ts.isoformat(),
        "fetched_at": datetime.now(UTC).isoformat(),
        "vs_currency": VS_CURRENCY,
        "records": records,
    }


def run(ts: datetime, settings: Settings) -> str:
    records = fetch_markets(settings)
    payload = build_payload(ts, records)
    path = build_blob_path(ts)
    put_blob(settings, settings.bronze_container, path, json.dumps(payload).encode("utf-8"))
    log.info("Depot bronze : %s (%d enregistrements)", path, len(records))
    return path
