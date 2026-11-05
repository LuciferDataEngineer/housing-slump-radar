with totals as (
    select vintage, region, month, value
    from {{ ref('stg_approvals') }}
    where dwelling_type = 'Total (Type of Building)'
      and vintage = (select max(vintage) from {{ ref('stg_approvals') }})
)
select
    current_month.region,
    current_month.month,
    current_month.value as approvals,
    year_ago.value as approvals_year_ago,
    current_month.value - year_ago.value as change_count,
    round(100.0 * (current_month.value * 1.0 / year_ago.value - 1), 2) as yoy_pct
from totals as current_month
join totals as year_ago
  on current_month.region = year_ago.region
 and year_ago.month = current_month.month - interval 1 year
where current_month.month = (select max(month) from totals)
order by current_month.region
