"""Test d'integration de bout en bout (PostgreSQL + Azurite + dbt reels).

Execution : CRYPTOPULSE_E2E=1 pytest -m e2e   (voir `make e2e` et la CI)
Variables : POSTGRES_HOST/USER/PASSWORD/DB, AZURE_STORAGE_CONNECTION_STRING (Azurite), DBT_BIN.
Les tests sont ordonnes : chaque etape s'appuie sur la precedente.
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import subprocess
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(os.environ.get("CRYPTOPULSE_E2E") != "1", reason="CRYPTOPULSE_E2E=1 requis"),
]

ROOT = Path(__file__).resolve().parents[4]
APP = ROOT / "app"
DBT_DIR = APP / "dbt"
DASHBOARDS = APP / "monitoring" / "grafana" / "dashboards"
QUERIES = APP / "monitoring" / "postgres-exporter" / "queries.yaml"
ROLES_SQL = APP / "deploy" / "sql" / "roles.sql"

PW_MONITORING, PW_API = "monitoring-pw-test", "api-pw-test"
COINS = ("bitcoin", "ethereum")
SPIKE_HOUR = 800

NOW_HOUR = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)


def pg_env():
    return {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "cryptopulse"),
    }


def connect(user=None, password=None):
    import psycopg2

    return psycopg2.connect(
        user=user or os.environ.get("POSTGRES_USER", "cryptopulse"),
        password=password or os.environ["POSTGRES_PASSWORD"],
        **pg_env(),
    )


def psql_env():
    return {**os.environ, "PGPASSWORD": os.environ["POSTGRES_PASSWORD"], "PGHOST": pg_env()["host"],
            "PGPORT": str(pg_env()["port"]), "PGUSER": os.environ.get("POSTGRES_USER", "cryptopulse"),
            "PGDATABASE": pg_env()["dbname"]}


def run_dbt(*args):
    env = {**os.environ, "DBT_TARGET_PATH": "/tmp/cp-dbt-target", "DBT_LOG_PATH": "/tmp/cp-dbt-logs"}
    cmd = [os.environ.get("DBT_BIN", "dbt"), *args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600)
    assert result.returncode == 0, f"dbt a echoue :\n{result.stdout[-3000:]}\n{result.stderr[-1000:]}"
    return result.stdout


def scalar(sql, *params, user=None, password=None):
    with connect(user, password) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def settings():
    os.environ.setdefault("COINS", ",".join(COINS))
    os.environ["BACKFILL_PAUSE_SECONDS"] = "0"
    os.environ["FORECAST_MIN_POINTS"] = "21"
    from cryptopulse_ingestion.config import get_settings

    return get_settings()


@pytest.fixture(scope="module", autouse=True)
def clean_environment(settings):
    from cryptopulse_ingestion.clients import blob_service

    with connect() as conn, conn.cursor() as cur:
        for schema in ("raw", "ops", "staging", "marts"):
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
    service = blob_service(settings)
    for container in (settings.bronze_container, settings.silver_container, settings.gold_container):
        try:
            service.delete_container(container)
        except Exception:
            pass
    yield


def fake_markets(factor=1.0):
    return [
        {"id": "bitcoin", "symbol": "btc", "name": "Bitcoin", "current_price": 60000 * factor,
         "market_cap": 1.2e12, "total_volume": 3.0e10, "high_24h": 61000, "low_24h": 59000,
         "price_change_percentage_24h": 1.5},
        {"id": "ethereum", "symbol": "eth", "name": "Ethereum", "current_price": 3000 * factor,
         "market_cap": 3.6e11, "total_volume": 1.5e10, "high_24h": 3100, "low_24h": 2900,
         "price_change_percentage_24h": -0.8},
    ]


# --------------------------------------------------------------------------- 1. schema et roles
def test_01_schema_and_roles(settings):
    from cryptopulse_ingestion.db import ensure_schema

    with connect() as conn, conn.cursor() as cur:
        ensure_schema(cur)
        ensure_schema(cur)  # idempotent

    for _ in range(2):  # le script de roles est rejouable a chaque deploiement
        subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-v", f"pw_monitoring={PW_MONITORING}", "-v", f"pw_api={PW_API}",
             "-f", str(ROLES_SQL)],
            check=True, capture_output=True, env=psql_env(),
        )
    assert scalar("SELECT 1", user="monitoring_ro", password=PW_MONITORING) == 1
    assert scalar("SELECT 1", user="api_ro", password=PW_API) == 1


def test_02_roles_are_read_only():
    import psycopg2

    with pytest.raises(psycopg2.Error):
        with connect("monitoring_ro", PW_MONITORING) as conn, conn.cursor() as cur:
            cur.execute("CREATE TABLE raw.hack (x int)")
    with pytest.raises(psycopg2.Error):
        with connect("api_ro", PW_API) as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM raw.prices")  # l'API ne lit jamais les donnees brutes
    with pytest.raises(psycopg2.Error):
        with connect("api_ro", PW_API) as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO ops.quality_runs (run_id, check_name, status) VALUES ('x','x','OK')")


# --------------------------------------------------------------------------- 2. donnees historiques synthetiques
def test_03_seed_history_with_one_spike(settings):
    from psycopg2.extras import execute_values

    start = NOW_HOUR - timedelta(hours=3) - timedelta(hours=24 * 60)
    rows = []
    for coin, symbol, name, base in (("bitcoin", "btc", "Bitcoin", 60000.0), ("ethereum", "eth", "Ethereum", 3000.0)):
        for n in range(24 * 60 - 1):
            ts = start + timedelta(hours=n)
            price = base * (1 + 0.05 * math.sin(n / 50.0))
            if n == SPIKE_HOUR and coin == "bitcoin":
                price *= 1.12  # anomalie injectee : +12 % sur une heure
            rows.append((coin, symbol, name, ts, price, base * 2e7, base * 5e5, price * 1.01, price * 0.99,
                         0.5, "seed"))
    with connect() as conn, conn.cursor() as cur:
        execute_values(
            cur,
            "INSERT INTO raw.prices (coin_id, symbol, name, snapshot_ts, price_usd, market_cap_usd, "
            "volume_24h_usd, high_24h_usd, low_24h_usd, pct_change_24h, source_file) VALUES %s",
            rows,
        )
    assert scalar("SELECT count(*) FROM raw.prices") == len(rows)


# --------------------------------------------------------------------------- 3. pipeline horaire
def test_04_ingest_validate_load_is_idempotent(settings, monkeypatch):
    from cryptopulse_ingestion import ingest, load, validate
    from cryptopulse_ingestion.clients import get_blob

    monkeypatch.setattr(ingest, "fetch_markets", lambda s: fake_markets())
    path = ingest.run(NOW_HOUR, settings)
    assert path.startswith("coingecko/markets/year=")
    assert json.loads(get_blob(settings, settings.bronze_container, path))["records"]
    assert validate.run(NOW_HOUR, settings) == 2
    assert load.run(NOW_HOUR, settings) == 2
    assert load.run(NOW_HOUR, settings) == 0  # idempotence : aucune ligne dupliquee
    monkeypatch.setattr(ingest, "fetch_markets", lambda s: fake_markets(factor=1.01))
    ingest.run(NOW_HOUR, settings)  # nouvelle tentative de la meme heure : le blob est ecrase
    assert load.run(NOW_HOUR, settings) == 0


def test_05_dbt_main_pipeline():
    out = run_dbt("build", "--exclude", "tag:sentiment", "tag:forecast")
    assert re.search(r"ERROR=0", out) and re.search(r"PASS=\d+", out), out[-1500:]
    assert scalar("SELECT count(*) FROM marts.dim_coins") == 2
    assert scalar("SELECT count(*) FROM marts.fct_latest_prices") == 2
    assert scalar("SELECT count(*) FROM marts.fct_daily_prices") >= 60


def test_06_indicators_are_null_until_window_is_full():
    assert scalar("SELECT count(*) FROM marts.fct_price_indicators WHERE ma_30d IS NOT NULL") > 0
    first_days = scalar(
        "SELECT count(*) FROM (SELECT ma_30d FROM marts.fct_price_indicators WHERE coin_id='bitcoin' "
        "ORDER BY price_date LIMIT 29) t WHERE ma_30d IS NOT NULL"
    )
    assert first_days == 0


def test_07_anomaly_detection_finds_the_injected_spike():
    spike_ts = NOW_HOUR - timedelta(hours=3) - timedelta(hours=24 * 60) + timedelta(hours=SPIKE_HOUR)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT snapshot_ts, direction, z_score FROM marts.fct_price_anomalies "
                    "WHERE is_anomaly AND coin_id='bitcoin' ORDER BY snapshot_ts")
        anomalies = cur.fetchall()
        cur.execute("SELECT count(*) FROM marts.fct_price_anomalies WHERE is_anomaly AND coin_id='ethereum'")
        eth = cur.fetchone()[0]
    stamps = {a[0] for a in anomalies}
    assert spike_ts in stamps, anomalies
    assert {a[1] for a in anomalies if a[0] == spike_ts} == {"hausse"}
    assert spike_ts + timedelta(hours=1) in stamps  # le retour a la normale est aussi detecte
    assert eth == 0  # aucun faux positif sur la serie sans anomalie


def test_08_quality_report_and_freshness(settings):
    from cryptopulse_ingestion import quality
    from cryptopulse_ingestion.clients import blob_service

    run_id = quality.run_report(settings)
    quality.assert_quality(settings, run_id)
    quality.check_freshness(settings)
    names = [b.name for b in blob_service(settings).get_container_client(settings.gold_container)
             .list_blobs(name_starts_with="reports/quality/")]
    assert names, "le rapport qualite doit etre depose dans gold"


def test_09_parquet_exports_match_postgres(settings):
    import pyarrow.parquet as pq
    from cryptopulse_ingestion import lake
    from cryptopulse_ingestion.clients import get_blob

    result = lake.run(NOW_HOUR, settings)
    assert result["silver"] > 0 and result["gold"]["fct_daily_prices"] >= 60
    silver = pq.read_table(io.BytesIO(get_blob(settings, settings.silver_container, lake.silver_path(NOW_HOUR.date()))))
    expected = scalar("SELECT count(*) FROM staging.stg_prices WHERE price_date = %s", NOW_HOUR.date())
    assert silver.num_rows == expected
    gold = pq.read_table(io.BytesIO(get_blob(settings, settings.gold_container,
                                             lake.gold_path("fct_daily_prices", NOW_HOUR.date()))))
    assert gold.num_rows == result["gold"]["fct_daily_prices"]
    assert "close_usd" in gold.column_names


def test_10_backfill_never_overwrites_real_snapshots(settings):
    from cryptopulse_ingestion import backfill

    anchor = NOW_HOUR - timedelta(days=61)
    points = [(anchor - timedelta(hours=h), 50000.0 + h) for h in range(48)]
    points += [(NOW_HOUR, 1.0)]  # heure courante : doit etre ignoree

    def fake_fetch(coin, days):
        return {"prices": [[int(t.timestamp() * 1000), p] for t, p in points], "market_caps": [],
                "total_volumes": []}

    before_current = scalar("SELECT price_usd FROM raw.prices WHERE coin_id='bitcoin' AND snapshot_ts=%s", NOW_HOUR)
    inserted = backfill.run(settings, days=90, now=NOW_HOUR + timedelta(minutes=30), fetch=fake_fetch)
    assert inserted == 2 * 48
    assert backfill.run(settings, days=90, now=NOW_HOUR + timedelta(minutes=30), fetch=fake_fetch) == 0
    assert scalar("SELECT price_usd FROM raw.prices WHERE coin_id='bitcoin' AND snapshot_ts=%s", NOW_HOUR) == before_current


# --------------------------------------------------------------------------- 4. sentiment
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>Bitcoin surges to record high as investors celebrate</title><link>https://news.example/a</link>
<pubDate>%(now)s</pubDate></item>
<item><title>Ethereum crashes amid fears and heavy losses</title><link>https://news.example/b</link>
<pubDate>%(now)s</pubDate></item></channel></rss>"""


