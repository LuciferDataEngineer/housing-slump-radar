-- name: latest_geography_comparison
-- Compare total dwellings once per geography. AUS is a benchmark, not an extra state.
SELECT region, region_name, month, value AS approvals_original,
       ROUND(yoy_pct, 2) AS year_on_year_pct, trailing_12_month_total
FROM monthly_metrics
WHERE dwelling_type = 'Total (Type of Building)'
  AND month = (SELECT MAX(month) FROM current_observations)
ORDER BY value DESC;

-- name: national_annual_totals
-- One vintage and one non-overlapping category. Rolling annual counts overlap in time.
SELECT month, value, trailing_12_month_total, ROUND(yoy_pct, 2) AS year_on_year_pct
FROM monthly_metrics
WHERE region = 'AUS' AND dwelling_type = 'Total (Type of Building)'
ORDER BY month DESC LIMIT 12;

-- name: release_comparison_counts
-- Changed cells overlap across aggregate series and are not distinct dwelling counts.
SELECT release_period, edition, change_type, COUNT(*) AS cells
FROM release_changes
GROUP BY release_period, edition, change_type
ORDER BY release_period, edition, change_type;

-- name: national_total_revisions
SELECT release_period, edition, month, previous_value, value, change_value
FROM release_changes
WHERE region = 'AUS' AND dwelling_type = 'Total (Type of Building)'
  AND change_type = 'changed'
ORDER BY release_period, edition, month;

-- name: published_arithmetic_discrepancies
SELECT rule, month, region, dwelling_type, expected, actual, delta
FROM quality_findings
WHERE snapshot_id = (SELECT snapshot_id FROM snapshots ORDER BY release_period DESC, edition DESC LIMIT 1)
ORDER BY month, rule, region, dwelling_type;

-- name: immutable_release_inventory
SELECT release_period, edition, published_at AS announced_release_date,
       captured_at, row_count, first_month, last_month, source_sha256
FROM snapshots ORDER BY release_period, edition;

-- name: load_audit
SELECT operation, status, COALESCE(replayed, 0) AS replayed, COUNT(*) AS attempts
FROM pipeline_runs GROUP BY operation, status, COALESCE(replayed, 0)
ORDER BY operation, status, replayed;
