with cash_now as (
    select rate_date, round(cash_rate_target, 2) as cash_rate_target
    from {{ ref('stg_cash_rate') }}
    order by rate_date desc
    limit 1
),
cash_end_2025 as (
    select round(cash_rate_target, 2) as cash_rate_target
    from {{ ref('stg_cash_rate') }}
    where rate_date = (
        select max(rate_date) from {{ ref('stg_cash_rate') }} where rate_date <= date '2025-12-31'
    )
),
hikes as (
    select count(*) as hikes_2026
    from {{ ref('mart_cash_decisions') }}
    where rate_date >= date '2026-01-01'
      and rate_date < date '2027-01-01'
      and change_pp > 0
),
lending as (
    select
        month_end,
        round(discounted_owner_occupier, 2) as rate,
        lag(round(discounted_owner_occupier, 2)) over (order by month_end) as previous_rate
    from {{ ref('stg_lending_rates') }}
),
last_increase as (
    select month_end, rate
    from lending
    where previous_rate is not null and rate > previous_rate
    order by month_end desc
    limit 1
),
published as (
    select month_end, rate as discounted_rate_published
    from lending
    order by month_end desc
    limit 1
),
rate_dec_2025 as (
    select rate as discounted_rate_end_2025
    from lending
    where month_end = date '2025-12-31'
),
cash_at_increase as (
    select round(cash_rate_target, 2) as cash_rate_target
    from {{ ref('stg_cash_rate') }}
    where rate_date = (
        select max(rate_date)
        from {{ ref('stg_cash_rate') }}
        where rate_date <= (select month_end from last_increase)
    )
),
loan as (
    select
        quarter as loan_quarter,
        cast(round(value_aud * 1.0 / commitments, 0) as bigint) as loan_principal
    from {{ ref('stg_commitments') }}
    where region_code = 'AUS'
      and housing_purpose = 'total'
      and adjustment = 'seasonally_adjusted'
    order by quarter desc
    limit 1
),
prices as (
    select mean_price_aud, quarter, qoq_pct, yoy_pct, versus_peak_pct
    from {{ ref('mart_state_prices') }}
    where region_code = 'AUS'
),
approvals as (
    select
        any_value(month) as approvals_month,
        max(case when region = 'Australia' then approvals end) as approvals_australia,
        max(case when region = 'Australia' then yoy_pct end) as approvals_australia_yoy_pct,
        max(case when region = 'Victoria' then approvals end) as approvals_victoria,
        max(case when region = 'Victoria' then approvals_year_ago end) as approvals_victoria_year_ago,
        max(case when region = 'Victoria' then yoy_pct end) as approvals_victoria_yoy_pct
    from {{ ref('mart_approval_yoy') }}
),
revision as (
    select september.value - august.value as august_revision
    from {{ ref('stg_approvals') }} as september
    join {{ ref('stg_approvals') }} as august
      on september.month = august.month
     and september.region = august.region
     and september.dwelling_type = august.dwelling_type
    where september.vintage = '2026-09'
      and august.vintage = '2026-08'
      and september.region = 'Australia'
      and september.dwelling_type = 'Total (Type of Building)'
      and september.month = date '2026-08-01'
),
commitments as (
    select
        current_quarter.quarter as commitments_quarter,
        current_quarter.commitments as commitments_number,
        round(100.0 * (current_quarter.commitments * 1.0 / year_ago.commitments - 1), 2) as commitments_yoy_pct
    from {{ ref('stg_commitments') }} as current_quarter
    join {{ ref('stg_commitments') }} as year_ago
      on year_ago.region_code = current_quarter.region_code
     and year_ago.housing_purpose = current_quarter.housing_purpose
     and year_ago.adjustment = current_quarter.adjustment
     and year_ago.quarter = '2025-Q2'
    where current_quarter.region_code = 'AUS'
      and current_quarter.housing_purpose = 'total'
      and current_quarter.adjustment = 'seasonally_adjusted'
      and current_quarter.quarter = '2026-Q2'
),
suburbs as (
    select
        count(*) as suburbs_compared,
        count(*) filter (where yoy_pct < 0) as suburbs_down,
        count(*) filter (where yoy_pct <= -5) as suburbs_act,
        round(median(yoy_pct), 2) as suburb_median_yoy_pct
    from {{ ref('mart_suburb_risk') }}
),
rates as (
    select
        cash_now.rate_date as cash_rate_date,
        cash_now.cash_rate_target,
        cash_end_2025.cash_rate_target as cash_rate_end_2025,
        rate_dec_2025.discounted_rate_end_2025,
        published.discounted_rate_published,
        published.month_end as discounted_rate_month,
        last_increase.month_end as lending_rate_last_increased,
        round(cash_now.cash_rate_target - cash_at_increase.cash_rate_target, 2) as passthrough_gap_pp,
        round(published.discounted_rate_published + (cash_now.cash_rate_target - cash_at_increase.cash_rate_target), 2) as scenario_rate
    from cash_now
    cross join cash_end_2025
    cross join rate_dec_2025
    cross join published
    cross join last_increase
    cross join cash_at_increase
)
select
    rates.cash_rate_date,
    rates.cash_rate_target,
    hikes.hikes_2026,
    rates.cash_rate_end_2025,
    rates.discounted_rate_end_2025,
    rates.discounted_rate_published,
    rates.discounted_rate_month,
    rates.lending_rate_last_increased,
    rates.passthrough_gap_pp,
    rates.scenario_rate,
    loan.loan_principal,
    loan.loan_quarter,
    round(loan.loan_principal * ((rates.discounted_rate_end_2025 / 100.0) / 12.0) * pow(1 + ((rates.discounted_rate_end_2025 / 100.0) / 12.0), 360) / (pow(1 + ((rates.discounted_rate_end_2025 / 100.0) / 12.0), 360) - 1), 2) as repayment_end_2025,
    round(loan.loan_principal * ((rates.discounted_rate_published / 100.0) / 12.0) * pow(1 + ((rates.discounted_rate_published / 100.0) / 12.0), 360) / (pow(1 + ((rates.discounted_rate_published / 100.0) / 12.0), 360) - 1), 2) as repayment_published,
    round(loan.loan_principal * ((rates.scenario_rate / 100.0) / 12.0) * pow(1 + ((rates.scenario_rate / 100.0) / 12.0), 360) / (pow(1 + ((rates.scenario_rate / 100.0) / 12.0), 360) - 1), 2) as repayment_scenario,
    prices.mean_price_aud as mean_price_australia,
    prices.quarter as mean_price_quarter,
    prices.qoq_pct as mean_price_qoq_pct,
    prices.yoy_pct as mean_price_yoy_pct,
    prices.versus_peak_pct as mean_price_versus_peak_pct,
    approvals.approvals_month,
    approvals.approvals_australia,
    approvals.approvals_australia_yoy_pct,
    approvals.approvals_victoria,
    approvals.approvals_victoria_year_ago,
    approvals.approvals_victoria_yoy_pct,
    revision.august_revision,
    commitments.commitments_quarter,
    commitments.commitments_number,
    commitments.commitments_yoy_pct,
    suburbs.suburbs_compared,
    suburbs.suburbs_down,
    suburbs.suburbs_act,
    suburbs.suburb_median_yoy_pct
from rates
cross join hikes
cross join loan
cross join prices
cross join approvals
cross join revision
cross join commitments
cross join suburbs
