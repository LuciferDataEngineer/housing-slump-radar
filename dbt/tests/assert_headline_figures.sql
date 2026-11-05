select *
from {{ ref('mart_overview') }}
where round(cash_rate_target, 2) <> 4.85
   or hikes_2026 <> 5
   or round(discounted_rate_published, 2) <> 6.80
   or round(discounted_rate_end_2025, 2) <> 6.05
   or loan_principal <> 727494
   or mean_price_australia <> 1100400
   or approvals_australia <> 18318
   or approvals_victoria <> 3918
   or august_revision <> 206
   or abs(scenario_rate - (discounted_rate_published + passthrough_gap_pp)) > 0.001
