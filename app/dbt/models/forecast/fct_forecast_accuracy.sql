-- Backtest : compare les previsions passees a la cloture reelle des jours termines.
with evaluated as (
    select
        f.coin_id,
        f.horizon_day,
        abs(d.close_usd - f.yhat) / nullif(d.close_usd, 0) * 100                  as abs_pct_error,
        (d.close_usd between f.yhat_lower and f.yhat_upper)                       as within_interval
    from {{ source('ops', 'forecast_history') }} f
    join {{ ref('fct_daily_prices') }} d
      on d.coin_id = f.coin_id
     and d.price_date = f.forecast_date
    where f.forecast_date < current_date
)

select
    coin_id || '|' || horizon_day::text                          as accuracy_key,
    coin_id,
    horizon_day,
    count(*)                                                     as evaluations,
    round(avg(abs_pct_error)::numeric, 3)                        as mape_pct,
    round((avg(within_interval::int) * 100)::numeric, 1)         as interval_hit_rate_pct
from evaluated
group by coin_id, horizon_day
