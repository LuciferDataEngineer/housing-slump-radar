"""CLI with machine-readable output and human-readable diagnostics on stderr."""

import argparse
import json
import logging
import sys

from .pipeline import export_report, fetch_release, run_pipeline


def main() -> int:
    logging.basicConfig(level=logging.INFO,format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Store immutable ABS Table 09 release snapshots")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest", help="Validate and load a local ABS workbook")
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--source-url", help="Original source URL; defaults to local file provenance")
    fetch = commands.add_parser("fetch", help="Download an official ABS release workbook and load it")
    for command in (ingest, fetch):
        command.add_argument("--release-period", required=True, help="Observation release period YYYY-MM")
        command.add_argument("--published-at", required=True, help="Announced release date YYYY-MM-DD; not capture time")
        command.add_argument("--edition", type=int, default=1, help="Explicit local edition number for source replacements")
        command.add_argument("--data-dir", default="data")
    report = commands.add_parser("report", help="Regenerate current-snapshot CSV and JSON reports")
    report.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    try:
        if args.command == "report":
            result = export_report(args.data_dir)
        else:
            options = {"release_period": args.release_period, "published_at": args.published_at, "edition": args.edition}
            if args.command == "ingest":
                result = run_pipeline(args.data_dir, file_path=args.file, source_url=args.source_url, **options)
            else:
                result = fetch_release(args.data_dir, **options)
    except Exception as exc:
        print(f"Housing pipeline failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