def test_11_sentiment_news_and_fear_greed(settings):
    from email.utils import format_datetime

    from cryptopulse_ingestion import sentiment

    feed = RSS % {b"now": format_datetime(NOW_HOUR).encode()}
    assert sentiment.run_news(NOW_HOUR, settings, fetch=lambda url: feed) == 2 * len(settings.news_feeds) // len(
        settings.news_feeds)
    assert sentiment.run_news(NOW_HOUR, settings, fetch=lambda url: feed) == 0  # idempotent

    payload = {"data": [
        {"value": str(40 + i), "value_classification": "Fear", "timestamp": str(int((NOW_HOUR - timedelta(days=i)).timestamp()))}
        for i in range(10)]}
    assert sentiment.run_fear_greed(NOW_HOUR, settings, fetch=lambda: payload) == 10
    assert sentiment.run_fear_greed(NOW_HOUR, settings, fetch=lambda: payload) == 10  # upsert

    out = run_dbt("build", "--select", "tag:sentiment")
    assert "ERROR=0" in out, out[-1500:]
    assert scalar("SELECT count(*) FROM marts.fct_daily_sentiment") == 2
    assert scalar("SELECT count(*) FROM marts.fct_fear_greed") == 10
    assert scalar("SELECT label FROM staging.stg_news WHERE coin_id='bitcoin'") == "positive"
    assert scalar("SELECT label FROM staging.stg_news WHERE coin_id='ethereum'") == "negative"


