select
    cast(month_end as date) as month_end,
    cast(discounted_owner_occupier as double) as discounted_owner_occupier,
    cast(standard_owner_occupier as double) as standard_owner_occupier,
    cast(discounted_investor as double) as discounted_investor,
    cast(fixed_3y_owner_occupier as double) as fixed_3y_owner_occupier
from {{ tidy('lending_rates') }}
