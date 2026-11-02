# Observed validation

Verified on **2 November 2026** using the installed package, Python **3.14.7**, SQLite **3.53.4** and openpyxl **3.1.5**. These are observed local results, not estimated production performance.

## Deterministic suite

```bash
python -m pip install .
python -W error::ResourceWarning -m unittest discover -s tests -v
```

**22 tests passed.** The final observed suite took 2.688 seconds locally; timings depend on the machine. Tests import the installed package and generate fictional workbooks in temporary directories. They do not contact the ABS.

Coverage includes exact-byte replay, immutable conflicts, explicit replacement editions, late backfills, new/revised/removed observations, strict series metadata, duplicate/missing months, incomplete workbooks, invalid numeric values, source checksums, preserved arithmetic warnings, null zero-baseline growth, twelve-month windows, database integrity, CSV/JSON equivalence and recovery after failed exports.

One test installs an SQLite trigger that fails after ten observation inserts and confirms the entire new snapshot rolls back. Another commits a newer edition through a second connection during export and confirms one output generation retains a consistent read snapshot. This does not remove the requirement to serialize complete runners: concurrent output pointers can still finish out of order.

GitHub Actions runs the same offline suite on Python 3.11 and 3.14. Remote results are visible in the [CI workflow](https://github.com/LuciferDataEngineer/housing-slump-radar/actions/workflows/ci.yml); they are separate from the local results above. The live source is not downloaded by CI.

## Live smoke test

The installed CLI fetched both official workbooks and loaded them successfully:

```bash
housing-radar fetch --release-period 2026-08 --published-at 2026-09-30 --data-dir data/live
housing-radar fetch --release-period 2026-09 --published-at 2026-11-02 --data-dir data/live
python scripts/run_queries.py data/live/warehouse.sqlite --output examples/sql-results-2026-11-02.json
```

| Check | Observed result |
| --- | --- |
| August snapshot | 13,986 observations, 518 months × 27 series |
| September snapshot | 14,013 observations, 519 months × 27 series |
| Both snapshots retained | 27,999 observations |
| Changed shared cells | 120 |
| New September cells | 27 |
| Unchanged shared cells | 13,866 |
| Arithmetic quality findings | 36 per snapshot; zero in the latest 12 reference months |
| Identical September replay | Business-table hash unchanged; no extra snapshot or facts |
| SQLite integrity / foreign keys | `ok` / zero violations |
| Exact CSV-to-SQL comparison | All rows match in all three exports |
| Latest trailing annual totals | All 27 independently recomputed from the underlying observations |
| Named SQL examples | All 7 executed successfully |
| Documented synthetic CLI demo | 648 fictional observations loaded; zero quality findings |

Hashes and machine-readable verification are in [validation-2026-11-02.json](../examples/validation-2026-11-02.json). The identical replay digest covers ordered rows in `snapshots`, `series`, `observations` and `quality_findings`. Audits and raw capture records intentionally change on replay and are excluded from that business-state check.

The three exact export comparisons covered 14,013 monthly metric rows, 14,013 release comparison rows and 36 quality findings. Nulls were compared as empty CSV fields, with the complete header and row order included. The source workbook hashes also match the independent download checks in [SOURCES.md](SOURCES.md).

## Interpretable sample results

Within the September vintage, Australia's original September total is **18,318 approvals**, with **208,219** over the twelve months ending September. Its same-month year-on-year change is **−1.69%**. Victoria's corresponding original monthly count is **3,918**, and its trailing annual total is **55,440**. These are unadjusted approvals, not completed homes or price changes.

The August observation for Australia's total changes from **16,968** in the August archive to **17,174** in the September archive: a **+206** revision to the same reference month. That is a concrete reason to preserve vintages rather than overwrite the old value. The 120 changed cells include overlapping component and aggregate series and must not be summed as distinct dwelling approvals.

Read the [captured report](../examples/report-2026-11-02.json) and [query outputs](../examples/sql-results-2026-11-02.json). They are real, dated outputs. Source: ABS, Building Approvals, Australia, August/September 2026 Table 09; accessed 2 November 2026; transformed by this project under CC BY 4.0.

## Limits of the checks

Two successful bounded downloads do not establish ongoing source availability. Historical arithmetic findings remain unresolved source differences. These snapshots were retrieved now and do not prove the exact information available on the original publication dates. No hosted service, dashboard, scheduler, multi-writer deployment, disaster-recovery SLA or large-scale performance benchmark was tested.
