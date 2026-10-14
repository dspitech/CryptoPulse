"""Genere les dashboards Grafana provisionnes (JSON) dans app/monitoring/grafana/dashboards.

Usage : python tools/generate_dashboards.py
Les JSON generes sont versionnes ; la CI verifie qu'ils sont a jour.
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "app" / "monitoring" / "grafana" / "dashboards"

PROM = {"type": "prometheus", "uid": "prometheus"}
PG = {"type": "grafana-postgresql-datasource", "uid": "cryptopulse-pg"}
LOKI = {"type": "loki", "uid": "loki"}

GREEN, YELLOW, ORANGE, RED, BLUE = "green", "yellow", "orange", "red", "blue"


# --------------------------------------------------------------------------- helpers
def thresholds(*steps):
    """steps : liste de (couleur, seuil). Le premier seuil est None (base)."""
    return {
        "mode": "absolute",
        "steps": [{"color": c, "value": v} for c, v in steps],
    }


def prom(expr, legend="", instant=False, ref="A", fmt=None):
    target = {
        "refId": ref,
        "datasource": PROM,
        "expr": expr,
        "legendFormat": legend,
        "range": not instant,
        "instant": instant,
        "editorMode": "code",
    }
    if fmt:
        target["format"] = fmt
    return target


def sql(query, fmt="time_series", ref="A"):
    return {
        "refId": ref,
        "datasource": PG,
        "format": fmt,
        "rawQuery": True,
        "editorMode": "code",
        "rawSql": query.strip(),
    }


def loki(expr, legend="", instant=False, ref="A"):
    return {
        "refId": ref,
        "datasource": LOKI,
        "expr": expr,
        "legendFormat": legend,
        "queryType": "instant" if instant else "range",
        "editorMode": "code",
    }


class Dash:
    def __init__(self, uid, title, tags, time_from="now-7d", refresh="1m", variables=None,
                 time_to="now", annotations=None):
        self.uid, self.title, self.tags = uid, title, tags
        self.time_from, self.time_to, self.refresh = time_from, time_to, refresh
        self.extra_annotations = annotations or []
        self.variables = variables or []
        self.panels = []
        self._id = 0

    def _next(self):
        self._id += 1
        return self._id

    def row(self, title, y):
        self.panels.append(
            {
                "id": self._next(),
                "type": "row",
                "title": title,
                "collapsed": False,
                "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
                "panels": [],
            }
        )

    def panel(self, ptype, title, pos, ds, targets, description="", defaults=None,
              overrides=None, options=None, transformations=None):
        x, y, w, h = pos
        self.panels.append(
            {
                "id": self._next(),
                "type": ptype,
                "title": title,
                "description": description,
                "datasource": ds,
                "gridPos": {"h": h, "w": w, "x": x, "y": y},
                "targets": targets,
                "fieldConfig": {"defaults": defaults or {}, "overrides": overrides or []},
                "options": options or {},
                "transformations": transformations or [],
            }
        )

    def build(self):
        return {
            "id": None,
            "uid": self.uid,
            "title": self.title,
            "tags": self.tags,
            "timezone": "browser",
            "schemaVersion": 39,
            "version": 1,
            "editable": True,
            "graphTooltip": 1,
            "refresh": self.refresh,
            "time": {"from": self.time_from, "to": self.time_to},
            "timepicker": {},
            "templating": {"list": self.variables},
            "annotations": {
                "list": [
                    {
                        "builtIn": 1,
                        "datasource": {"type": "grafana", "uid": "-- Grafana --"},
                        "enable": True,
                        "hide": True,
                        "iconColor": "rgba(0, 211, 255, 1)",
                        "name": "Annotations & Alerts",
                        "type": "dashboard",
                    },
                    *self.extra_annotations,
                ]
            },
            "links": [
                {
                    "title": "Dashboards CryptoPulse",
                    "type": "dashboards",
                    "tags": ["cryptopulse"],
                    "asDropdown": True,
                    "includeVars": False,
                    "keepTime": True,
                }
            ],
            "panels": self.panels,
        }

    def write(self, filename):
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / filename).write_text(
            json.dumps(self.build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


def stat_options(graph="area", color="value", calcs=("lastNotNull",), text="auto"):
    return {
        "reduceOptions": {"calcs": list(calcs), "fields": "", "values": False},
        "colorMode": color,
        "graphMode": graph,
        "justifyMode": "auto",
        "textMode": text,
        "orientation": "auto",
    }


def ts_defaults(unit="short", fill=12, stack=None, style="line", minimum=None, maximum=None, decimals=None):
    d = {
        "unit": unit,
        "color": {"mode": "palette-classic"},
        "custom": {
            "drawStyle": style,
            "lineInterpolation": "smooth",
            "lineWidth": 2,
            "fillOpacity": fill,
            "gradientMode": "opacity",
            "showPoints": "never",
            "spanNulls": True,
            "axisPlacement": "auto",
            "barAlignment": 0,
            "stacking": {"mode": stack or "none", "group": "A"},
        },
    }
    if minimum is not None:
        d["min"] = minimum
    if maximum is not None:
        d["max"] = maximum
    if decimals is not None:
        d["decimals"] = decimals
    return d


TS_OPTIONS = {
    "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True, "calcs": []},
    "tooltip": {"mode": "multi", "sort": "desc"},
}

TS_TABLE_LEGEND = {
    "legend": {"displayMode": "table", "placement": "bottom", "showLegend": True, "calcs": ["lastNotNull", "mean", "max"]},
    "tooltip": {"mode": "multi", "sort": "desc"},
}


def ts(d, title, pos, ds, targets, unit="short", description="", fill=12, stack=None,
       style="line", minimum=None, maximum=None, legend_table=False, decimals=None):
    d.panel("timeseries", title, pos, ds, targets, description,
            defaults=ts_defaults(unit, fill, stack, style, minimum, maximum, decimals),
            options=TS_TABLE_LEGEND if legend_table else TS_OPTIONS)


def stat(d, title, pos, ds, targets, unit="short", steps=None, description="", graph="area",
         decimals=None, mappings=None, color="value", text="auto", color_mode="thresholds"):
    defaults = {
        "unit": unit,
        "color": {"mode": color_mode},
        "thresholds": thresholds(*(steps or [(BLUE, None)])),
        "mappings": mappings or [],
    }
    if decimals is not None:
        defaults["decimals"] = decimals
    d.panel("stat", title, pos, ds, targets, description, defaults=defaults,
            options=stat_options(graph=graph, color=color, text=text))


def gauge(d, title, pos, ds, targets, unit="percent", steps=None, minimum=0, maximum=100, description=""):
    d.panel(
        "gauge", title, pos, ds, targets, description,
        defaults={
            "unit": unit, "min": minimum, "max": maximum,
            "color": {"mode": "thresholds"},
            "thresholds": thresholds(*(steps or [(GREEN, None), (ORANGE, 70), (RED, 90)])),
        },
        options={
            "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
            "showThresholdLabels": False,
            "showThresholdMarkers": True,
            "orientation": "auto",
        },
    )


STATUS_MAPPING = [
    {
        "type": "value",
        "options": {
            "OK": {"text": "OK", "color": "green", "index": 0},
            "WARNING": {"text": "WARNING", "color": "orange", "index": 1},
            "FAIL": {"text": "FAIL", "color": "red", "index": 2},
        },
    }
]

UP_DOWN_MAPPING = [
    {
        "type": "value",
        "options": {
            "0": {"text": "HORS LIGNE", "color": "red", "index": 0},
            "1": {"text": "EN LIGNE", "color": "green", "index": 1},
        },
    }
]


def table(d, title, pos, ds, targets, description="", overrides=None, transformations=None, sort=None):
    options = {"showHeader": True, "cellHeight": "sm", "footer": {"show": False}}
    if sort:
        options["sortBy"] = [{"displayName": sort, "desc": True}]
    d.panel(
        "table", title, pos, ds, targets, description,
        defaults={"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "inspect": False}},
        overrides=overrides, options=options, transformations=transformations,
    )


def override_raw(field, *properties):
    """properties : couples (id, valeur) au format brut de Grafana."""
    return {
        "matcher": {"id": "byName", "options": field},
        "properties": [{"id": i, "value": v} for i, v in properties],
    }


def override(field, **props):
    mapping = {
        "unit": "unit",
        "decimals": "decimals",
        "cell": "custom.cellOptions",
        "mappings": "mappings",
        "thresholds": "thresholds",
        "color": "color",
        "width": "custom.width",
    }
    return {
        "matcher": {"id": "byName", "options": field},
        "properties": [{"id": mapping[k], "value": v} for k, v in props.items()],
    }


# --------------------------------------------------------------------------- dashboard 1 : marche
COIN_VARIABLES = [
    {
        "name": "coin", "label": "Crypto", "type": "query", "datasource": PG,
        "query": "SELECT DISTINCT coin_id FROM raw.prices ORDER BY 1",
        "definition": "SELECT DISTINCT coin_id FROM raw.prices ORDER BY 1",
        "refresh": 1, "sort": 1, "multi": False, "includeAll": False, "current": {},
    },
    {
        "name": "coins", "label": "Comparaison", "type": "query", "datasource": PG,
        "query": "SELECT DISTINCT coin_id FROM raw.prices ORDER BY 1",
        "definition": "SELECT DISTINCT coin_id FROM raw.prices ORDER BY 1",
        "refresh": 1, "sort": 1, "multi": True, "includeAll": True,
        "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
    },
]

ANOMALY_ANNOTATION = {
    "datasource": PG,
    "enable": True,
    "iconColor": "red",
    "name": "Anomalies de prix",
    "target": {
        "refId": "Anno", "datasource": PG, "format": "table", "rawQuery": True, "editorMode": "code",
        "rawSql": (
            "SELECT snapshot_ts AS time, "
            "'Anomalie : ' || direction || ' de ' || return_pct || ' % (z-score ' || z_score || ')' AS text, "
            "'anomalie' AS tags "
            "FROM marts.fct_price_anomalies "
            "WHERE is_anomaly AND coin_id = '${coin}' AND $__timeFilter(snapshot_ts)"
        ),
    },
}


def market():
    d = Dash("cp-market", "CryptoPulse : Marché", ["cryptopulse", "marche"], "now-30d", "1m",
             COIN_VARIABLES, time_to="now+7d", annotations=[ANOMALY_ANNOTATION])

    latest = "SELECT {col} AS \"{label}\" FROM raw.prices WHERE coin_id = '${{coin}}' ORDER BY snapshot_ts DESC LIMIT 1"
    d.row("Synthese", 0)

    series = (
        "SELECT snapshot_ts AS time, price_usd AS \"Prix\" FROM raw.prices "
        "WHERE coin_id = '${coin}' AND $__timeFilter(snapshot_ts) ORDER BY 1"
    )
    stat(d, "Prix actuel", (0, 1, 4, 4), PG, [sql(series)], unit="currencyUSD", decimals=2,
         steps=[(BLUE, None)], description="Dernier prix connu de la crypto selectionnee.")
    stat(d, "Variation 24 h", (4, 1, 4, 4), PG,
         [sql(latest.format(col="pct_change_24h", label="Variation 24h"), fmt="table")],
         unit="percent", decimals=2, graph="none",
         steps=[(RED, None), (GREEN, 0)], description="Variation de prix sur les dernieres 24 heures.")
    stat(d, "Capitalisation", (8, 1, 4, 4), PG,
         [sql(latest.format(col="market_cap_usd", label="Capitalisation"), fmt="table")],
         unit="currencyUSD", graph="none", steps=[(BLUE, None)])
    stat(d, "Volume 24 h", (12, 1, 4, 4), PG,
         [sql(latest.format(col="volume_24h_usd", label="Volume"), fmt="table")],
         unit="currencyUSD", graph="none", steps=[(BLUE, None)])
    stat(d, "Plus haut 24 h", (16, 1, 4, 4), PG,
         [sql(latest.format(col="high_24h_usd", label="Plus haut"), fmt="table")],
         unit="currencyUSD", decimals=2, graph="none", steps=[(GREEN, None)])
    stat(d, "Plus bas 24 h", (20, 1, 4, 4), PG,
         [sql(latest.format(col="low_24h_usd", label="Plus bas"), fmt="table")],
         unit="currencyUSD", decimals=2, graph="none", steps=[(RED, None)])

    d.row("Analyse du marche", 5)
    candles = """
