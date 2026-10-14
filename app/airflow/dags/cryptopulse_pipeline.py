"""Pipeline horaire : API -> bronze -> staging -> dbt -> Parquet (silver, gold) -> qualite."""
from __future__ import annotations

import logging
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from cryptopulse_common import (
    DBT_MAIN_SELECTORS,
    DBT_POOL,
    DEFAULT_ARGS,
    dbt_build,
    get_settings,
    snapshot,
)

log = logging.getLogger(__name__)

# Instant logique de l'execution, tronque a l'heure cote code (idempotence).
TS = "{{ data_interval_end.isoformat() }}"


def _ingest(ts_iso: str) -> str:
    from cryptopulse_ingestion import ingest

    return ingest.run(snapshot(ts_iso), get_settings())


def _validate(ts_iso: str) -> int:
    from cryptopulse_ingestion import validate

    return validate.run(snapshot(ts_iso), get_settings())


def _load(ts_iso: str) -> int:
    from cryptopulse_ingestion import load

    return load.run(snapshot(ts_iso), get_settings())


def _export_lake(ts_iso: str) -> dict:
    from cryptopulse_ingestion import lake

    return lake.run(snapshot(ts_iso), get_settings())


def _quality_report() -> str:
    from cryptopulse_ingestion import quality

    return quality.run_report(get_settings())


def _check_quality(run_id: str) -> None:
    from cryptopulse_ingestion import quality

    quality.assert_quality(get_settings(), run_id)


def _check_freshness() -> None:
    from cryptopulse_ingestion import quality

    quality.check_freshness(get_settings())


def _notify_success() -> None:
    log.info("Pipeline CryptoPulse termine avec succes.")


with DAG(
    dag_id="cryptopulse_pipeline",
    description="Ingestion de prix crypto, transformation dbt, export Parquet et controles qualite",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="@hourly",
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "dbt", "quality"],
) as dag:
    ingest_prices = PythonOperator(task_id="ingest_prices", python_callable=_ingest, op_args=[TS])
    validate_bronze = PythonOperator(task_id="validate_bronze", python_callable=_validate, op_args=[TS])
    load_staging = PythonOperator(task_id="load_staging", python_callable=_load, op_args=[TS])
    dbt_build_main = BashOperator(
        task_id="dbt_build", bash_command=dbt_build(*DBT_MAIN_SELECTORS), pool=DBT_POOL
    )
    export_lake = PythonOperator(task_id="export_lake", python_callable=_export_lake, op_args=[TS])
    quality_report = PythonOperator(task_id="quality_report", python_callable=_quality_report)
    check_quality = PythonOperator(
        task_id="check_quality",
        python_callable=_check_quality,
        op_args=["{{ ti.xcom_pull(task_ids='quality_report') }}"],
    )
    freshness_check = PythonOperator(task_id="freshness_check", python_callable=_check_freshness)
    notify = PythonOperator(task_id="notify", python_callable=_notify_success)

    (
        ingest_prices
        >> validate_bronze
        >> load_staging
        >> dbt_build_main
        >> export_lake
        >> quality_report
        >> check_quality
        >> freshness_check
        >> notify
    )
