"""Configuration lue depuis les variables d'environnement."""
from __future__ import annotations

import os
from dataclasses import dataclass

VS_CURRENCY = "usd"
API_URL = "https://api.coingecko.com/api/v3/coins/markets"
CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin}/market_chart"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

DEFAULT_NEWS_FEEDS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
)


@dataclass(frozen=True)
class Settings:
    coins: tuple[str, ...]
    pg_host: str
    pg_port: int
    pg_db: str
    pg_user: str
    pg_password: str
    storage_account: str = ""
    azure_client_id: str | None = None
    storage_connection_string: str | None = None
    freshness_max_hours: int = 3
    bronze_container: str = "bronze"
    silver_container: str = "silver"
    gold_container: str = "gold"
    news_feeds: tuple[str, ...] = DEFAULT_NEWS_FEEDS
    news_max_age_days: int = 3
    forecast_horizon_days: int = 7
    forecast_min_points: int = 21
    backfill_pause_seconds: float = 15.0

    @property
    def storage_url(self) -> str:
        return f"https://{self.storage_account}.blob.core.windows.net"


def get_settings() -> Settings:
    feeds = os.environ.get("NEWS_FEEDS", "")
    return Settings(
        coins=tuple(c.strip() for c in os.environ["COINS"].split(",") if c.strip()),
        pg_host=os.environ.get("POSTGRES_HOST", "postgres"),
        pg_port=int(os.environ.get("POSTGRES_PORT", "5432")),
        pg_db=os.environ.get("POSTGRES_DB", "cryptopulse"),
        pg_user=os.environ.get("POSTGRES_USER", "cryptopulse"),
        pg_password=os.environ["POSTGRES_PASSWORD"],
        storage_account=os.environ.get("STORAGE_ACCOUNT", ""),
        azure_client_id=os.environ.get("AZURE_CLIENT_ID") or None,
        storage_connection_string=os.environ.get("AZURE_STORAGE_CONNECTION_STRING") or None,
        freshness_max_hours=int(os.environ.get("FRESHNESS_MAX_HOURS", "3")),
        news_feeds=tuple(f.strip() for f in feeds.split(",") if f.strip()) or DEFAULT_NEWS_FEEDS,
        forecast_horizon_days=int(os.environ.get("FORECAST_HORIZON_DAYS", "7")),
        forecast_min_points=int(os.environ.get("FORECAST_MIN_POINTS", "21")),
        backfill_pause_seconds=float(os.environ.get("BACKFILL_PAUSE_SECONDS", "15")),
    )