SELECT price_date::timestamp AS time,
       open_usd AS open, high_usd AS high, low_usd AS low, close_usd AS close,
       volume_24h_usd AS volume
FROM marts.fct_daily_prices
WHERE coin_id = '${coin}' AND $__timeFilter(price_date::timestamp)
ORDER BY 1
"""
    d.panel(
        "candlestick", "Bougies journalieres (OHLC)", (0, 6, 16, 10), PG, [sql(candles)],
        description="Ouverture, plus haut, plus bas et cloture par jour, calcules par dbt.",
        defaults={"unit": "currencyUSD", "custom": {"axisPlacement": "auto", "fillOpacity": 40, "lineWidth": 1}},
        options={
            "mode": "candles+volume", "candleStyle": "candles", "colorStrategy": "open-close",
            "colors": {"up": "green", "down": "red"}, "includeAllFields": False,
            "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True, "calcs": []},
        },
    )
    cap = """
SELECT DISTINCT ON (coin_id) coin_id, market_cap_usd
FROM raw.prices
ORDER BY coin_id, snapshot_ts DESC
"""
    d.panel(
        "piechart", "Repartition de la capitalisation", (16, 6, 8, 10), PG, [sql(cap, fmt="table")],
        description="Poids de chaque crypto dans la capitalisation totale suivie.",
        defaults={"unit": "currencyUSD", "color": {"mode": "palette-classic"}},
        options={
            "reduceOptions": {"values": True, "calcs": ["lastNotNull"], "fields": "/^market_cap_usd$/"},
            "pieType": "donut", "displayLabels": ["percent"],
            "legend": {"displayMode": "table", "placement": "right", "showLegend": True, "values": ["value", "percent"]},
            "tooltip": {"mode": "single", "sort": "none"},
        },
    )

    norm = """
