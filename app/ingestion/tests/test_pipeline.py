from datetime import UTC, datetime

import pytest
from cryptopulse_ingestion import ingest, load, quality, validate


def test_build_blob_path_is_partitioned_and_hourly():
    ts = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)
    assert ingest.build_blob_path(ts) == (
        "coingecko/markets/year=2026/month=10/day=09/markets_20261009T140000Z.json"
    )


def test_records_to_rows_maps_fields():
    payload = {
        "snapshot_ts": "2026-10-09T14:00:00+00:00",
        "records": [
            {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 60000, "market_cap": 1}
        ],
    }
    rows = load.records_to_rows(payload, "file.json")
    assert rows[0][0] == "bitcoin"
    assert rows[0][4] == 60000
    assert rows[0][-1] == "file.json"


def test_validate_payload_accepts_valid():
    payload = {"records": [{"id": "btc", "symbol": "btc", "current_price": 10}]}
    assert validate.validate_payload(payload) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"records": []},
        {"records": [{"id": "btc", "symbol": "btc"}]},
        {"records": [{"id": "btc", "symbol": "btc", "current_price": 0}]},
    ],
)
def test_validate_payload_rejects_invalid(payload):
    with pytest.raises(ValueError):
        validate.validate_payload(payload)


def test_quality_statuses():
    ok = quality.evaluate(10, 0, 5, 5)
    assert quality.overall_status(ok) == "OK"
    warn = quality.evaluate(10, 0, 4, 5)
    assert quality.overall_status(warn) == "WARNING"
    fail = quality.evaluate(0, 0, 0, 5)
    assert quality.overall_status(fail) == "FAIL"


def test_report_mentions_every_check():
    report = quality.render_report("abc", quality.evaluate(1, 0, 1, 1), datetime(2026, 1, 1, tzinfo=UTC))
    assert "Statut global : OK" in report
    for name in ("row_count", "invalid_prices", "coin_coverage"):
        assert name in report