# --------------------------------------------------------------------------- 5. previsions
def test_12_forecast_and_accuracy(settings):
    from cryptopulse_ingestion import forecast

    today = date.today()
    assert forecast.run(settings, today) == 2 * settings.forecast_horizon_days
    assert forecast.run(settings, today) == 2 * settings.forecast_horizon_days  # rejouable
    assert scalar("SELECT count(*) FROM ops.forecast_history") == 2 * settings.forecast_horizon_days

    # Prevision passee fictive, pour que le backtest ait quelque chose a evaluer
    yesterday = today - timedelta(days=1)
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT close_usd FROM marts.fct_daily_prices WHERE coin_id='bitcoin' AND price_date=%s", (yesterday,))
        close = float(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO ops.forecast_history VALUES ('bitcoin', %s, %s, 1, %s, %s, %s, 'test', 30)",
            (yesterday, yesterday - timedelta(days=1), close * 1.02, close * 0.9, close * 1.1),
        )
    out = run_dbt("build", "--select", "tag:forecast")
    assert "ERROR=0" in out, out[-1500:]
    assert scalar("SELECT count(*) FROM marts.fct_forecasts_latest WHERE coin_id='bitcoin'") >= settings.forecast_horizon_days
    assert float(scalar("SELECT mape_pct FROM marts.fct_forecast_accuracy WHERE coin_id='bitcoin'")) == pytest.approx(
        100 * 0.02 / 1.0 * (close / close), rel=0.05)
    assert float(scalar("SELECT interval_hit_rate_pct FROM marts.fct_forecast_accuracy WHERE coin_id='bitcoin'")) == 100.0


