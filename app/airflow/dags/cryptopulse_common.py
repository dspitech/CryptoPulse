"""Elements communs aux DAGs CryptoPulse."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import requests

log = logging.getLogger(__name__)

DBT_BIN = "/home/airflow/dbt-venv/bin/dbt"
DBT_DIR = "/opt/airflow/dbt"

# Pool a un seul slot : les executions dbt de tous les DAGs sont serialisees, car elles
# recreent des tables que d'autres DAGs peuvent lire.
DBT_POOL = "dbt"


def dbt_build(*selectors: str) -> str:
    """Commande dbt build. Exemple : dbt_build('--select', 'tag:sentiment')."""
    args = " ".join(selectors)
    return f"cd {DBT_DIR} && {DBT_BIN} build --project-dir {DBT_DIR} --profiles-dir {DBT_DIR} {args}".strip()


# Le pipeline horaire construit tout sauf les modeles gerees par les DAGs sentiment et forecast.
DBT_MAIN_SELECTORS = ("--exclude", "tag:sentiment", "tag:forecast")


def get_settings():
    from cryptopulse_ingestion.config import get_settings as _get

    return _get()


def snapshot(ts_iso: str) -> datetime:
    """Instant logique tronque a l'heure : garantit l'idempotence des reprises."""
    return datetime.fromisoformat(ts_iso).replace(minute=0, second=0, microsecond=0)


def on_failure(context) -> None:
    ti = context["task_instance"]
    message = f"CryptoPulse: la tache {ti.task_id} du DAG {ti.dag_id} a echoue ({context['ts']})."
    log.error(message)
    url = os.environ.get("NOTIFY_WEBHOOK_URL")
    if url:
        try:
            requests.post(url, json={"text": message}, timeout=10)
        except requests.RequestException:
            log.exception("Envoi de la notification impossible")


DEFAULT_ARGS = {
    "owner": "dataops",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure,
}