SELECT snapshot_ts AS time, coin_id AS metric,
       price_usd / first_value(price_usd) OVER (PARTITION BY coin_id ORDER BY snapshot_ts) * 100 AS value
FROM raw.prices
WHERE $__timeFilter(snapshot_ts) AND coin_id IN ($coins)
ORDER BY 1
"""
    ts(d, "Performance comparee (base 100)", (0, 16, 12, 9), PG, [sql(norm)], unit="short", fill=0,
       description="Evolution relative des cryptos sur la periode, base 100 au debut de la fenetre.",
       legend_table=True, decimals=1)

    ind = """
SELECT price_date::timestamp AS time,
       close_usd AS "Cloture", ma_7d AS "MM 7 jours", ma_30d AS "MM 30 jours"
FROM marts.fct_price_indicators
WHERE coin_id = '${coin}' AND $__timeFilter(price_date::timestamp)
ORDER BY 1
"""
    ts(d, "Cloture et moyennes mobiles", (12, 16, 12, 9), PG, [sql(ind)], unit="currencyUSD", fill=8,
       description="Les moyennes mobiles n'apparaissent que lorsque la fenetre de 7 ou 30 jours est complete. "
                   "Les marqueurs rouges signalent les anomalies detectees.")

    vol = """
SELECT price_date::timestamp AS time, coin_id AS metric, volatility_7d * 100 AS value
FROM marts.fct_price_indicators
WHERE $__timeFilter(price_date::timestamp) AND coin_id IN ($coins)
ORDER BY 1
"""
    ts(d, "Volatilite sur 7 jours", (0, 25, 12, 8), PG, [sql(vol)], unit="percent", fill=0, decimals=2,
       description="Ecart-type des rendements journaliers sur 7 jours glissants.")

    chg = """
SELECT price_date::timestamp AS time, pct_change_1d AS "Variation journaliere"
FROM marts.fct_price_indicators
WHERE coin_id = '${coin}' AND $__timeFilter(price_date::timestamp)
ORDER BY 1
"""
    ts(d, "Variation journaliere", (12, 25, 12, 8), PG, [sql(chg)], unit="percent", fill=70, style="bars", decimals=2)

    d.row("Previsions et anomalies", 33)
    history = """
SELECT price_date::timestamp AS time, close_usd AS "Cloture"
FROM marts.fct_daily_prices
WHERE coin_id = '${coin}' AND $__timeFilter(price_date::timestamp)
ORDER BY 1
"""
    projected = """
SELECT forecast_date::timestamp AS time, yhat AS "Prevision",
       yhat_lower AS "Borne basse (80 %)", yhat_upper AS "Borne haute (80 %)"