def test_13_roles_still_work_after_dbt_recreated_the_tables():
    """dbt supprime et recree les tables : api_ro doit les lire grace aux privileges par defaut."""
    assert scalar("SELECT count(*) FROM marts.fct_latest_prices", user="api_ro", password=PW_API) == 2
    assert scalar("SELECT count(*) FROM ops.quality_runs", user="api_ro", password=PW_API) > 0


# --------------------------------------------------------------------------- 6. API
def test_14_api_against_real_database(monkeypatch):
    from fastapi.testclient import TestClient

    for key, value in {"API_KEY": "e2e-key-0123456789abcdef", "API_METRICS_PORT": "0",
                       "POSTGRES_USER": "api_ro", "POSTGRES_PASSWORD": PW_API}.items():
        monkeypatch.setenv(key, value)  # restaure l'environnement : les tests suivants utilisent le role proprietaire
    sys.path.insert(0, str(APP / "api"))
    import main
    headers = {"X-API-Key": os.environ["API_KEY"]}

    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok", "database": "up"}
        assert client.get("/v1/coins").status_code == 401
        coins = client.get("/v1/coins", headers=headers).json()
        assert {c["coin_id"] for c in coins} == set(COINS)
        latest = client.get("/v1/prices/bitcoin/latest", headers=headers).json()
        assert latest["symbol"] == "btc" and latest["price_usd"] > 0
        daily = client.get("/v1/prices/bitcoin/daily?limit=5", headers=headers).json()
        assert len(daily) == 5 and daily[0]["price_date"] > daily[-1]["price_date"]
        assert client.get("/v1/prices/bitcoin/daily?start=2999-01-01", headers=headers).json() == []
        assert client.get("/v1/indicators/bitcoin?limit=3", headers=headers).json()
        assert client.get("/v1/anomalies?coin_id=bitcoin&hours=2160", headers=headers).json()
        assert len(client.get("/v1/forecasts/bitcoin", headers=headers).json()) >= 7
        assert client.get("/v1/sentiment/bitcoin", headers=headers).json()[0]["articles"] == 1
        assert client.get("/v1/fear-greed?limit=3", headers=headers).json()[0]["value"] in range(0, 101)
        assert {q["check_name"] for q in client.get("/v1/quality/latest", headers=headers).json()} >= {"row_count"}
        assert client.get("/v1/prices/unknown/latest", headers=headers).status_code == 404


