select
    fng_date,
    value,
    classification,
    round(avg(value) over (order by fng_date rows between 6 preceding and current row), 1) as value_ma7,
    value - lag(value) over (order by fng_date)                                           as change_1d
from {{ source('raw', 'fear_greed') }}
