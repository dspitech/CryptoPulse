-- Echoue si une bougie journaliere est incoherente.
select *
from {{ ref('fct_daily_prices') }}
where high_usd < low_usd
   or close_usd > high_usd
   or close_usd < low_usd
   or open_usd  > high_usd
   or open_usd  < low_usd
