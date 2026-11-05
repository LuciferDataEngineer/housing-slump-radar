"""Runnable asset graph: tidy tables, contracts, dbt marts, dashboard JSON.

Load it with `dagster dev -m housing_radar.orchestration.definitions` from the
repository root after installing the stack extra.
"""

import json
import subprocess
import sys
from pathlib import Path

from dagster import Definitions, asset

from housing_radar.contracts import validate_all
from housing_radar.paths import DBT, ROOT
from housing_radar.prepare import prepare
from housing_radar.publish import publish


@asset(group_name="mesh", description="Tidy prices, credit and supply tables from pinned files.")
def tidy_tables() -> dict:
    return prepare()


@asset(group_name="mesh", deps=[tidy_tables], description="Versioned contracts for the three domains.")
def contract_results() -> list:
    return validate_all()


@asset(group_name="mesh", deps=[contract_results], description="dbt-duckdb marts that feed the dashboard.")
def dbt_marts() -> dict:
    subprocess.check_call(
        [
            str(Path(sys.executable).with_name("dbt")),
            "build",
            "--profiles-dir",
            ".",
            "--vars",
            json.dumps({"tidy_dir": str((ROOT / "data" / "tidy").resolve())}),
        ],
        cwd=DBT,
    )
    return {"project": "housing_slump_radar"}


@asset(group_name="mesh", deps=[dbt_marts], description="Static JSON consumed by the GitHub Pages dashboard.")
def dashboard_json() -> dict:
    pages = publish()
    return {"pages": sorted(pages)}


defs = Definitions(assets=[tidy_tables, contract_results, dbt_marts, dashboard_json])
