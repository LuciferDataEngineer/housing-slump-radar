select
    locality,
    cast(year as integer) as year,
    cast(median_price as bigint) as median_price,
    cast(low_sample as integer) as low_sample
from {{ tidy('suburb_annual') }}
