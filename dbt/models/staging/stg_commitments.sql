select
    quarter,
    region_code,
    region_name,
    housing_purpose,
    adjustment,
    cast(commitments as bigint) as commitments,
    cast(value_aud as bigint) as value_aud
from {{ tidy('loan_commitments') }}
