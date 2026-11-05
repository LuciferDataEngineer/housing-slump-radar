with quarters as (
    select * from {{ ref('stg_suburb_median') }}
)
select
    current_quarter.locality,
    previous_quarter.median_price as price_2025_q1,
    current_quarter.median_price as price_2026_q1,
    current_quarter.sales as sales_2026_q1,
    round(100.0 * (current_quarter.median_price * 1.0 / previous_quarter.median_price - 1), 2) as yoy_pct
from quarters as current_quarter
join quarters as previous_quarter
  on current_quarter.locality = previous_quarter.locality
where current_quarter.quarter = '2026-Q1'
  and previous_quarter.quarter = '2025-Q1'
  and current_quarter.low_sample = 0
  and previous_quarter.low_sample = 0
  and current_quarter.median_price > 0
  and previous_quarter.median_price > 0
order by yoy_pct, current_quarter.locality
