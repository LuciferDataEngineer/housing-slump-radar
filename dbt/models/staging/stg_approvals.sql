select
    vintage,
    series_id,
    region,
    dwelling_type,
    cast(month as date) as month,
    cast(value as integer) as value
from {{ tidy('building_approvals') }}
