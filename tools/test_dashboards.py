"""Verifie la coherence des dashboards Grafana generes."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASH_DIR = ROOT / "app" / "monitoring" / "grafana" / "dashboards"
KNOWN_DS = {"prometheus", "cryptopulse-pg", "loki", "-- Grafana --"}


def load():
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(DASH_DIR.glob("*.json"))}


def test_dashboards_exist():
    assert len(load()) >= 5


def test_unique_uids_and_titles():
    dashboards = load().values()
    uids = [d["uid"] for d in dashboards]
    titles = [d["title"] for d in dashboards]
    assert len(set(uids)) == len(uids)
    assert len(set(titles)) == len(titles)


def test_datasources_are_provisioned():
    for name, d in load().items():
        for p in d["panels"]:
            if p["type"] == "row":
                continue
            assert p["datasource"]["uid"] in KNOWN_DS, (name, p["title"])
            for t in p["targets"]:
                assert t["datasource"]["uid"] in KNOWN_DS, (name, p["title"])
        for v in d["templating"]["list"]:
            if v["type"] != "textbox":  # une variable textbox n'a pas de datasource
                assert v["datasource"]["uid"] in KNOWN_DS, (name, v["name"])
        for a in d["annotations"]["list"]:
            assert a["datasource"]["uid"] in KNOWN_DS | {"-- Grafana --"}, (name, a["name"])


def test_panels_fit_grid_without_overlap():
    for name, d in load().items():
        boxes = []
        for p in d["panels"]:
            g = p["gridPos"]
            assert 0 <= g["x"] and g["x"] + g["w"] <= 24, (name, p["title"])
            boxes.append((g["x"], g["y"], g["x"] + g["w"], g["y"] + g["h"], p["title"]))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                overlap = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                assert not overlap, (name, a[4], b[4])


def test_panel_ids_unique_and_targets_present():
    for name, d in load().items():
        ids = [p["id"] for p in d["panels"]]
        assert len(set(ids)) == len(ids), name
        for p in d["panels"]:
            if p["type"] != "row":
                assert p["targets"], (name, p["title"])


def test_generated_files_are_up_to_date():
    before = {p.name: p.read_text(encoding="utf-8") for p in DASH_DIR.glob("*.json")}
    subprocess.run([sys.executable, str(ROOT / "tools" / "generate_dashboards.py")], check=True,
                   capture_output=True)
    after = {p.name: p.read_text(encoding="utf-8") for p in DASH_DIR.glob("*.json")}
    assert before == after, "Relancer python tools/generate_dashboards.py et versionner le resultat"
