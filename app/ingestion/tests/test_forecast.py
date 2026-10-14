from datetime import date, timedelta

import numpy as np
import pytest
from cryptopulse_ingestion import forecast

LAST = date(2026, 10, 8)


def random_walk(n, seed=1):
    rng = np.random.default_rng(seed)
    return list(100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, n))))


def test_forecast_shape_dates_and_bounds():
    result = forecast.forecast_series(random_walk(60), LAST, 7, 21)
    assert len(result) == 7
    assert [r["forecast_date"] for r in result] == [LAST + timedelta(days=i) for i in range(1, 8)]
    assert [r["horizon_day"] for r in result] == list(range(1, 8))
    for r in result:
        assert r["yhat_lower"] < r["yhat"] < r["yhat_upper"]
        assert r["training_points"] == 60 and r["model"] == "arima_1_1_1"


def test_uncertainty_grows_with_horizon():
    result = forecast.forecast_series(random_walk(90), LAST, 7, 21)
    width = [r["yhat_upper"] - r["yhat_lower"] for r in result]
    assert width[-1] > width[0]


def test_insufficient_or_invalid_history_returns_none():
    assert forecast.forecast_series(random_walk(10), LAST, 7, 21) is None
    assert forecast.forecast_series([100.0] * 29 + [-1.0], LAST, 7, 21) is None


def test_fallback_to_random_walk_when_arima_fails(monkeypatch):
    import statsmodels.tsa.arima.model as arima

    class Broken:
        def __init__(self, *a, **k):
            raise ValueError("boom")

    monkeypatch.setattr(arima, "ARIMA", Broken)
    result = forecast.forecast_series(random_walk(40), LAST, 5, 21)
    assert len(result) == 5 and result[0]["model"] == "naive_random_walk"
    assert result[0]["yhat"] == pytest.approx(result[-1]["yhat"])
    assert result[-1]["yhat_upper"] - result[-1]["yhat_lower"] > result[0]["yhat_upper"] - result[0]["yhat_lower"]
