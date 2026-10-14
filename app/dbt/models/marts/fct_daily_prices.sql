with ranked as (
    select
        *,
        row_number() over (partition by coin_id, price_date order by snapshot_ts)      as rn_first,
        row_number() over (partition by coin_id, price_date order by snapshot_ts desc) as rn_last
    from {{ ref('stg_prices') }}
),

daily as (
    select
        coin_id,
        price_date,
        max(price_usd) filter (where rn_first = 1)      as open_usd,
        max(price_usd)                                  as high_usd,
        min(price_usd)                                  as low_usd,
        max(price_usd) filter (where rn_last = 1)       as close_usd,
        round(avg(price_usd), 6)                        as avg_usd,
        count(*)                                        as snapshots,
        max(market_cap_usd) filter (where rn_last = 1)  as market_cap_usd,
        max(volume_24h_usd) filter (where rn_last = 1)  as volume_24h_usd
    from ranked
    group by coin_id, price_date
)

select
    daily.coin_id || '|' || daily.price_date::text as daily_key,
    daily.coin_id,
    coins.symbol,
    daily.price_date,
    daily.open_usd,
    daily.high_usd,
    daily.low_usd,
    daily.close_usd,
    daily.avg_usd,
    daily.snapshots,
    daily.market_cap_usd,
    daily.volume_24h_usd
from daily
left join {{ ref('dim_coins') }} as coins using (coin_id)
