select
    coin_id,
    max(symbol)         as symbol,
    max(name)           as name,
    min(snapshot_ts)    as first_seen_at,
    max(snapshot_ts)    as last_seen_at
from {{ ref('stg_prices') }}
group by coin_id
