"""Previsions de prix a court terme (ARIMA sur le logarithme des cloture journalieres).

Il s'agit d'une illustration statistique et non d'un conseil financier : les cours des
cryptomonnaies sont tres peu previsibles, les intervalles a 80 % le montrent.
"""
from __future__ import annotations

import logging
import math
import warnings
from datetime import date, timedelta

from .clients import pg_connect
from .config import Settings
from .db import ensure_schema

log = logging.getLogger(__name__)

Z80 = 1.2816  # quantile de la loi normale pour un intervalle a 80 %


class NotReadyError(RuntimeError):
    """Les tables dbt necessaires n'existent pas encore."""


def forecast_series(closes: list[float], last_date: date, horizon: int, min_points: int) -> list[dict] | None:
    """Retourne les previsions sur `horizon` jours, ou None si l'historique est insuffisant."""
    if len(closes) < min_points or any(c <= 0 for c in closes):
        return None

    import numpy as np

    y = np.log(np.asarray(closes, dtype=float))
    model = "arima_1_1_1"
    try:
        from statsmodels.tsa.arima.model import ARIMA

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = ARIMA(y, order=(1, 1, 1)).fit()
            fc = result.get_forecast(steps=horizon)
            mean = np.asarray(fc.predicted_mean, dtype=float)
            conf = np.asarray(fc.conf_int(alpha=0.2), dtype=float)
            lower, upper = conf[:, 0], conf[:, 1]
        if not np.all(np.isfinite(mean)) or not np.all(np.isfinite(conf)):
            raise ValueError("prevision non finie")
    except Exception:  # repli sur une marche aleatoire si l'ajustement echoue
        log.warning("Ajustement ARIMA impossible, repli sur une marche aleatoire", exc_info=True)
        model = "naive_random_walk"
        sigma = float(np.std(np.diff(y), ddof=1)) or 1e-6
        steps = np.arange(1, horizon + 1)
        mean = np.full(horizon, y[-1])
        lower = mean - Z80 * sigma * np.sqrt(steps)
        upper = mean + Z80 * sigma * np.sqrt(steps)

    return [
        {
            "forecast_date": last_date + timedelta(days=h + 1),
            "horizon_day": h + 1,
            "yhat": math.exp(mean[h]),
            "yhat_lower": math.exp(lower[h]),
            "yhat_upper": math.exp(upper[h]),
            "model": model,
            "training_points": len(closes),
        }
        for h in range(horizon)
    ]


def run(settings: Settings, today: date) -> int:
    from psycopg2 import errors
    from psycopg2.extras import execute_values

    total = 0
    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        conn.commit()
        for coin in settings.coins:
            try:
                cur.execute(
                    "SELECT price_date, close_usd::float8 FROM marts.fct_daily_prices "
                    "WHERE coin_id = %s AND price_date < %s ORDER BY price_date",
                    (coin, today),
                )
            except errors.UndefinedTable as exc:
                raise NotReadyError("marts.fct_daily_prices n'existe pas encore") from exc
            rows = cur.fetchall()
            if not rows:
                log.info("Prevision %s ignoree : aucune donnee", coin)
                continue
            result = forecast_series(
                [r[1] for r in rows], rows[-1][0], settings.forecast_horizon_days, settings.forecast_min_points
            )
            if result is None:
                log.info("Prevision %s ignoree : %d points (minimum %d)", coin, len(rows),
                         settings.forecast_min_points)
                continue
            execute_values(
                cur,
                "INSERT INTO ops.forecast_history (coin_id, forecast_date, generated_on, horizon_day, "
                "yhat, yhat_lower, yhat_upper, model, training_points) VALUES %s "
                "ON CONFLICT (coin_id, forecast_date, generated_on) DO UPDATE SET "
                "horizon_day = EXCLUDED.horizon_day, yhat = EXCLUDED.yhat, "
                "yhat_lower = EXCLUDED.yhat_lower, yhat_upper = EXCLUDED.yhat_upper, "
                "model = EXCLUDED.model, training_points = EXCLUDED.training_points, generated_at = now()",
                [(coin, r["forecast_date"], today, r["horizon_day"], r["yhat"], r["yhat_lower"],
                  r["yhat_upper"], r["model"], r["training_points"]) for r in result],
            )
            conn.commit()
            total += len(result)
            log.info("Prevision %s : %d jours (%s)", coin, len(result), result[0]["model"])
    return total
