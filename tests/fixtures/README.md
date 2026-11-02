# Fictional workbook generator

`generate_workbook.py` creates deterministic test workbooks in temporary directories. It preserves the public Table 09 header structure and 27 series identifiers, but **all numbers are fictional**. No ABS source workbook or approval observations are committed as test data.

The default fixture covers October 2024–September 2026 (24 months). Eight states and territories each have houses, other dwellings and total dwellings. Australian series sum the eight jurisdictions. The generator reconciles both dimensions, supports consistent revisions and zero-baseline months, and normalizes workbook metadata timestamps to produce repeatable bytes.

Tests deliberately alter copies to probe structural failures and source-authored arithmetic discrepancies. An arithmetic discrepancy should be recorded as a quality finding while preserving the original observation; malformed schemas and invalid observations must fail the load.
