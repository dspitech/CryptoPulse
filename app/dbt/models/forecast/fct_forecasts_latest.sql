-- Derniere prevision generee pour chaque crypto et chaque date cible.
select distinct on (coin_id, forecast_date)
    coin_id,
    forecast_date,
    horizon_day,
    yhat::float8        as yhat,
    yhat_lower::float8  as yhat_lower,
    yhat_upper::float8  as yhat_upper,
    model,
    training_points,
    generated_on
from {{ source('ops', 'forecast_history') }}
order by coin_id, forecast_date, generated_on desc
