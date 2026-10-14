-- Echoue si une valeur Fear & Greed sort de l'intervalle 0 a 100.
select * from {{ ref('fct_fear_greed') }} where value < 0 or value > 100
