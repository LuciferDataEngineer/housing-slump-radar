select
    cast(date as date) as rate_date,
    cast(cash_rate_target as double) as cash_rate_target
from {{ tidy('cash_rate') }}
