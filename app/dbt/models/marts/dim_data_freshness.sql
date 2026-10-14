select
    coin_id,
    max(snapshot_ts)                                                         as last_snapshot_ts,
    round((extract(epoch from (now() - max(snapshot_ts))) / 3600)::numeric, 2) as age_hours,
    count(*)                                                                 as snapshots_total
from {{ ref('stg_prices') }}
group by coin_id
