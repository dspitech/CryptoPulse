"""API de donnees CryptoPulse : lecture seule sur les marts dbt, authentification par cle."""
from __future__ import annotations

import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import Annotated

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.pool
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Path, Query, Request, Security
from fastapi.security import APIKeyHeader
from prometheus_client import Counter, Histogram, start_http_server

COIN_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{0,63}$")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

REQUESTS = Counter("cryptopulse_api_requests_total", "Requetes HTTP", ["method", "path", "status"])
LATENCY = Histogram("cryptopulse_api_request_duration_seconds", "Duree des requetes", ["path"])

_pool: psycopg2.pool.ThreadedConnectionPool | None = None


# --------------------------------------------------------------------------- base de donnees
def get_pool() -> psycopg2.pool.ThreadedConnectionPool:
    global _pool
    if _pool is None:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            1, 5,
            host=os.environ.get("POSTGRES_HOST", "postgres"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            dbname=os.environ.get("POSTGRES_DB", "cryptopulse"),
            user=os.environ.get("POSTGRES_USER", "api_ro"),
            password=os.environ["POSTGRES_PASSWORD"],
            connect_timeout=5,
        )
    return _pool


def normalize(row: dict) -> dict:
    """Les NUMERIC PostgreSQL arrivent en Decimal, que Pydantic v2 serialise en texte : on veut des nombres JSON."""
    return {key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()}


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Execute une requete en lecture seule et retourne les lignes sous forme de dictionnaires."""
    pool = get_pool()
    conn = pool.getconn()
    broken = False
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [normalize(dict(r)) for r in cur.fetchall()]
        conn.rollback()
        return rows
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.InsufficientPrivilege) as exc:
        conn.rollback()
        raise HTTPException(status_code=503, detail="Donnees pas encore disponibles") from exc
    except psycopg2.OperationalError as exc:
        broken = True
        raise HTTPException(status_code=503, detail="Base de donnees indisponible") from exc
    finally:
        pool.putconn(conn, close=broken)


# --------------------------------------------------------------------------- securite
def require_api_key(key: Annotated[str | None, Security(api_key_header)]) -> None:
    expected = os.environ.get("API_KEY", "")
    if not expected:
        raise HTTPException(status_code=503, detail="API non configuree")
    if not key or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(
            status_code=401, detail="Cle d'API invalide ou manquante",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def coin_param(coin_id: Annotated[str, Path(description="Identifiant CoinGecko, par exemple bitcoin")]) -> str:
    if not COIN_RE.match(coin_id):
        raise HTTPException(status_code=422, detail="coin_id invalide")
    return coin_id


Coin = Annotated[str, Depends(coin_param)]
Limit = Annotated[int, Query(ge=1, le=1000, description="Nombre maximal de lignes")]

# --------------------------------------------------------------------------- application
_metrics_started = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _metrics_started
    if len(os.environ.get("API_KEY", "")) < 16:
        raise RuntimeError("API_KEY doit etre definie (16 caracteres minimum)")
    port = int(os.environ.get("API_METRICS_PORT", "9000"))
    if port > 0 and not _metrics_started:  # serveur de metriques separe, non expose publiquement
        start_http_server(port)
        _metrics_started = True
    yield


app = FastAPI(
    title="CryptoPulse API",
    version="1.0.0",
    description=(
        "Acces en lecture seule aux donnees analytiques CryptoPulse (prix, indicateurs, anomalies, "
        "previsions, sentiment). Les previsions sont une illustration statistique, pas un conseil financier."
    ),
    lifespan=lifespan,
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "non_routee")
        REQUESTS.labels(request.method, path, str(status)).inc()
        LATENCY.labels(path).observe(time.perf_counter() - started)


@app.get("/health", tags=["service"])
def health() -> dict:
    try:
        query("SELECT 1 AS ok")
        return {"status": "ok", "database": "up"}
    except HTTPException:
        return {"status": "degraded", "database": "down"}


v1 = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


@v1.get("/coins", tags=["referentiel"], summary="Cryptomonnaies suivies")
def coins() -> list[dict]:
    return query("SELECT coin_id, symbol, name, first_seen_at, last_seen_at FROM marts.dim_coins ORDER BY coin_id")


@v1.get("/prices/latest", tags=["prix"], summary="Dernier prix de chaque crypto")
def latest_prices() -> list[dict]:
    return query("SELECT * FROM marts.fct_latest_prices ORDER BY coin_id")


@v1.get("/prices/{coin_id}/latest", tags=["prix"], summary="Dernier prix d'une crypto")
def latest_price(coin_id: Coin) -> dict:
    rows = query("SELECT * FROM marts.fct_latest_prices WHERE coin_id = %s", (coin_id,))
    if not rows:
        raise HTTPException(status_code=404, detail="Crypto inconnue")
    return rows[0]


@v1.get("/prices/{coin_id}/daily", tags=["prix"], summary="Prix OHLC journaliers")
def daily_prices(
    coin_id: Coin,
    limit: Limit = 90,
    start: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date minimale (AAAA-MM-JJ)")] = None,
    end: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$", description="Date maximale (AAAA-MM-JJ)")] = None,
) -> list[dict]:
    return query(
        "SELECT price_date, open_usd, high_usd, low_usd, close_usd, avg_usd, snapshots, "
        "market_cap_usd, volume_24h_usd FROM marts.fct_daily_prices "
        "WHERE coin_id = %s AND (%s::date IS NULL OR price_date >= %s::date) "
        "AND (%s::date IS NULL OR price_date <= %s::date) ORDER BY price_date DESC LIMIT %s",
        (coin_id, start, start, end, end, limit),
    )


@v1.get("/indicators/{coin_id}", tags=["analytique"], summary="Moyennes mobiles, variation et volatilite")
def indicators(coin_id: Coin, limit: Limit = 90) -> list[dict]:
    return query(
        "SELECT price_date, close_usd, ma_7d, ma_30d, pct_change_1d, volatility_7d "
        "FROM marts.fct_price_indicators WHERE coin_id = %s ORDER BY price_date DESC LIMIT %s",
        (coin_id, limit),
    )


@v1.get("/anomalies", tags=["analytique"], summary="Anomalies de prix detectees")
def anomalies(
    coin_id: Annotated[str | None, Query(pattern=COIN_RE.pattern)] = None,
    hours: Annotated[int, Query(ge=1, le=24 * 90, description="Fenetre en heures")] = 168,
    limit: Limit = 100,
) -> list[dict]:
    return query(
        "SELECT coin_id, snapshot_ts, price_usd, return_pct, z_score, direction "
        "FROM marts.fct_price_anomalies WHERE is_anomaly "
        "AND snapshot_ts >= now() - make_interval(hours => %s) "
        "AND (%s::text IS NULL OR coin_id = %s) ORDER BY snapshot_ts DESC LIMIT %s",
        (hours, coin_id, coin_id, limit),
    )


@v1.get("/forecasts/{coin_id}", tags=["analytique"], summary="Prevision a court terme (intervalle a 80 %)")
def forecasts(coin_id: Coin) -> list[dict]:
    return query(
        "SELECT forecast_date, horizon_day, yhat, yhat_lower, yhat_upper, model, training_points, generated_on "
        "FROM marts.fct_forecasts_latest WHERE coin_id = %s AND forecast_date >= current_date - 1 "
        "ORDER BY forecast_date",
        (coin_id,),
    )


@v1.get("/sentiment/{coin_id}", tags=["sentiment"], summary="Sentiment quotidien des actualites")
def sentiment(coin_id: Coin, limit: Limit = 30) -> list[dict]:
    return query(
        "SELECT published_date, articles, avg_sentiment, positive_articles, negative_articles, neutral_articles "
        "FROM marts.fct_daily_sentiment WHERE coin_id = %s ORDER BY published_date DESC LIMIT %s",
        (coin_id, limit),
    )


@v1.get("/fear-greed", tags=["sentiment"], summary="Fear & Greed Index")
def fear_greed(limit: Limit = 30) -> list[dict]:
    return query(
        "SELECT fng_date, value, classification, value_ma7, change_1d "
        "FROM marts.fct_fear_greed ORDER BY fng_date DESC LIMIT %s",
        (limit,),
    )


@v1.get("/quality/latest", tags=["qualite"], summary="Derniers controles qualite du pipeline")
def quality_latest() -> list[dict]:
    return query(
        "SELECT run_id, run_at, check_name, metric, status, details FROM ops.quality_runs "
        "WHERE run_id = (SELECT run_id FROM ops.quality_runs WHERE check_name <> 'freshness' "
        "ORDER BY run_at DESC LIMIT 1) ORDER BY check_name"
    )


app.include_router(v1)
