-- Detection d'anomalies : z-score du rendement horaire par rapport aux 7 derniers jours.
-- Un rendement n'est calcule que si l'ecart avec le snapshot precedent est inferieur a
-- 3 heures, pour ne pas confondre une interruption de la VM avec une anomalie de marche.
with base as (
    select
        coin_id,
        snapshot_ts,
        price_usd,
        case
            when snapshot_ts - lag(snapshot_ts) over w <= interval '3 hours'
            then price_usd / nullif(lag(price_usd) over w, 0) - 1
        end as ret
    from {{ ref('stg_prices') }}
    window w as (partition by coin_id order by snapshot_ts)
),

stats as (
    select
        *,
        avg(ret)         over h as mean_ret,
        stddev_samp(ret) over h as std_ret,
        count(ret)       over h as n_obs
    from base
    window h as (partition by coin_id order by snapshot_ts rows between 168 preceding and 1 preceding)
)

select
    coin_id || '|' || snapshot_ts::text                                   as anomaly_key,
    coin_id,
    snapshot_ts,
    price_usd,
    round((ret * 100)::numeric, 4)                                        as return_pct,
    round(((ret - mean_ret) / nullif(std_ret, 0))::numeric, 3)            as z_score,
    coalesce(
        n_obs >= 24
        and std_ret > 0
        and abs((ret - mean_ret) / std_ret) >= {{ var('anomaly_z_threshold') }},
        false
    )                                                                     as is_anomaly,
    case when ret > 0 then 'hausse' when ret < 0 then 'baisse' else 'stable' end as direction
from stats
where ret is not null
