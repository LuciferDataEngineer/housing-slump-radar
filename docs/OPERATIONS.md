# Running and recovering the pipeline

## Operating contract

Use **one pipeline process per data directory**. SQLite provides transactional writes and each export uses a consistent read transaction, but two concurrent export processes could finish out of order and replace `latest.json` with an older generation. Serialize runs in any scheduler. Read-only SQL clients can query the warehouse concurrently.

The downloader requests a release-specific official ABS URL. It does not substitute another edition or fall back to a synthetic sample when a source is unavailable. Limits are 12 MiB compressed, 80 MiB expanded XLSX content, 200 ZIP entries and 2,000 observation months. HTTP requests use a 45-second socket timeout, with at most three attempts on transient network errors, HTTP 429 or server errors. These bounds are not a strict end-to-end wall-clock deadline. `Content-Length`, when supplied, must match the bytes received.

CLI results are JSON on standard output; progress and errors go to standard error. Ingestion attempts and report operations are audited in SQLite. **Download and argument failures before ingestion are not database-audited**: retain the CLI error in your scheduler's logs. Database-initialization failures may likewise precede creation of a run record.

## Local layout

```text
data/
  warehouse.sqlite            # validated snapshots, source references and audits
  downloads/                  # fetched XLSX files; failed downloads may be partial
  raw/<run_id>/
    8731009.xlsx               # exact bytes retained for this ingestion attempt
    manifest.json             # source, SHA-256, size, capture and release metadata
  exports/
    latest.json               # pointer to the last fully written generation
    <run_id>/
      report.json
      monthly_metrics.csv
      release_changes.csv
      quality_findings.csv
```

Follow the pointer rather than choosing the newest directory name. A failed export can leave an incomplete unreferenced directory. CSV empty fields correspond to SQL nulls. Raw manifests include local absolute paths and are intentionally ignored by Git.

## Regular release load

Verify the release's date and the correct Table 09 URL on the ABS website. Then run, for example:

```bash
housing-radar fetch --release-period 2026-09 --published-at 2026-11-02 --data-dir data
python scripts/run_queries.py data/warehouse.sqlite
```

The release period is not the publication month. `--published-at` documents the announced date; the application cannot independently authenticate a supplied publication date. Each input must end at the requested reference month and pass the workbook contract.

Inspect the report's release period, latest reference month, source digest, quality counts and revision counts. The observed historical arithmetic discrepancies are preserved, not patched. If an unexpected new warning appears, inspect its source cell and document the interpretation before relying on an affected total.

## Recovery cases

| Situation | Behaviour | Recovery |
| --- | --- | --- |
| HTTP error, timeout or partial download | Command fails before ingestion; no new business snapshot | Inspect stderr, retry the same explicit release later; do not ingest a partial download |
| Invalid workbook or changed schema | Ingest fails, retains copied bytes and failure audit where available; business tables unchanged | Check the publisher's file and metadata. Update the parser contract intentionally with tests |
| Identical release/edition replay | Existing business snapshot remains unchanged; a new audit and output generation are created | Safe to rerun using the same bytes and publication date |
| Different bytes for an existing release/edition | Rejected, without overwriting history | Compare both files. For a verified replacement, use `--edition 2` (or the next unused local edition) |
| Mid-transaction database error | Entire new business snapshot rolls back | Resolve the write/space/locking issue and retry the same input |
| Database commit followed by export failure | Snapshot survives; audit records failure and committed snapshot; previous output pointer remains until a complete new export is written | Repair output permissions/space, then run `housing-radar report --data-dir data`, or replay the identical input |
| Process killed mid-run | SQLite rolls back uncommitted writes; an audit can remain `running` and files may be incomplete | Confirm no process still owns the run, inspect snapshots and pointer, then replay. No automatic stale-run repair is implemented |
| Older release arrives later | Stored as history; latest release remains current | No special repair. Revision comparisons recalculate against the loaded predecessor set |

Example of an intentional replacement after inspecting changed publisher bytes:

```bash
housing-radar ingest --file corrected-8731009.xlsx --release-period 2026-09 --published-at 2026-11-02 --edition 2 --source-url https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/sep-2026/8731009.xlsx --data-dir data
```

`corrected-8731009.xlsx` in that command is a future example, not an included or observed source correction. Edition numbers are local ordering decisions. Do not use a higher edition just to bypass a checksum conflict without checking which file is newer.

## Backups and rebuilds

Keep the raw files/manifests and a consistent database backup. Use SQLite's backup API or stop all writers before copying the database together with any WAL state. Copying only an actively written main database file can omit committed WAL changes.

Rebuild into a **new directory**, loading retained raw files with their recorded release/edition/publication metadata. Compare row counts, source digests, revision summaries and integrity checks before using the rebuilt outputs. Changing parser logic does not silently rewrite an immutable existing snapshot: use a separate rebuild to make that change reviewable.

No automatic retention deletion, schema migration, production alerting, service deployment or refresh scheduler is included. Version 1 rejects an unsupported database schema version. Raw files and export generations accumulate until an operator applies a retention policy.