FROM marts.fct_forecasts_latest
WHERE coin_id = '${coin}' AND forecast_date >= current_date - 1
ORDER BY 1
"""
    d.panel(
        "timeseries", "Prevision a 7 jours (ARIMA, intervalle a 80 %)", (0, 34, 16, 9), PG,
        [sql(history, ref="A"), sql(projected, ref="B")],
        description="Illustration statistique et non un conseil financier : les cours des cryptomonnaies sont "
                    "tres peu previsibles, l'intervalle s'elargit avec l'horizon.",
        defaults=ts_defaults("currencyUSD", fill=6),
        overrides=[
            override_raw("Prevision", ("color", {"mode": "fixed", "fixedColor": "orange"}),
                         ("custom.lineStyle", {"fill": "dash", "dash": [10, 10]})),
            override_raw("Borne basse (80 %)", ("color", {"mode": "fixed", "fixedColor": "gray"}),
                         ("custom.lineWidth", 1), ("custom.fillOpacity", 0)),
            override_raw("Borne haute (80 %)", ("color", {"mode": "fixed", "fixedColor": "gray"}),
                         ("custom.lineWidth", 1), ("custom.fillOpacity", 0)),
        ],
        options=TS_OPTIONS,
    )
    anomalies = """
SELECT snapshot_ts AS "Date", coin_id AS "Crypto", price_usd AS "Prix (USD)",
       return_pct AS "Rendement (%)", z_score AS "Z-score", direction AS "Sens"
FROM marts.fct_price_anomalies
WHERE is_anomaly AND $__timeFilter(snapshot_ts)
ORDER BY snapshot_ts DESC
LIMIT 50
"""
    table(
        d, "Anomalies detectees", (16, 34, 8, 9), PG, [sql(anomalies, fmt="table")],
        description="Rendement horaire dont le z-score depasse 3 par rapport aux 7 derniers jours.",
        overrides=[
            override("Prix (USD)", unit="currencyUSD", decimals=2),
            override("Rendement (%)", unit="percent", decimals=2, cell={"type": "color-text"},
                     thresholds=thresholds((RED, None), (GREEN, 0)), color={"mode": "thresholds"}),
        ],
    )

    d.row("Marche en temps reel", 43)
    live = """
SELECT DISTINCT ON (coin_id)
       coin_id AS "Crypto", upper(symbol) AS "Symbole", price_usd AS "Prix (USD)",
       pct_change_24h AS "Variation 24h", market_cap_usd AS "Capitalisation",
       volume_24h_usd AS "Volume 24h", high_24h_usd AS "Plus haut 24h",
       low_24h_usd AS "Plus bas 24h", snapshot_ts AS "Mis a jour"
FROM raw.prices
ORDER BY coin_id, snapshot_ts DESC
"""
    table(
        d, "Cotations des cryptomonnaies suivies", (0, 44, 24, 9), PG, [sql(live, fmt="table")],
        overrides=[
            override("Prix (USD)", unit="currencyUSD", decimals=2),
            override("Variation 24h", unit="percent", decimals=2, cell={"type": "color-background", "mode": "basic"},
                     thresholds=thresholds((RED, None), (GREEN, 0)), color={"mode": "thresholds"}),
            override("Capitalisation", unit="currencyUSD", decimals=0),
            override("Volume 24h", unit="currencyUSD", decimals=0),
            override("Plus haut 24h", unit="currencyUSD", decimals=2),
            override("Plus bas 24h", unit="currencyUSD", decimals=2),
        ],
    )
    d.write("cryptopulse-market.json")


# --------------------------------------------------------------------------- dashboard 2 : pipeline
def pipeline():
    d = Dash("cp-pipeline", "CryptoPulse : Pipeline et qualité", ["cryptopulse", "pipeline", "qualite"], "now-24h", "1m")

    d.row("Sante du pipeline", 0)
    stat(d, "Fraicheur des donnees", (0, 1, 4, 4), PROM, [prom("cryptopulse_freshness_age_hours", instant=True)],
         unit="h", decimals=1, graph="none", steps=[(GREEN, None), (ORANGE, 2), (RED, 3)],
         description="Age du dernier snapshot de prix. Alerte au-dela de 3 heures.")
    stat(d, "Controles qualite en echec", (4, 1, 4, 4), PROM,
         [prom("cryptopulse_quality_failed_checks", instant=True)], unit="short", decimals=0, graph="none",
         steps=[(GREEN, None), (RED, 1)], description="Controles en FAIL sur les 3 dernieres heures.")
    stat(d, "Lignes chargees (24 h)", (8, 1, 4, 4), PROM, [prom("cryptopulse_rows_last_24h", instant=True)],
         unit="short", decimals=0, graph="none", steps=[(BLUE, None)])
    stat(d, "Lignes totales (raw)", (12, 1, 4, 4), PROM, [prom("cryptopulse_rows_total", instant=True)],
         unit="short", decimals=0, graph="none", steps=[(BLUE, None)])
    stat(d, "Taches en echec (24 h)", (16, 1, 4, 4), PROM,
         [prom('sum(increase(airflow_task_finished_total{state="failed"}[24h])) or vector(0)', instant=True)],
         unit="short", decimals=0, graph="none", steps=[(GREEN, None), (RED, 1)])
    stat(d, "Alertes actives", (20, 1, 4, 4), PROM,
         [prom('count(ALERTS{alertstate="firing"}) or vector(0)', instant=True)],
         unit="short", decimals=0, graph="none", steps=[(GREEN, None), (ORANGE, 1), (RED, 3)])

    d.row("Airflow", 5)
    ts(d, "Taches terminees par etat (par heure)", (0, 6, 12, 8), PROM,
       [prom("sum by (state) (increase(airflow_task_finished_total[1h]))", "{{state}}")],
       unit="short", fill=60, stack="normal", style="bars", decimals=0)
    ts(d, "Duree moyenne des DAG runs", (12, 6, 12, 8), PROM,
       [prom("rate(airflow_dagrun_duration_seconds_sum[1h]) / rate(airflow_dagrun_duration_seconds_count[1h])",
             "{{dag_id}} ({{state}})")], unit="s", decimals=1)
    ts(d, "Duree moyenne par tache", (0, 14, 12, 8), PROM,
       [prom("avg by (task_id) (rate(airflow_task_duration_seconds_sum[1h]) / rate(airflow_task_duration_seconds_count[1h]))",
             "{{task_id}}")], unit="s", decimals=1, legend_table=True)
    ts(d, "Executor : slots et taches", (12, 14, 12, 8), PROM,
       [prom("airflow_executor_open_slots", "slots libres", ref="A"),
        prom("airflow_executor_running_tasks", "taches en cours", ref="B"),
        prom("airflow_executor_queued_tasks", "taches en file", ref="C")],
       unit="short", fill=8, decimals=0)

    d.row("Disponibilite des services", 22)
    stat(d, "Etat des sondes HTTP", (0, 23, 12, 6), PROM,
         [prom("probe_success", "{{instance}}", instant=True)], unit="short", graph="none",
         steps=[(RED, None), (GREEN, 1)], mappings=UP_DOWN_MAPPING, color="background", text="value_and_name")
    ts(d, "Temps de reponse des sondes", (12, 23, 12, 6), PROM,
       [prom("probe_duration_seconds", "{{instance}}")], unit="s", fill=5, decimals=3)

    d.row("Qualite des donnees", 29)
    quality = """
