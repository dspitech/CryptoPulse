from datetime import UTC, datetime, timedelta

from cryptopulse_ingestion import backfill

BASE = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)


def ms(dt):
    return int(dt.timestamp() * 1000)


def chart(points):
    return {
        "prices": [[ms(t), p] for t, p in points],
        "market_caps": [[ms(t), p * 1000] for t, p in points],
        "total_volumes": [[ms(t), p * 10] for t, p in points],
    }


def test_points_are_aligned_on_the_hour_and_deduplicated():
    pts = [(BASE + timedelta(minutes=5), 100.0), (BASE + timedelta(minutes=50), 101.0),
           (BASE + timedelta(hours=1, minutes=3), 102.0)]
    rows = backfill.chart_to_rows("bitcoin", chart(pts), "f.json", BASE + timedelta(days=1))
    assert [r[3] for r in rows] == ["2026-10-01T00:00:00+00:00", "2026-10-01T01:00:00+00:00"]
    assert rows[0][4] == 101.0  # le dernier point de l'heure est conserve


def test_current_and_future_hours_are_excluded():
    cutoff = BASE + timedelta(hours=2)
    pts = [(BASE + timedelta(hours=h), 100.0 + h) for h in range(5)]
    rows = backfill.chart_to_rows("bitcoin", chart(pts), "f.json", cutoff)
    assert len(rows) == 2  # heures 0 et 1 uniquement


def test_invalid_prices_are_dropped_and_metadata_left_null():
    pts = [(BASE, 0.0), (BASE + timedelta(hours=1), -5.0), (BASE + timedelta(hours=2), 50.0)]
    rows = backfill.chart_to_rows("ethereum", chart(pts), "f.json", BASE + timedelta(days=1))
    assert len(rows) == 1
    coin, symbol, name, _, price, cap, vol, high, low, pct, source = rows[0]
    assert (coin, symbol, name, price, cap, vol) == ("ethereum", None, None, 50.0, 50000.0, 500.0)
    assert high is low is pct is None and source == "f.json"
    assert len(rows[0]) == 11  # meme forme que load.INSERT
