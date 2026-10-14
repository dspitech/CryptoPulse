select
    coin_id || '|' || snapshot_ts::text         as price_key,
    coin_id,
    symbol,
    name,
    snapshot_ts,
    (snapshot_ts at time zone 'UTC')::date      as price_date,
    price_usd,
    market_cap_usd,
    volume_24h_usd,
    high_24h_usd,
    low_24h_usd,
    pct_change_24h
from {{ source('raw', 'prices') }}
where price_usd is not null
  and price_usd > 0
