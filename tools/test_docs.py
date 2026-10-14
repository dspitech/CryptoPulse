"""La documentation ne doit pas deriver du code : chaque element cite est verifie."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")
RUNBOOK = (ROOT / "docs" / "runbook.md").read_text(encoding="utf-8")
DOCS = {p: p.read_text(encoding="utf-8") for p in [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]}
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")


def alert_names():
    names = []
    for f in sorted((ROOT / "app/monitoring/prometheus/rules").glob("*.yml")):
        for group in yaml.safe_load(f.read_text(encoding="utf-8"))["groups"]:
            names += [r["alert"] for r in group["rules"]]
    return names


def dashboards():
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "app/monitoring/grafana/dashboards").glob("*.json"))]


def test_no_emoji_and_no_long_dashes():
    for path, text in DOCS.items():
        assert "\u2014" not in text and "\u2013" not in text, f"tiret long dans {path.name}"
        assert not re.search("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2705\u274C]", text), f"emoji dans {path.name}"


def test_every_make_target_cited_exists():
    targets = set(re.findall(r"^([a-z][a-z0-9-]*):", MAKEFILE, re.MULTILINE))
    for path, text in DOCS.items():
        for target in re.findall(r"`make ([a-z][a-z0-9-]*)", text):
            assert target in targets, f"make {target} cite dans {path.name} mais absent du Makefile"


def test_every_alert_is_documented_in_readme_and_runbook():
    for name in alert_names():
        assert f"| {name}" in README or f"| {name}," in README or name in README, f"{name} absente du README"
        assert name in RUNBOOK, f"{name} absente du runbook"


def test_numeric_claims_match_reality():
    assert int(re.search(r"(\d+) règles d'alerte", README).group(1)) == len(alert_names())
    models = len(list((ROOT / "app/dbt/models").rglob("*.sql")))
    assert int(re.search(r"dbt : (\d+) modèles", README).group(1)) == models
    assert int(re.search(r"(\d+) dashboards Grafana", README).group(1)) == len(dashboards())
    exporters = len(re.findall(r"^  (?:node|postgres|statsd|blackbox)-exporter:|^  cadvisor:", (ROOT / "app/deploy/docker-compose.yml").read_text(), re.M))
    assert int(re.search(r"(\d+) exporters", README).group(1)) == exporters
    promql = sum(1 for d in dashboards() for p in d["panels"] for t in p.get("targets", [])
                 if "expr" in t and t["datasource"]["uid"] == "prometheus")
    assert int(re.search(r"Les (\d+) requêtes PromQL", README).group(1)) == promql
    adr = len(list((ROOT / "docs/adr").glob("0*.md")))
    assert f"{adr} décisions d'architecture" in README.replace("Onze", "11")


def test_every_terraform_variable_is_documented():
    text = (ROOT / "infra/modules/platform/variables.tf").read_text(encoding="utf-8")
    for name in re.findall(r'^variable "(\w+)"', text, re.MULTILINE):
        assert f"`{name}`" in README, f"variable {name} non documentee dans le README"


def test_every_dag_and_dashboard_is_documented():
    for dag in re.findall(r'dag_id="(\w+)"', "".join(p.read_text() for p in (ROOT / "app/airflow/dags").glob("*.py"))):
        assert f"`{dag}`" in README, f"DAG {dag} non documente"
    for dash in dashboards():
        assert dash["title"] in README, f"dashboard {dash['title']} non documente"


def test_every_api_route_is_documented():
    source = (ROOT / "app/api/main.py").read_text(encoding="utf-8")
    for path in re.findall(r'@(?:v1|app)\.get\("([^"]+)"', source):
        full = path if path == "/health" else f"/v1{path}"
        assert full in README, f"route {full} non documentee"


def test_every_metric_in_exporter_queries_is_documented():
    queries = yaml.safe_load((ROOT / "app/monitoring/postgres-exporter/queries.yaml").read_text(encoding="utf-8"))
    for prefix, spec in queries.items():
        for metric in spec["metrics"]:
            name, definition = next(iter(metric.items()))
            if definition["usage"] != "LABEL":
                assert f"{prefix}_{name}" in README, f"metrique {prefix}_{name} non documentee"


def test_internal_links_resolve():
    for path, text in DOCS.items():
        for target in re.findall(r"\]\(([^)#\s]+)(?:#([^)]+))?\)", text):
            link, anchor = target
            if link.startswith("http"):
                continue
            destination = (path.parent / link).resolve()
            assert destination.exists(), f"{path.name} : lien casse vers {link}"
            if anchor and destination.suffix == ".md":
                headings = {re.sub(r"[^\w\- ]", "", h.lower()).strip().replace(" ", "-")
                            for h in re.findall(r"^#+ (.+)$", destination.read_text(encoding="utf-8"), re.M)}
                assert anchor in headings, f"{path.name} : ancre #{anchor} introuvable dans {destination.name}"
    for path, text in DOCS.items():
        for anchor in re.findall(r"\]\(#([^)]+)\)", text):
            headings = {re.sub(r"[^\w\- ]", "", h.lower()).strip().replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
            assert anchor in headings, f"{path.name} : ancre interne #{anchor} introuvable"


def test_adr_index_lists_every_adr():
    index = (ROOT / "docs/adr/README.md").read_text(encoding="utf-8")
    for adr in (ROOT / "docs/adr").glob("0*.md"):
        assert adr.name in index, f"{adr.name} absent de l'index"
