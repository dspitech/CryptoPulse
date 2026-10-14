{{ config(materialized='view', schema='staging') }}

select
    link || '|' || coin_id                          as news_key,
    link,
    coin_id,
    source,
    title,
    published_at,
    (published_at at time zone 'UTC')::date         as published_date,
    sentiment::float8                               as sentiment,
    label
from {{ source('raw', 'news_sentiment') }}