# --------------------------------------------------------------------------- 7. supervision
def _sql_from_dashboards():
    statements = []
    for path in sorted(DASHBOARDS.glob("*.json")):
        dash = json.loads(path.read_text(encoding="utf-8"))
        for panel in dash["panels"]:
            for target in panel.get("targets", []):
                if "rawSql" in target:
                    statements.append((f"{path.name}:{panel['title']}", target["rawSql"]))
        for var in dash["templating"]["list"]:
            if var.get("datasource", {}).get("uid") == "cryptopulse-pg":
                statements.append((f"{path.name}:var:{var['name']}", var["query"]))
        for annotation in dash["annotations"]["list"]:
            if "target" in annotation and "rawSql" in annotation["target"]:
                statements.append((f"{path.name}:annotation:{annotation['name']}", annotation["target"]["rawSql"]))
    return statements


def grafana_to_sql(sql: str) -> str:
    sql = re.sub(r"\$__timeFilter\(([^)]+)\)", r"\1 >= now() - interval '90 days'", sql)
    sql = re.sub(r"\$__timeFrom\(\)", "now() - interval '90 days'", sql)
    sql = re.sub(r"\$__timeTo\(\)", "now()", sql)
    return sql.replace("${coin}", "bitcoin").replace("$coins", "'bitcoin','ethereum'")


def test_15_every_dashboard_query_runs_with_the_read_only_role():
    statements = _sql_from_dashboards()
    assert len(statements) >= 25, "les dashboards doivent contenir de nombreuses requetes SQL"
    failures = []
    with connect("monitoring_ro", PW_MONITORING) as conn:
        for name, sql in statements:
            with conn.cursor() as cur:
                try:
                    cur.execute(grafana_to_sql(sql))
                    cur.fetchall()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    failures.append(f"{name}: {exc}".splitlines()[0])
    assert not failures, "\n".join(failures)


