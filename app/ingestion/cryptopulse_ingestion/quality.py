"""Etapes de controle : rapport qualite, verification du statut et fraicheur."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from .clients import pg_connect, put_blob
from .config import Settings
from .db import ensure_schema

log = logging.getLogger(__name__)


@dataclass
class Check:
    name: str
    metric: float | None
    status: str
    details: str


def evaluate(total_rows: int, bad_prices: int, coins_in_latest: int, expected_coins: int) -> list[Check]:
    return [
        Check(
            "row_count",
            total_rows,
            "OK" if total_rows > 0 else "FAIL",
            f"{total_rows} lignes dans raw.prices",
        ),
        Check(
            "invalid_prices",
            bad_prices,
            "OK" if bad_prices == 0 else "FAIL",
            f"{bad_prices} prix nuls ou negatifs",
        ),
        Check(
            "coin_coverage",
            coins_in_latest,
            "OK" if coins_in_latest == expected_coins else "WARNING",
            f"{coins_in_latest} cryptos dans le dernier snapshot, {expected_coins} attendues",
        ),
    ]


def overall_status(checks: list[Check]) -> str:
    statuses = {c.status for c in checks}
    if "FAIL" in statuses:
        return "FAIL"
    if "WARNING" in statuses:
        return "WARNING"
    return "OK"


def render_report(run_id: str, checks: list[Check], generated_at: datetime) -> str:
    lines = [
        "CRYPTOPULSE QUALITY REPORT",
        "==========================",
        f"Run id        : {run_id}",
        f"Genere le     : {generated_at.isoformat()}",
        f"Statut global : {overall_status(checks)}",
        "",
    ]
    lines += [f"[{c.status:<7}] {c.name:<15} {c.details}" for c in checks]
    return "\n".join(lines) + "\n"


def run_report(settings: Settings) -> str:
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)

    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        cur.execute("SELECT count(*) FROM raw.prices")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM raw.prices WHERE price_usd IS NULL OR price_usd <= 0")
        bad = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM raw.prices "
            "WHERE snapshot_ts = (SELECT max(snapshot_ts) FROM raw.prices)"
        )
        latest = cur.fetchone()[0]

        checks = evaluate(total, bad, latest, len(settings.coins))
        for c in checks:
            cur.execute(
                "INSERT INTO ops.quality_runs (run_id, check_name, metric, status, details) "
                "VALUES (%s, %s, %s, %s, %s)",
                (run_id, c.name, c.metric, c.status, c.details),
            )

    report = render_report(run_id, checks, now)
    log.info("\n%s", report)

    blob = (
        f"reports/quality/year={now:%Y}/month={now:%m}/day={now:%d}/"
        f"quality_{now:%Y%m%dT%H%M%SZ}_{run_id}.txt"
    )
    put_blob(settings, settings.gold_container, blob, report.encode("utf-8"))
    return run_id


def assert_quality(settings: Settings, run_id: str) -> None:
    with pg_connect(settings) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT check_name, details FROM ops.quality_runs WHERE run_id = %s AND status = 'FAIL'",
            (run_id,),
        )
        failures = cur.fetchall()
    if failures:
        raise ValueError(f"Controles qualite en echec : {failures}")
    log.info("Statut qualite acceptable pour le run %s", run_id)


def check_freshness(settings: Settings) -> None:
    run_id = f"fresh-{uuid.uuid4().hex[:8]}"
    with pg_connect(settings) as conn, conn.cursor() as cur:
        ensure_schema(cur)
        cur.execute(
            "SELECT extract(epoch FROM (now() - max(snapshot_ts))) / 3600 FROM raw.prices"
        )
        age_hours = cur.fetchone()[0]
        stale = age_hours is None or float(age_hours) > settings.freshness_max_hours
        cur.execute(
            "INSERT INTO ops.quality_runs (run_id, check_name, metric, status, details) "
            "VALUES (%s, 'freshness', %s, %s, %s)",
            (
                run_id,
                None if age_hours is None else float(age_hours),
                "FAIL" if stale else "OK",
                f"age du dernier snapshot : {age_hours} h (seuil {settings.freshness_max_hours} h)",
            ),
        )
    if stale:
        raise ValueError(f"Donnees perimees : age {age_hours} h, seuil {settings.freshness_max_hours} h")
