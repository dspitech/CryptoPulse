select distinct on (p.coin_id)
    p.coin_id,
    c.symbol,
    c.name,
    p.snapshot_ts,
    p.price_usd,
    p.market_cap_usd,
    p.volume_24h_usd,
    p.high_24h_usd,
    p.low_24h_usd,
    p.pct_change_24h
from {{ ref('stg_prices') }} p
left join {{ ref('dim_coins') }} c using (coin_id)
order by p.coin_id, p.snapshot_ts desc
