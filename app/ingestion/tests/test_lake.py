import io
from datetime import UTC, date, datetime
from decimal import Decimal

import pyarrow.parquet as pq
from cryptopulse_ingestion import lake


def test_paths_are_partitioned():
    assert lake.silver_path(date(2026, 10, 9)) == "prices/year=2026/month=10/day=09/prices.parquet"
    assert lake.gold_path("fct_daily_prices", date(2026, 10, 9)) == (
        "marts/fct_daily_prices/snapshot=2026-10-09/fct_daily_prices.parquet"
    )


def test_parquet_roundtrip_converts_decimals():
    ts = datetime(2026, 10, 9, 12, tzinfo=UTC)
    rows = [("bitcoin", Decimal("60000.5"), ts, None), ("ethereum", Decimal("3000"), ts, 1.5)]
    data = lake.rows_to_parquet(["coin_id", "price", "ts", "pct"], rows)
    table = pq.read_table(io.BytesIO(data))
    assert table.num_rows == 2
    assert table.column("price").to_pylist() == [60000.5, 3000.0]
    assert str(table.schema.field("price").type) == "double"
    assert table.column("pct").to_pylist() == [None, 1.5]
    assert table.column("ts").to_pylist()[0] == ts
