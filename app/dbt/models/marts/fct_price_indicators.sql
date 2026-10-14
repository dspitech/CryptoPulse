with daily as (
    select * from {{ ref('fct_daily_prices') }}
),

returns as (
    select
        *,
        close_usd / nullif(lag(close_usd) over (partition by coin_id order by price_date), 0) - 1
            as daily_return
    from daily
)

select
    daily_key,
    coin_id,
    symbol,
    price_date,
    close_usd,
    case when count(close_usd) over w7 = 7 then avg(close_usd) over w7 end    as ma_7d,
    case when count(close_usd) over w30 = 30 then avg(close_usd) over w30 end as ma_30d,
    round((daily_return * 100)::numeric, 4)                                   as pct_change_1d,
    case when count(daily_return) over w7 = 7 then stddev_samp(daily_return) over w7 end
        as volatility_7d
from returns
window
    w7  as (partition by coin_id order by price_date rows between 6 preceding and current row),
    w30 as (partition by coin_id order by price_date rows between 29 preceding and current row)
