"""Sources complementaires : actualites crypto (sentiment) et Fear & Greed Index."""
from __future__ import annotations

from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from cryptopulse_common import DBT_POOL, DEFAULT_ARGS, dbt_build, get_settings, snapshot

TS = "{{ data_interval_end.isoformat() }}"


def _news(ts_iso: str) -> int:
    from cryptopulse_ingestion import sentiment

    return sentiment.run_news(snapshot(ts_iso), get_settings())


def _fear_greed(ts_iso: str) -> int:
    from cryptopulse_ingestion import sentiment

    return sentiment.run_fear_greed(snapshot(ts_iso), get_settings())


with DAG(
    dag_id="cryptopulse_sentiment",
    description="Flux RSS scores avec VADER, Fear & Greed Index, modeles dbt de sentiment",
    default_args=DEFAULT_ARGS,
    start_date=datetime(2026, 1, 1),
    schedule="20 * * * *",  # decale de 20 minutes par rapport au pipeline principal
    catchup=False,
    max_active_runs=1,
    tags=["cryptopulse", "sentiment"],
) as dag:
    ingest_news = PythonOperator(task_id="ingest_news", python_callable=_news, op_args=[TS])
    ingest_fear_greed = PythonOperator(task_id="ingest_fear_greed", python_callable=_fear_greed, op_args=[TS])
    dbt_build_sentiment = BashOperator(
        task_id="dbt_build_sentiment", bash_command=dbt_build("--select", "tag:sentiment"), pool=DBT_POOL
    )

    ingest_news >> ingest_fear_greed >> dbt_build_sentiment
