"""Verifie la structure des DAGs sans installer Airflow (modules factices)."""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

DAGS = Path(__file__).resolve().parent.parent / "dags"


class FakeDAG:
    registry: list = []
    current = None

    def __init__(self, dag_id, **kwargs):
        self.dag_id, self.kwargs, self.tasks, self.edges = dag_id, kwargs, {}, set()

    def __enter__(self):
        FakeDAG.current = self
        return self

    def __exit__(self, *exc):
        FakeDAG.current = None
        FakeDAG.registry.append(self)


class FakeOp:
    def __init__(self, task_id, **kwargs):
        self.task_id, self.kwargs, self.dag = task_id, kwargs, FakeDAG.current
        assert task_id not in self.dag.tasks, f"task_id duplique : {task_id}"
        self.dag.tasks[task_id] = self

    def __rshift__(self, other):
        for o in other if isinstance(other, list) else [other]:
            self.dag.edges.add((self.task_id, o.task_id))
        return other


class FakeSkip(Exception):
    pass


@pytest.fixture(scope="module")
def dags():
    fakes = {
        "airflow": types.SimpleNamespace(DAG=FakeDAG),
        "airflow.operators": types.ModuleType("airflow.operators"),
        "airflow.operators.bash": types.SimpleNamespace(BashOperator=FakeOp),
        "airflow.operators.python": types.SimpleNamespace(PythonOperator=FakeOp),
        "airflow.exceptions": types.SimpleNamespace(AirflowSkipException=FakeSkip),
        "airflow.models": types.ModuleType("airflow.models"),
        "airflow.models.param": types.SimpleNamespace(Param=lambda default, **kw: {"default": default, **kw}),
    }
    saved = {k: sys.modules.get(k) for k in fakes}
    sys.modules.update(fakes)
    sys.path.insert(0, str(DAGS))
    FakeDAG.registry.clear()
    try:
        for name in ("cryptopulse_pipeline", "cryptopulse_backfill", "cryptopulse_sentiment", "cryptopulse_forecast"):
            spec = importlib.util.spec_from_file_location(name, DAGS / f"{name}.py")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        yield {d.dag_id: d for d in FakeDAG.registry}
    finally:
        sys.path.remove(str(DAGS))
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def is_acyclic(dag):
    remaining = set(dag.tasks)
    edges = set(dag.edges)
    while remaining:
        free = {t for t in remaining if not any(b == t and a in remaining for a, b in edges)}
        if not free:
            return False
        remaining -= free
    return True


def test_four_dags_are_registered(dags):
    assert set(dags) == {"cryptopulse_pipeline", "cryptopulse_backfill", "cryptopulse_sentiment", "cryptopulse_forecast"}


def test_all_dags_are_acyclic_and_connected(dags):
    for dag in dags.values():
        assert is_acyclic(dag), dag.dag_id
        linked = {t for edge in dag.edges for t in edge}
        assert linked == set(dag.tasks), f"taches isolees dans {dag.dag_id}"
        assert dag.kwargs["catchup"] is False and dag.kwargs["max_active_runs"] == 1


def test_main_pipeline_order(dags):
    chain = ["ingest_prices", "validate_bronze", "load_staging", "dbt_build", "export_lake",
             "quality_report", "check_quality", "freshness_check", "notify"]
    assert dags["cryptopulse_pipeline"].edges == set(zip(chain, chain[1:], strict=False))
    assert dags["cryptopulse_pipeline"].kwargs["schedule"] == "@hourly"


def test_dbt_selections_match_what_the_e2e_test_validates(dags):
    """tests/e2e/test_e2e.py execute exactement ces selections dbt."""
    cmd = lambda dag, task: dags[dag].tasks[task].kwargs["bash_command"]  # noqa: E731
    assert cmd("cryptopulse_pipeline", "dbt_build").endswith("--exclude tag:sentiment tag:forecast")
    assert cmd("cryptopulse_backfill", "dbt_build").endswith("--exclude tag:sentiment tag:forecast")
    assert cmd("cryptopulse_sentiment", "dbt_build_sentiment").endswith("--select tag:sentiment")
    assert cmd("cryptopulse_forecast", "dbt_build_forecast").endswith("--select tag:forecast")
    for dag in dags.values():
        for task in dag.tasks.values():
            if "bash_command" in task.kwargs:
                assert task.kwargs["pool"] == "dbt", "les executions dbt doivent etre serialisees"
                assert "/home/airflow/dbt-venv/bin/dbt build" in task.kwargs["bash_command"]


def test_schedules_do_not_overlap_on_the_hour(dags):
    assert dags["cryptopulse_sentiment"].kwargs["schedule"] == "20 * * * *"
    assert dags["cryptopulse_forecast"].kwargs["schedule"] == "30 2 * * *"
    assert dags["cryptopulse_backfill"].kwargs["schedule"] is None


def test_backfill_exposes_bounded_days_parameter(dags):
    days = dags["cryptopulse_backfill"].kwargs["params"]["days"]
    assert days["default"] == 90 and days["minimum"] == 2 and days["maximum"] == 365
    assert dags["cryptopulse_backfill"].tasks["backfill_history"].kwargs["op_args"] == ["{{ params.days }}"]


def test_forecast_skips_when_marts_are_missing(dags, monkeypatch):
    cryptopulse_forecast = sys.modules["cryptopulse_forecast"]
    from cryptopulse_ingestion import forecast

    monkeypatch.setattr(cryptopulse_forecast, "get_settings", lambda: object())

    def not_ready(settings, today):
        raise forecast.NotReadyError("marts absents")

    monkeypatch.setattr(forecast, "run", not_ready)
    with pytest.raises(FakeSkip):
        cryptopulse_forecast._forecast()
