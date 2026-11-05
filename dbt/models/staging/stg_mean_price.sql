select
    region_code,
    region_name,
    quarter,
    cast(mean_price_aud as bigint) as mean_price_aud,
    cast(dwelling_count as bigint) as dwelling_count,
    cast(stock_value_aud as bigint) as stock_value_aud
from {{ tidy('mean_dwelling_price') }}
