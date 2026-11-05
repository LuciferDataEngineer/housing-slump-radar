with ordered as (
    select
        region_code,
        region_name,
        quarter,
        mean_price_aud,
        lag(mean_price_aud) over (partition by region_code order by quarter) as previous_price,
        lag(mean_price_aud, 4) over (partition by region_code order by quarter) as price_year_ago,
        max(mean_price_aud) over (partition by region_code) as peak_price
    from {{ ref('stg_mean_price') }}
),
latest as (
    select * from ordered
    qualify row_number() over (partition by region_code order by quarter desc) = 1
)
select
    region_code,
    region_name,
    quarter,
    mean_price_aud,
    round(100.0 * (mean_price_aud * 1.0 / previous_price - 1), 2) as qoq_pct,
    round(100.0 * (mean_price_aud * 1.0 / price_year_ago - 1), 2) as yoy_pct,
    peak_price,
    round(100.0 * (mean_price_aud * 1.0 / peak_price - 1), 2) as versus_peak_pct
from latest
order by region_name
