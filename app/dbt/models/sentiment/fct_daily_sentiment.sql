select
    coin_id || '|' || published_date::text                      as sentiment_key,
    coin_id,
    published_date,
    count(*)                                                    as articles,
    round(avg(sentiment)::numeric, 4)                           as avg_sentiment,
    count(*) filter (where label = 'positive')                  as positive_articles,
    count(*) filter (where label = 'negative')                  as negative_articles,
    count(*) filter (where label = 'neutral')                   as neutral_articles
from {{ ref('stg_news') }}
group by coin_id, published_date