SELECT run_at AS "Date", check_name AS "Controle", status AS "Statut",
       metric AS "Metrique", details AS "Details"
FROM ops.quality_runs
ORDER BY run_at DESC
LIMIT 25
"""
    table(
        d, "Derniers controles qualite", (0, 30, 16, 9), PG, [sql(quality, fmt="table")],
        overrides=[override("Statut", cell={"type": "color-background", "mode": "basic"}, mappings=STATUS_MAPPING,
                            width=110)],
    )
    loads = """
SELECT date_trunc('day', loaded_at) AS time, count(*) AS "Lignes chargees"
FROM raw.prices
WHERE $__timeFilter(loaded_at)
GROUP BY 1
ORDER BY 1
"""
    ts(d, "Chargements par jour", (16, 30, 8, 9), PG, [sql(loads)], unit="short", fill=70, style="bars", decimals=0)

    fresh = """
SELECT coin_id AS "Crypto", last_snapshot_ts AS "Dernier snapshot",
       age_hours AS "Age (h)", snapshots_total AS "Snapshots"
FROM marts.dim_data_freshness
ORDER BY coin_id
"""
    table(
        d, "Fraicheur par crypto", (0, 39, 12, 7), PG, [sql(fresh, fmt="table")],
        overrides=[override("Age (h)", unit="h", decimals=2, cell={"type": "color-background", "mode": "basic"},
                            thresholds=thresholds((GREEN, None), (ORANGE, 2), (RED, 3)),
                            color={"mode": "thresholds"})],
    )
    table(
        d, "Alertes actives", (12, 39, 12, 7), PROM,
        [prom('ALERTS{alertstate="firing"}', instant=True, fmt="table")],
        description="Alertes Prometheus en cours. Le tableau est vide quand tout va bien.",
        transformations=[
            {"id": "organize", "options": {
                "excludeByName": {"Time": True, "Value": True, "__name__": True, "alertstate": True},
                "indexByName": {}, "renameByName": {"alertname": "Alerte", "severity": "Severite"}}},
        ],
    )
    d.row("Sauvegardes", 46)
    stat(d, "Derniere sauvegarde", (0, 47, 4, 4), PROM,
         [prom("(time() - cryptopulse_backup_last_success_timestamp_seconds) / 3600", instant=True)],
         unit="h", decimals=1, graph="none", steps=[(GREEN, None), (ORANGE, 26), (RED, 36)],
         description="Age de la derniere sauvegarde PostgreSQL envoyee dans le Data Lake. Alerte au-dela de 36 h.")
    stat(d, "Taille de la sauvegarde", (4, 47, 4, 4), PROM,
         [prom("cryptopulse_backup_size_bytes", instant=True)], unit="bytes", graph="none", steps=[(BLUE, None)])
    stat(d, "Dernier snapshot disque", (8, 47, 4, 4), PROM,
         [prom("(time() - cryptopulse_disk_snapshot_last_success_timestamp_seconds) / 86400", instant=True)],
         unit="d", decimals=1, graph="none", steps=[(GREEN, None), (ORANGE, 8), (RED, 10)],
         description="Age du dernier snapshot du disque de donnees (hebdomadaire).")
    stat(d, "Requetes API par minute", (12, 47, 4, 4), PROM,
         [prom("sum(rate(cryptopulse_api_requests_total[5m])) * 60 or vector(0)", instant=True)],
         unit="short", decimals=1, graph="area", steps=[(BLUE, None)])
    stat(d, "Latence API p95", (16, 47, 4, 4), PROM,
         [prom("histogram_quantile(0.95, sum by (le) (rate(cryptopulse_api_request_duration_seconds_bucket[5m])))",
               instant=True)],
         unit="s", decimals=3, graph="none", steps=[(GREEN, None), (ORANGE, 0.5), (RED, 2)])
    stat(d, "Erreurs API 5xx (1 h)", (20, 47, 4, 4), PROM,
         [prom('sum(increase(cryptopulse_api_requests_total{status=~"5.."}[1h])) or vector(0)', instant=True)],
         unit="short", decimals=0, graph="none", steps=[(GREEN, None), (RED, 1)])

    d.row("API de donnees", 51)
    ts(d, "Requetes par route et par statut", (0, 52, 12, 8), PROM,
       [prom("sum by (path, status) (rate(cryptopulse_api_requests_total[5m])) * 60", "{{path}} ({{status}})")],
       unit="short", fill=20, stack="normal", decimals=2)
    ts(d, "Latence p95 par route", (12, 52, 12, 8), PROM,
       [prom("histogram_quantile(0.95, sum by (le, path) (rate(cryptopulse_api_request_duration_seconds_bucket[5m])))",
             "{{path}}")], unit="s", fill=5, decimals=3)
    d.write("cryptopulse-pipeline.json")


# --------------------------------------------------------------------------- dashboard 3 : infrastructure
def infrastructure():
    d = Dash("cp-infra", "CryptoPulse : Infrastructure", ["cryptopulse", "infrastructure"], "now-6h", "30s")

    d.row("Machine virtuelle", 0)
    gauge(d, "CPU", (0, 1, 4, 5), PROM,
          [prom('100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)', instant=True)])
    gauge(d, "Memoire", (4, 1, 4, 5), PROM,
          [prom("(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100", instant=True)],
          steps=[(GREEN, None), (ORANGE, 75), (RED, 90)])
    gauge(d, "Swap", (8, 1, 4, 5), PROM,
          [prom("(1 - node_memory_SwapFree_bytes / node_memory_SwapTotal_bytes) * 100", instant=True)],
          steps=[(GREEN, None), (ORANGE, 30), (RED, 60)])
    gauge(d, "Disque /data", (12, 1, 4, 5), PROM,
          [prom('100 - (node_filesystem_avail_bytes{mountpoint="/data"} / node_filesystem_size_bytes{mountpoint="/data"} * 100)',
                instant=True)], steps=[(GREEN, None), (ORANGE, 70), (RED, 85)])
    gauge(d, "Disque /", (16, 1, 4, 5), PROM,
          [prom('100 - (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"} * 100)',
                instant=True)], steps=[(GREEN, None), (ORANGE, 70), (RED, 85)])
    stat(d, "Uptime", (20, 1, 4, 5), PROM, [prom("time() - node_boot_time_seconds", instant=True)],
         unit="s", graph="none", steps=[(BLUE, None)])

    ts(d, "CPU par mode", (0, 6, 12, 8), PROM,
       [prom('avg by (mode) (rate(node_cpu_seconds_total{mode!="idle"}[5m])) * 100', "{{mode}}")],
       unit="percent", fill=40, stack="normal", minimum=0, decimals=1)
    ts(d, "Charge systeme (load average)", (12, 6, 12, 8), PROM,
       [prom("node_load1", "1 min", ref="A"), prom("node_load5", "5 min", ref="B"),
        prom("node_load15", "15 min", ref="C")], unit="short", decimals=2)
    ts(d, "Memoire", (0, 14, 12, 8), PROM,
       [prom("node_memory_MemTotal_bytes", "total", ref="A"),
        prom("node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes", "utilisee", ref="B"),
        prom("node_memory_Cached_bytes", "cache", ref="C"),
        prom("node_memory_SwapTotal_bytes - node_memory_SwapFree_bytes", "swap utilise", ref="D")],
       unit="bytes", fill=10)
    ts(d, "Entrees et sorties disque", (12, 14, 12, 8), PROM,
       [prom('sum(rate(node_disk_read_bytes_total[5m]))', "lecture", ref="A"),
        prom('sum(rate(node_disk_written_bytes_total[5m]))', "ecriture", ref="B")], unit="Bps", fill=15)
    ts(d, "Reseau", (0, 22, 12, 8), PROM,
       [prom('sum(rate(node_network_receive_bytes_total{device!~"lo|docker.*|br-.*|veth.*"}[5m])) * 8', "reception", ref="A"),
        prom('sum(rate(node_network_transmit_bytes_total{device!~"lo|docker.*|br-.*|veth.*"}[5m])) * 8', "emission", ref="B")],
       unit="bps", fill=15)
    ts(d, "Occupation des disques", (12, 22, 12, 8), PROM,
       [prom('100 - (node_filesystem_avail_bytes{mountpoint=~"/|/data"} / node_filesystem_size_bytes{mountpoint=~"/|/data"} * 100)',
             "{{mountpoint}}")], unit="percent", fill=10, minimum=0, maximum=100, decimals=1)

    svc = 'container_label_com_docker_compose_service!=""'
    d.row("Conteneurs Docker", 30)
    ts(d, "CPU par service", (0, 31, 12, 8), PROM,
       [prom(f"sum by (container_label_com_docker_compose_service) (rate(container_cpu_usage_seconds_total{{{svc}}}[5m])) * 100",
             "{{container_label_com_docker_compose_service}}")],
       unit="percent", fill=15, legend_table=True, decimals=1)
    ts(d, "Memoire par service", (12, 31, 12, 8), PROM,
       [prom(f"sum by (container_label_com_docker_compose_service) (container_memory_working_set_bytes{{{svc}}})",
             "{{container_label_com_docker_compose_service}}")],
       unit="bytes", fill=15, legend_table=True)
    ts(d, "Trafic reseau par service", (0, 39, 12, 8), PROM,
       [prom(f"sum by (container_label_com_docker_compose_service) (rate(container_network_receive_bytes_total{{{svc}}}[5m]) + rate(container_network_transmit_bytes_total{{{svc}}}[5m]))",
             "{{container_label_com_docker_compose_service}}")], unit="Bps", fill=10)
    d.panel(
        "bargauge", "Anciennete des conteneurs", (12, 39, 12, 8), PROM,
        [prom(f"time() - max by (container_label_com_docker_compose_service) (container_start_time_seconds{{{svc}}})",
              "{{container_label_com_docker_compose_service}}", instant=True)],
        description="Temps depuis le dernier demarrage de chaque service. Une valeur faible indique un redemarrage recent.",
        defaults={"unit": "s", "min": 0, "color": {"mode": "thresholds"},
                  "thresholds": thresholds((RED, None), (ORANGE, 600), (GREEN, 3600))},
        options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                 "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                 "valueMode": "color", "namePlacement": "auto", "minVizHeight": 10, "minVizWidth": 0},
    )

    d.row("PostgreSQL", 47)
    stat(d, "Etat", (0, 48, 4, 4), PROM, [prom("pg_up", instant=True)], unit="short", graph="none",
         steps=[(RED, None), (GREEN, 1)], mappings=UP_DOWN_MAPPING, color="background")
    stat(d, "Taille de la base", (4, 48, 4, 4), PROM,
         [prom('pg_database_size_bytes{datname="cryptopulse"}', instant=True)], unit="bytes", graph="area",
         steps=[(BLUE, None)])
    stat(d, "Connexions", (8, 48, 4, 4), PROM, [prom("sum(pg_stat_activity_count)", instant=True)],
         unit="short", decimals=0, graph="area", steps=[(GREEN, None), (ORANGE, 60), (RED, 90)])
    stat(d, "Cache hit ratio", (12, 48, 4, 4), PROM,
         [prom('sum(pg_stat_database_blks_hit{datname="cryptopulse"}) / (sum(pg_stat_database_blks_hit{datname="cryptopulse"}) + sum(pg_stat_database_blks_read{datname="cryptopulse"})) * 100',
               instant=True)], unit="percent", decimals=1, graph="none",
         steps=[(RED, None), (ORANGE, 90), (GREEN, 99)])
    stat(d, "Verrous", (16, 48, 4, 4), PROM, [prom("sum(pg_locks_count)", instant=True)], unit="short",
         decimals=0, graph="area", steps=[(GREEN, None), (ORANGE, 50)])
    stat(d, "Transactions par seconde", (20, 48, 4, 4), PROM,
         [prom('sum(rate(pg_stat_database_xact_commit{datname="cryptopulse"}[5m]))', instant=True)],
         unit="ops", decimals=2, graph="area", steps=[(BLUE, None)])
    ts(d, "Connexions par etat", (0, 52, 12, 8), PROM,
       [prom("sum by (state) (pg_stat_activity_count)", "{{state}}")], unit="short", fill=30,
       stack="normal", decimals=0)
    ts(d, "Operations sur les lignes", (12, 52, 12, 8), PROM,
       [prom('sum(rate(pg_stat_database_tup_inserted{datname="cryptopulse"}[5m]))', "inserees", ref="A"),
        prom('sum(rate(pg_stat_database_tup_updated{datname="cryptopulse"}[5m]))', "mises a jour", ref="B"),
        prom('sum(rate(pg_stat_database_tup_deleted{datname="cryptopulse"}[5m]))', "supprimees", ref="C"),
        prom('sum(rate(pg_stat_database_tup_fetched{datname="cryptopulse"}[5m]))', "lues", ref="D")],
       unit="ops", fill=10, decimals=1)
    d.write("cryptopulse-infrastructure.json")


# --------------------------------------------------------------------------- dashboard 4 : sentiment
def sentiment_dashboard():
    d = Dash("cp-sentiment", "CryptoPulse : Sentiment", ["cryptopulse", "sentiment"], "now-30d", "5m",
             COIN_VARIABLES)

    d.row("Fear & Greed Index", 0)
    d.panel(
        "gauge", "Indice actuel", (0, 1, 6, 7), PG,
        [sql("SELECT value AS \"Indice\" FROM marts.fct_fear_greed ORDER BY fng_date DESC LIMIT 1", fmt="table")],
        description="0 correspond a une peur extreme, 100 a une avidite extreme (source : alternative.me).",
        defaults={"unit": "none", "min": 0, "max": 100, "decimals": 0, "color": {"mode": "thresholds"},
                  "thresholds": thresholds((RED, None), (ORANGE, 25), (YELLOW, 45), ("light-green", 55), (GREEN, 75))},
        options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False},
                 "showThresholdLabels": True, "showThresholdMarkers": True, "orientation": "auto"},
    )
    stat(d, "Classification", (6, 1, 6, 7), PG,
         [sql("SELECT classification AS \"Classification\" FROM marts.fct_fear_greed ORDER BY fng_date DESC LIMIT 1",
              fmt="table")],
         unit="none", graph="none", steps=[(BLUE, None)], text="value", color_mode="fixed")
    hist = """
