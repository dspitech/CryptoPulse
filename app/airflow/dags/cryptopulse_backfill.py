"""Backfill de l'historique de prix : a declencher manuellement (parametre `days`)."""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from cryptopulse_common import DBT_MAIN_SELECTORS, DBT_POOL, DEFAULT_ARGS, dbt_build, get_settings


def _backfill(days) -> int:
    from cryptopulse_ingestion import backfill

    return backfill.run(get_settings(), int(days))


with DAG(
    dag_id="cryptopulse_backfill",
    description="Charge l'historique horaire (jusqu'a 90 jours) puis recalcule les modeles dbt",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    params={
        "days": Param(
            90, type="integer", minimum=2, maximum=365,
            description="Profondeur d'historique. Jusqu'a 90 jours : points horaires. Au-dela : points quotidiens.",
        )
    },
    tags=["cryptopulse", "backfill"],
) as dag:
    backfill_history = PythonOperator(
        task_id="backfill_history", python_callable=_backfill, op_args=["{{ params.days }}"]
    )
    dbt_build_main = BashOperator(
        task_id="dbt_build", bash_command=dbt_build(*DBT_MAIN_SELECTORS), pool=DBT_POOL
    )

    backfill_history >> dbt_build_main
