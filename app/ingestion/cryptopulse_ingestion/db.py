"""Schemas et tables du warehouse, crees de facon idempotente."""
from __future__ import annotations

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS marts;

CREATE TABLE IF NOT EXISTS raw.prices (
    coin_id         text        NOT NULL,
    symbol          text,
    name            text,
    snapshot_ts     timestamptz NOT NULL,
    price_usd       numeric,
    market_cap_usd  numeric,
    volume_24h_usd  numeric,
    high_24h_usd    numeric,
    low_24h_usd     numeric,
    pct_change_24h  numeric,
    source_file     text        NOT NULL,
    loaded_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (coin_id, snapshot_ts)
);

CREATE TABLE IF NOT EXISTS raw.news_sentiment (
    link         text        NOT NULL,
    coin_id      text        NOT NULL,
    published_at timestamptz NOT NULL,
    source       text        NOT NULL,
    title        text        NOT NULL,
    sentiment    numeric     NOT NULL,
    label        text        NOT NULL,
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (link, coin_id)
);

CREATE TABLE IF NOT EXISTS raw.fear_greed (
    fng_date       date        PRIMARY KEY,
    value          integer     NOT NULL,
    classification text        NOT NULL,
    loaded_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ops.quality_runs (
    id         bigserial   PRIMARY KEY,
    run_id     text        NOT NULL,
    run_at     timestamptz NOT NULL DEFAULT now(),
    check_name text        NOT NULL,
    metric     numeric,
    status     text        NOT NULL,
    details    text
);

CREATE TABLE IF NOT EXISTS ops.forecast_history (
    coin_id         text    NOT NULL,
    forecast_date   date    NOT NULL,
    generated_on    date    NOT NULL,
    horizon_day     integer NOT NULL,
    yhat            numeric NOT NULL,
    yhat_lower      numeric NOT NULL,
    yhat_upper      numeric NOT NULL,
    model           text    NOT NULL,
    training_points integer NOT NULL,
    generated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (coin_id, forecast_date, generated_on)
);
"""


def ensure_schema(cur) -> None:
    cur.execute(DDL)
