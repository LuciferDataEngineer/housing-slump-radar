select
    locality,
    quarter,
    cast(median_price as bigint) as median_price,
    try_cast(cast(sales as varchar) as bigint) as sales,
    cast(low_sample as integer) as low_sample
from {{ tidy('suburb_median') }}