def test_16_dashboards_return_data_for_key_panels():
    """Les requetes ne doivent pas seulement s'executer : elles doivent aussi retourner des donnees."""
    expected_non_empty = ("Bougies journalieres", "Cotations", "Repartition", "Performance comparee",
                          "Anomalies detectees", "Prevision a 7 jours", "Indice actuel", "Evolution de l'indice",
                          "Sentiment moyen", "Articles par crypto", "Prix et sentiment", "Titres recents")
    seen = set()
    with connect("monitoring_ro", PW_MONITORING) as conn:
        for name, sql in _sql_from_dashboards():
            if not any(key in name for key in expected_non_empty):
                continue
            with conn.cursor() as cur:
                cur.execute(grafana_to_sql(sql))
                if cur.fetchall():
                    seen.add(next(k for k in expected_non_empty if k in name))
    assert seen == set(expected_non_empty), f"panneaux sans donnees : {set(expected_non_empty) - seen}"


def test_17_postgres_exporter_custom_queries():
    import yaml

    queries = yaml.safe_load(QUERIES.read_text(encoding="utf-8"))
    assert {"cryptopulse_freshness", "cryptopulse_rows", "cryptopulse_quality", "cryptopulse_price"} <= set(queries)
    with connect("monitoring_ro", PW_MONITORING) as conn:
        for name, spec in queries.items():
            with conn.cursor() as cur:
                cur.execute(spec["query"])
                columns = [d[0] for d in cur.description]
                rows = cur.fetchall()
            declared = [next(iter(m)) for m in spec["metrics"]]
            assert set(declared) == set(columns), (name, declared, columns)
            assert rows, f"{name} ne retourne aucune ligne"
    assert float(scalar("SELECT age_hours FROM (" + queries["cryptopulse_freshness"]["query"] + ") q",
                        user="monitoring_ro", password=PW_MONITORING)) < 3


# --------------------------------------------------------------------------- 8. sauvegarde et restauration
def test_18_backup_and_restore_roundtrip(tmp_path):
    """Memes options de pg_dump et pg_restore que scripts/cryptopulse-backup et cryptopulse-restore."""
    dump = tmp_path / "cryptopulse.dump"
    env = psql_env()
    with open(dump, "wb") as fh:
        subprocess.run(["pg_dump", "-Fc", "--no-owner"], check=True, stdout=fh, env=env)
    assert dump.stat().st_size > 10_000
    listing = subprocess.run(["pg_restore", "--list", str(dump)], check=True, capture_output=True, text=True, env=env)
    assert "raw.prices" in listing.stdout or "prices" in listing.stdout

    before = scalar("SELECT count(*) FROM raw.prices")
    with connect() as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM raw.prices WHERE coin_id = 'ethereum'")
        cur.execute("DROP TABLE marts.fct_daily_prices")
    assert scalar("SELECT count(*) FROM raw.prices") < before

    subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--single-transaction", "-d", env["PGDATABASE"],
                    str(dump)], check=True, capture_output=True, env=env)
    assert scalar("SELECT count(*) FROM raw.prices") == before
    assert scalar("SELECT count(*) FROM marts.fct_daily_prices") >= 60

    # Apres restauration, le script de roles est rejoue (comme le fait cryptopulse-restore)
    subprocess.run(["psql", "-v", "ON_ERROR_STOP=1", "-v", f"pw_monitoring={PW_MONITORING}", "-v", f"pw_api={PW_API}",
                    "-f", str(ROLES_SQL)], check=True, capture_output=True, env=env)
    assert scalar("SELECT count(*) FROM marts.fct_daily_prices", user="api_ro", password=PW_API) >= 60
