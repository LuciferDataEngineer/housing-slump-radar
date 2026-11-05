select
    date_trunc('month', rate_date) as month_start,
    max(rate_date) as as_of,
    arg_max(cash_rate_target, rate_date) as cash_rate_target
from {{ ref('stg_cash_rate') }}
where rate_date >= date '2025-01-01'
group by 1
order by 1
