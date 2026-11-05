"""Repository paths. Editable installs keep this file inside the checkout."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    override = os.environ.get("HSR_ROOT")
    if override:
        return Path(override).resolve()
    return Path(__file__).resolve().parents[2]


ROOT = repo_root()
DATA = ROOT / "data"
RAW = DATA / "raw"
TIDY = DATA / "tidy"
DOCS = ROOT / "docs"
DASHBOARD_DATA = DOCS / "data"
DBT = ROOT / "dbt"
DUCKDB = DBT / "target" / "housing.duckdb"
CONTRACTS = ROOT / "contracts"