SELECT fng_date::timestamp AS time, value AS "Indice", value_ma7 AS "Moyenne 7 jours"
FROM marts.fct_fear_greed
WHERE $__timeFilter(fng_date::timestamp)
ORDER BY 1
"""
    ts(d, "Evolution de l'indice", (12, 1, 12, 7), PG, [sql(hist)], unit="none", fill=10, minimum=0, maximum=100,
       decimals=0)

    d.row("Sentiment des actualites", 8)
    daily = """
SELECT published_date::timestamp AS time, coin_id AS metric, avg_sentiment AS value
FROM marts.fct_daily_sentiment
WHERE $__timeFilter(published_date::timestamp) AND coin_id IN ($coins)
ORDER BY 1
"""
    ts(d, "Sentiment moyen par crypto", (0, 9, 16, 8), PG, [sql(daily)], unit="none", fill=0, minimum=-1, maximum=1,
       decimals=2, legend_table=True,
       description="Score VADER moyen des titres et resumes d'articles, de -1 (tres negatif) a +1 (tres positif).")
    volume = """
SELECT coin_id AS "Crypto", sum(articles) AS "Articles"
FROM marts.fct_daily_sentiment
WHERE $__timeFilter(published_date::timestamp)
GROUP BY coin_id
ORDER BY 2 DESC
"""
    d.panel(
        "bargauge", "Articles par crypto", (16, 9, 8, 8), PG, [sql(volume, fmt="table")],
        defaults={"unit": "short", "min": 0, "color": {"mode": "palette-classic"}, "decimals": 0},
        options={"reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": True},
                 "orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                 "valueMode": "color", "namePlacement": "auto", "minVizHeight": 10, "minVizWidth": 0},
    )
    corr = """
