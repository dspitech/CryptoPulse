"""Previsions quotidiennes de prix (ARIMA) et mesure de leur precision passee."""
from __future__ import annotations

from datetime import UTC, datetime

from airflow import DAG
from airflow.exceptions import AirflowSkipException
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from cryptopulse_common import DBT_POOL, DEFAULT_ARGS, dbt_build, get_settings


def _forecast() -> int:
    from cryptopulse_ingestion import forecast

    try:
        return forecast.run(get_settings(), datetime.now(UTC).date())
    except forecast.NotReadyError as exc:  # premier demarrage : les marts dbt n'existent pas encore
        raise AirflowSkipException(str(exc)) from exc


with DAG(
    dag_id="cryptopulse_forecast",
    description="Previsions a 7 jours, puis modeles dbt de previsions et de precision",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="30 2 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "forecast"],
) as dag:
    run_forecast = PythonOperator(task_id="run_forecast", python_callable=_forecast)
    dbt_build_forecast = BashOperator(
        task_id="dbt_build_forecast", bash_command=dbt_build("--select", "tag:forecast"), pool=DBT_POOL
    )

    run_forecast >> dbt_build_forecast
