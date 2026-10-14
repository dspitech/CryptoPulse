"""Etape 3 : chargement idempotent du bronze vers raw.prices (PostgreSQL)."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from .clients import get_blob, pg_connect
from .config import Settings
from .db import ensure_schema
from .ingest import build_blob_path

log = logging.getLogger(__name__)

INSERT = """
INSERT INTO raw.prices (
    coin_id, symbol, name, snapshot_ts, price_usd, market_cap_usd,
    volume_24h_usd, high_24h_usd, low_24h_usd, pct_change_24h, source_file
) VALUES %s
ON CONFLICT (coin_id, snapshot_ts) DO NOTHING
"""


def records_to_rows(payload: dict, source_file: str) -> list[tuple]:
    snapshot_ts = payload["snapshot_ts"]
    return [
        (
            r["id"],
            r.get("symbol"),
            r.get("name"),
            snapshot_ts,
            r.get("current_price"),
            r.get("market_cap"),
            r.get("total_volume"),
            r.get("high_24h"),
            r.get("low_24h"),
            r.get("price_change_percentage_24h"),
            source_file,
        )
        for r in payload["records"]
    ]


def insert_rows(cur, rows: list[tuple]) -> int:
    """Insere des lignes dans raw.prices sans jamais ecraser l'existant."""
    from psycopg2.extras import execute_values

    if not rows:
        return 0
    execute_values(cur, INSERT, rows)
    return cur.rowcount


def run(ts: datetime, settings: Settings) -> int:
    path = build_blob_path(ts)
    payload = json.loads(get_blob(settings, settings.bronze_container, path))
    rows = records_to_rows(payload, path)

    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        inserted = insert_rows(cur, rows)
    log.info("Charge %d nouvelles lignes sur %d (%s)", inserted, len(rows), path)
    return inserted