SELECT d.price_date::timestamp AS time, d.close_usd AS "Cloture", s.avg_sentiment AS "Sentiment"
FROM marts.fct_daily_prices d
LEFT JOIN marts.fct_daily_sentiment s ON s.coin_id = d.coin_id AND s.published_date = d.price_date
WHERE d.coin_id = '${coin}' AND $__timeFilter(d.price_date::timestamp)
ORDER BY 1
"""
    d.panel(
        "timeseries", "Prix et sentiment", (0, 17, 24, 8), PG, [sql(corr)],
        description="Mise en regard du cours de cloture (axe de gauche) et du sentiment des actualites (axe de droite). "
                    "Une correlation visuelle n'implique pas une causalite.",
        defaults=ts_defaults("currencyUSD", fill=8),
        overrides=[override_raw("Sentiment", ("unit", "none"), ("custom.axisPlacement", "right"),
                                ("min", -1), ("max", 1), ("custom.drawStyle", "points"),
                                ("custom.showPoints", "always"), ("custom.pointSize", 8),
                                ("color", {"mode": "fixed", "fixedColor": "purple"}))],
        options=TS_OPTIONS,
    )

    d.row("Dernieres actualites", 25)
    news = """
SELECT published_at AS "Publie", coin_id AS "Crypto", source AS "Source", title AS "Titre",
       label AS "Sentiment", sentiment AS "Score", link AS "Lien"
