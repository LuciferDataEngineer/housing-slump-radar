select count(*) as suburbs_2025
from {{ ref('stg_suburb_annual') }}
where year = 2025 and low_sample = 0
having count(*) < 500
