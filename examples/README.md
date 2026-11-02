# Captured outputs

These files were generated from the real August and September 2026 ABS Table 09 releases, retrieved on **2 November 2026**. They are not synthetic. The separate test fixture generator produces fictional data only.

- `report-2026-11-02.json`: September current-snapshot report after an identical replay; both archived releases remain in the warehouse.
- `sql-results-2026-11-02.json`: results of all seven named queries in `sql/analysis.sql`.
- `validation-2026-11-02.json`: observed counts, checksums, exact export comparisons, replay equality and runtime versions.

Source: Australian Bureau of Statistics, *Building Approvals, Australia*, August and September 2026, Table 09, accessed 2 November 2026. © Commonwealth of Australia. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Data reshaped and comparisons calculated by this project. The ABS has not endorsed these outputs. Exact source URLs and caveats are in [SOURCES.md](../docs/SOURCES.md).

The repository contains selected aggregate outputs, not raw workbooks, databases, local filesystem manifests or credentials. Reproduce the full exports with the README's live commands. Reference periods, run IDs and timestamps in newly generated outputs will reflect that new run.