FROM staging.stg_news
ORDER BY published_at DESC
LIMIT 50
"""
    table(
        d, "Titres recents et leur sentiment", (0, 26, 24, 11), PG, [sql(news, fmt="table")],
        description="Seuls le titre, le lien et le score sont conserves ; cliquez sur un titre pour ouvrir l'article.",
        overrides=[
            override("Sentiment", cell={"type": "color-text"}, mappings=[{
                "type": "value", "options": {
                    "positive": {"text": "positif", "color": "green", "index": 0},
                    "negative": {"text": "negatif", "color": "red", "index": 1},
                    "neutral": {"text": "neutre", "color": "text", "index": 2}}}]),
            override("Score", decimals=2),
            override_raw("Titre", ("links", [{"title": "Ouvrir l'article", "url": "${__data.fields.Lien}",
                                              "targetBlank": True}]), ("custom.width", 520)),
            override_raw("Lien", ("custom.hidden", True)),
        ],
    )
    d.write("cryptopulse-sentiment.json")


# --------------------------------------------------------------------------- dashboard 5 : logs
ERROR_REGEX = '(?i)(error|exception|traceback|critical)'


def logs_dashboard():
    variables = [
        {
            "name": "service", "label": "Service", "type": "query", "datasource": LOKI,
            "query": {"label": "service", "refId": "LokiVariableQueryEditor-VariableQuery", "stream": "", "type": 1},
            "definition": "", "refresh": 2, "sort": 1, "multi": True, "includeAll": True,
            "current": {"selected": True, "text": ["All"], "value": ["$__all"]},
        },
        {"name": "search", "label": "Recherche", "type": "textbox", "query": "",
         "current": {"selected": False, "text": "", "value": ""}},
    ]
    d = Dash("cp-logs", "CryptoPulse : Logs", ["cryptopulse", "logs"], "now-3h", "30s", variables)

    d.row("Vue d'ensemble", 0)
    stat(d, "Erreurs (1 h)", (0, 1, 6, 5), LOKI,
         [loki(f'sum(count_over_time({{service=~"$service"}} |~ "{ERROR_REGEX}" [1h]))', instant=True)],
         unit="short", decimals=0, graph="none", steps=[(GREEN, None), (ORANGE, 1), (RED, 20)],
         description="Lignes contenant error, exception, traceback ou critical sur la derniere heure.")
    stat(d, "Lignes de log (1 h)", (6, 1, 6, 5), LOKI,
         [loki('sum(count_over_time({service=~"$service"} [1h]))', instant=True)],
         unit="short", decimals=0, graph="none", steps=[(BLUE, None)])
    ts(d, "Volume de logs par service", (12, 1, 12, 5), LOKI,
       [loki('sum by (service) (count_over_time({service=~"$service"} [$__interval]))', "{{service}}")],
       unit="short", fill=50, stack="normal", style="bars", decimals=0)
    ts(d, "Erreurs par service", (0, 6, 24, 6), LOKI,
       [loki(f'sum by (service) (count_over_time({{service=~"$service"}} |~ "{ERROR_REGEX}" [$__interval]))',
             "{{service}}")], unit="short", fill=50, stack="normal", style="bars", decimals=0)

    d.row("Journaux", 12)
    d.panel(
        "logs", "Logs des conteneurs", (0, 13, 24, 16), LOKI,
        [loki('{service=~"$service"} |~ "(?i)$search"')],
        description="Utilisez la variable Recherche pour filtrer par mot, sans tenir compte de la casse.",
        options={"showTime": True, "showLabels": False, "showCommonLabels": False, "wrapLogMessage": True,
                 "prettifyLogMessage": False, "enableLogDetails": True, "dedupStrategy": "none",
                 "sortOrder": "Descending"},
    )
    d.write("cryptopulse-logs.json")


if __name__ == "__main__":
    market()
    pipeline()
    infrastructure()
    sentiment_dashboard()
    logs_dashboard()
    print(f"Dashboards generes dans {OUT}")
