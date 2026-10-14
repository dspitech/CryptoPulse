"""Export Parquet vers le Data Lake : couche silver (prix nettoyes) et gold (marts dbt)."""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

from .clients import pg_connect, put_blob
from .config import Settings

log = logging.getLogger(__name__)

SILVER_QUERY = """
SELECT coin_id, symbol, name, snapshot_ts,
       price_usd::float8 AS price_usd, market_cap_usd::float8 AS market_cap_usd,
       volume_24h_usd::float8 AS volume_24h_usd, high_24h_usd::float8 AS high_24h_usd,
       low_24h_usd::float8 AS low_24h_usd, pct_change_24h::float8 AS pct_change_24h
FROM staging.stg_prices
WHERE price_date = %s
ORDER BY coin_id, snapshot_ts
"""

GOLD_TABLES = (
    "dim_coins",
    "fct_latest_prices",
    "fct_daily_prices",
    "fct_price_indicators",
    "fct_price_anomalies",
)


def silver_path(day: date) -> str:
    return f"prices/year={day:%Y}/month={day:%m}/day={day:%d}/prices.parquet"


def gold_path(table: str, day: date) -> str:
    return f"marts/{table}/snapshot={day:%Y-%m-%d}/{table}.parquet"


def rows_to_parquet(columns: list[str], rows: list[tuple]) -> bytes:
    """Serialise des lignes en Parquet (snappy). Les Decimal sont convertis en float."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    data = {
        name: [float(v) if isinstance(v, Decimal) else v for v in (row[i] for row in rows)]
        for i, name in enumerate(columns)
    }
    table = pa.table(data)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="snappy")
    return sink.getvalue().to_pybytes()


def _fetch(cur, query: str, params: tuple = ()) -> tuple[list[str], list[tuple]]:
    cur.execute(query, params)
    return [d[0] for d in cur.description], cur.fetchall()


def export_silver(day: date, settings: Settings) -> int:
    with pg_connect(settings) as conn, conn.cursor() as cur:
        columns, rows = _fetch(cur, SILVER_QUERY, (day,))
    if not rows:
        log.info("Silver : aucune ligne pour %s", day)
        return 0
    put_blob(settings, settings.silver_container, silver_path(day), rows_to_parquet(columns, rows))
    log.info("Silver : %d lignes ecrites pour %s", len(rows), day)
    return len(rows)


def export_gold(day: date, settings: Settings) -> dict[str, int]:
    counts: dict[str, int] = {}
    with pg_connect(settings) as conn, conn.cursor() as cur:
        for table in GOLD_TABLES:
            columns, rows = _fetch(cur, f"SELECT * FROM marts.{table}")  # noqa: S608 (liste fermee)
            if rows:
                put_blob(settings, settings.gold_container, gold_path(table, day),
                         rows_to_parquet(columns, rows))
            counts[table] = len(rows)
    log.info("Gold : %s", counts)
    return counts


def run(ts: datetime, settings: Settings) -> dict:
    day = ts.date()
    return {"silver": export_silver(day, settings), "gold": export_gold(day, settings)}
