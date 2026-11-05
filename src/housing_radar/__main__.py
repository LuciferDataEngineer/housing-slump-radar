"""Command line for the offline build and the pinned-source check."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def _dbt() -> str:
    return str(Path(sys.executable).with_name("dbt"))

from housing_radar.contracts import validate_all
from housing_radar.paths import DASHBOARD_DATA, DBT, ROOT
from housing_radar.prepare import prepare
from housing_radar.publish import PAGES, publish
from housing_radar.sources import SOURCES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sources() -> None:
    for source in SOURCES:
        path = ROOT / source["path"]
        if not path.exists():
            raise SystemExit(f"Missing pinned file {source['path']}")
        actual = _sha256(path)
        if actual != source["sha256"]:
            raise SystemExit(f"Checksum mismatch for {source['path']}: {actual}")
    print(f"{len(SOURCES)} pinned source files match their checksums")


def fetch_sources(update: bool) -> None:
    for source in SOURCES:
        destination = ROOT / source["path"]
        urls = [source["url"]]
        if source.get("fallback_url"):
            urls.append(source["fallback_url"])
        payload = None
        used = None
        for url in urls:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "housing-slump-radar/2.0"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    payload = response.read()
                used = url
                break
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                print(f"Could not fetch {url}: {exc}", file=sys.stderr)
        if payload is None or used is None:
            raise SystemExit(f"No copy available for {source['path']}")
        actual = hashlib.sha256(payload).hexdigest()
        if actual != source["sha256"]:
            if not update:
                raise SystemExit(
                    f"{source['path']} from {used} hashed to {actual}, not the pinned {source['sha256']}. "
                    "The pinned file was left unchanged."
                )
            destination.write_bytes(payload)
            print(f"Updated {source['path']} from {used}. New sha256 {actual}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        print(f"Fetched {source['path']} from {used}")


def build() -> None:
    counts = prepare()
    print(json.dumps(counts, indent=2))
    results = validate_all()
    print(json.dumps(results, indent=2))
    import subprocess

    subprocess.check_call(
        [
            _dbt(),
            "build",
            "--profiles-dir",
            ".",
            "--vars",
            json.dumps({"tidy_dir": str((ROOT / "data" / "tidy").resolve())}),
        ],
        cwd=DBT,
    )
    publish()
    print(f"Wrote dashboard JSON to {DASHBOARD_DATA}")


def check() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        publish(Path(temporary))
        for name in PAGES:
            fresh = (Path(temporary) / f"{name}.json").read_text(encoding="utf-8")
            committed = DASHBOARD_DATA / f"{name}.json"
            if not committed.exists() or committed.read_text(encoding="utf-8") != fresh:
                raise SystemExit(f"docs/data/{name}.json does not match the marts. Run housing-radar build.")
    print("Dashboard JSON matches the marts")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the housing slump radar from pinned open data")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    commands.add_parser("contracts")
    commands.add_parser("publish")
    commands.add_parser("build")
    commands.add_parser("check")
    commands.add_parser("verify")
    fetch = commands.add_parser("fetch")
    fetch.add_argument("--update", action="store_true", help="Replace a pinned file when the publisher bytes change")
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(), indent=2))
    elif args.command == "contracts":
        print(json.dumps(validate_all(), indent=2))
    elif args.command == "publish":
        publish()
    elif args.command == "build":
        build()
    elif args.command == "check":
        check()
    elif args.command == "verify":
        verify_sources()
    elif args.command == "fetch":
        fetch_sources(args.update)
    return 0


if __name__ == "__main__":
    sys.exit(main())
