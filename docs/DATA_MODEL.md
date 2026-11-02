# Database model and metrics

The warehouse is `DATA_DIR/warehouse.sqlite`. Schema version 1 is stored in SQLite's `PRAGMA user_version`. Foreign keys are enabled on application connections, with WAL mode and a 30-second busy timeout. A single pipeline process should own a data directory at a time.

## Tables

| Table | Grain and key | Important fields |
| --- | --- | --- |
| `pipeline_runs` | One ingest or report attempt; PK `run_id` | UTC start/finish timestamps, operation, requested release/edition, status, resulting snapshot, replay indicator and error |
| `source_artifacts` | One retained workbook per ingest attempt; PK/FK `run_id` | SHA-256, source URL, local raw path, byte size, UTC capture time |
| `snapshots` | One immutable release and local edition; PK `snapshot_id`, unique `(release_period, edition)` | Announced publication date, source digest/URL, capture time, row count, first/last month, originating run |
| `series` | One ABS series; PK `series_id`, unique `(region, dwelling_type)` | Geography code/name, dwelling type and expected description |
| `observations` | One snapshot × series × reference month; composite PK | Nonnegative integer `value`, measured in dwelling units approved |
| `quality_findings` | One failed arithmetic rule per snapshot/month/component | Rule name, geography/type, expected component sum, actual published total, signed difference |

`observations` has foreign keys to snapshots and series, plus an index on `(snapshot_id, month, series_id)`. Quality findings are indexed on `(snapshot_id, month)`. The release/edition unique index supports latest-snapshot selection. Counts are bounded at the parser to avoid numeric overflow; source fractions, blanks, booleans, formulas, infinities and negative values are rejected.

## Time and identity

| Field | Meaning |
| --- | --- |
| `month` | Reference month, stored as the first day in `YYYY-MM-DD` format |
| `release_period` | The month named by the publication, `YYYY-MM`; not the publication date |
| `published_at` | Announced release date supplied by the operator, `YYYY-MM-DD` |
| `edition` | Positive local version number for a different source file under the same release period; not an ABS-assigned edition |
| `captured_at` | Actual UTC capture time of the bytes ingested |

This is a release comparison database, **not a reconstruction of information available at a historical timestamp**. The publication date does not prove when these exact archived bytes first appeared. Different bytes require a separate edition even if they decode to the same values. Edition numbers express operator-verified ordering; a larger number must not be assigned blindly to an older copy.

## Views and metric dictionary

`current_observations` selects the entire snapshot with the greatest `(release_period, edition)`. It includes typed observations, geography/type and source date metadata. A late older snapshot does not displace it.

`monthly_metrics` derives all comparisons within that single snapshot:

| Metric | Definition and guard |
| --- | --- |
| `value` | Published original count; no seasonal adjustment or recomputation of published totals |
| `prior_year_value` | Same series exactly 12 calendar months earlier, otherwise null |
| `yoy_pct` | `100 × (value − prior_year_value) / prior_year_value`; null when the baseline is missing or zero |
| `trailing_12_month_total` | Sum of the current and prior 11 observations, only when there are 12 rows and the earliest is exactly 11 months earlier |

`yoy_pct` compares a single month with the same month a year earlier. It is not the percentage change in rolling annual totals. Adjacent rolling annual totals overlap in 11 months and must not be summed together.

`release_changes` compares each snapshot to the chronologically preceding stored snapshot, ordered by release period and local edition. It includes a `previous_snapshot_id`, same-key previous value, signed count difference where both values exist, and a change type. A first snapshot is a baseline; a later unmatched key is a new observation; identical/different matched values are unchanged/changed. Comparisons depend on the snapshots actually loaded: a backfill can change which stored snapshot is the predecessor, without modifying any source observations.

A key present only in the predecessor is `removed_observation`: its current `value` and `change_value` are null, while its `previous_value` is preserved. This makes shortened source histories visible without pretending that a missing observation has become zero. A revision export can therefore contain more rows than the current snapshot.

These tables intentionally contain overlapping aggregates. Do not sum Australia and its state components, or total dwellings and its component dwelling types. Changed-cell counts likewise include affected component and aggregate series.

## Quality rules

Structural checks are blocking: the exact 27 known series and their metadata must exist, all series must share a complete contiguous monthly range ending at the requested release month, and observation counts must agree with workbook metadata.

Two arithmetic rules are nonblocking: `houses_plus_other_equals_total` and `states_sum_to_australia`. `expected` is the sum of components, `actual` is the published total, and `delta = actual − expected`. They flag a source inconsistency; they do not diagnose its cause or correct it. No tolerance is applied to these original integer counts. The two inspected files each contain 36 findings, all for November 2010 or earlier.
