"""Validate tidy tables against versioned domain contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import yaml

from housing_radar.paths import CONTRACTS, ROOT, TIDY


class ContractError(ValueError):
    """One or more contract expectations failed."""


@dataclass(frozen=True)
class Contract:
    path: Path
    domain: str
    name: str
    version: str
    file: Path
    columns: list[dict]
    expectations: list[dict]
    primary_key: list[str]


def contract_files() -> list[Path]:
    return sorted(CONTRACTS.glob("*/*.yaml"))


def load_contract(path: Path) -> Contract:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    relative = Path(document["file"])
    data_file = relative if relative.is_absolute() else ROOT / relative
    return Contract(
        path=path,
        domain=document["domain"],
        name=document["name"],
        version=str(document["version"]),
        file=data_file,
        columns=document["columns"],
        expectations=document.get("expectations", []),
        primary_key=document.get("primary_key", []),
    )


def _null(value: str) -> bool:
    return value is None or str(value).strip() == ""


def _decimal(value: str) -> Decimal:
    return Decimal(str(value).strip())


def _parse(value: str, kind: str):
    if kind == "string":
        return str(value).strip()
    if kind == "integer":
        return int(value)
    if kind == "number":
        return _decimal(value)
    if kind == "date":
        return date.fromisoformat(value)
    if kind == "quarter":
        text = str(value).strip()
        year, quarter = text.split("-Q")
        if len(year) != 4 or quarter not in {"1", "2", "3", "4"}:
            raise ValueError(f"not a quarter: {value}")
        return text
    raise ValueError(f"unknown type {kind}")


def _read_rows(contract: Contract) -> tuple[list[str], list[dict[str, str]]]:
    import csv

    with contract.file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ContractError(f"{contract.name}: empty file")
        rows = list(reader)
    return list(reader.fieldnames), rows


def validate_contract(contract: Contract) -> dict:
    errors: list[str] = []
    if not contract.file.exists():
        raise ContractError(f"{contract.name}: missing {contract.file}")
    header, rows = _read_rows(contract)
    expected_names = [column["name"] for column in contract.columns]
    if header != expected_names:
        errors.append(f"columns {header} != {expected_names}")
    parsed_rows: list[dict] = []
    column_by_name = {column["name"]: column for column in contract.columns}
    for line_number, raw in enumerate(rows, start=2):
        parsed: dict = {}
        for name, column in column_by_name.items():
            value = raw.get(name, "")
            if _null(value):
                if column.get("required", False):
                    errors.append(f"line {line_number}: {name} is null")
                parsed[name] = None
                continue
            try:
                coerced = _parse(value, column["type"])
            except (ValueError, ArithmeticError):
                errors.append(f"line {line_number}: {name} is not {column['type']} ({value})")
                parsed[name] = None
                continue
            if isinstance(coerced, Decimal):
                minimum = column.get("min")
                maximum = column.get("max")
                if minimum is not None and coerced < Decimal(str(minimum)):
                    errors.append(f"line {line_number}: {name} {coerced} < {minimum}")
                if maximum is not None and coerced > Decimal(str(maximum)):
                    errors.append(f"line {line_number}: {name} {coerced} > {maximum}")
            if isinstance(coerced, int) and not isinstance(coerced, bool):
                if "min" in column and coerced < column["min"]:
                    errors.append(f"line {line_number}: {name} {coerced} < {column['min']}")
                if "max" in column and coerced > column["max"]:
                    errors.append(f"line {line_number}: {name} {coerced} > {column['max']}")
            allowed = column.get("allowed")
            if allowed is not None and coerced not in allowed and str(coerced) not in {str(item) for item in allowed}:
                errors.append(f"line {line_number}: {name} {coerced} is not allowed")
            parsed[name] = coerced
        parsed_rows.append(parsed)
    if contract.primary_key:
        seen = set()
        for line_number, parsed in enumerate(parsed_rows, start=2):
            key = tuple(parsed.get(column) for column in contract.primary_key)
            if key in seen:
                errors.append(f"line {line_number}: duplicate primary key {key}")
            seen.add(key)
    for expectation in contract.expectations:
        errors.extend(_expectation(expectation, parsed_rows))
    if errors:
        preview = "\n".join(errors[:12])
        extra = f"\n... {len(errors) - 12} more" if len(errors) > 12 else ""
        raise ContractError(f"{contract.domain}/{contract.name} v{contract.version} failed\n{preview}{extra}")
    return {
        "domain": contract.domain,
        "name": contract.name,
        "version": contract.version,
        "rows": len(parsed_rows),
        "file": str(contract.file.relative_to(ROOT)),
    }


def _expectation(expectation: dict, rows: list[dict]) -> list[str]:
    kind = expectation["type"]
    if kind == "min_rows":
        if len(rows) < expectation["value"]:
            return [f"expected at least {expectation['value']} rows, found {len(rows)}"]
        return []
    if kind == "latest_value":
        ordered = [row for row in rows if row.get(expectation["order_by"]) is not None]
        ordered.sort(key=lambda row: row[expectation["order_by"]])
        latest = ordered[-1][expectation["column"]]
        target = Decimal(str(expectation["equals"]))
        if Decimal(str(latest)) != target:
            return [f"latest {expectation['column']} is {latest}, expected {target}"]
        return []
    if kind == "row_exists":
        wanted = expectation["where"]
        for row in rows:
            if all(_matches(row.get(key), value) for key, value in wanted.items()):
                if "equals" in expectation:
                    actual = row.get(expectation["column"])
                    if Decimal(str(actual)) != Decimal(str(expectation["equals"])):
                        return [
                            f"row {wanted} has {expectation['column']}={actual}, expected {expectation['equals']}"
                        ]
                return []
        return [f"missing row {wanted}"]
    return [f"unknown expectation {kind}"]


def _matches(actual, expected) -> bool:
    if isinstance(actual, date):
        return actual.isoformat() == str(expected) or actual == expected
    if isinstance(actual, datetime):
        return actual.date().isoformat() == str(expected)
    if isinstance(actual, Decimal):
        return actual == Decimal(str(expected))
    return actual == expected or str(actual) == str(expected)


def validate_all(tidy_dir=None) -> list[dict]:
    """Validate every contract. `tidy_dir` rewrites contract file locations for tests."""
    results = []
    for path in contract_files():
        contract = load_contract(path)
        if tidy_dir is not None:
            contract = Contract(
                path=contract.path,
                domain=contract.domain,
                name=contract.name,
                version=contract.version,
                file=Path(tidy_dir) / contract.file.name,
                columns=contract.columns,
                expectations=contract.expectations,
                primary_key=contract.primary_key,
            )
        results.append(validate_contract(contract))
    domains = {result["domain"] for result in results}
    missing = {"prices", "credit", "supply"} - domains
    if missing:
        raise ContractError(f"missing domains: {sorted(missing)}")
    return results


def tidy_ready() -> bool:
    return TIDY.exists() and any(TIDY.glob("*.csv"))
