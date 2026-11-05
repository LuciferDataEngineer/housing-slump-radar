with ordered as (
    select
        rate_date,
        cash_rate_target,
        lag(cash_rate_target) over (order by rate_date) as previous_target
    from {{ ref('stg_cash_rate') }}
)
select
    rate_date,
    round(cash_rate_target, 2) as cash_rate_target,
    round(previous_target, 2) as previous_target,
    round(cash_rate_target - previous_target, 2) as change_pp
from ordered
where previous_target is not null
  and round(cash_rate_target, 2) <> round(previous_target, 2)
order by rate_date
