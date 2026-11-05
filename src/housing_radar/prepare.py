"""Turn pinned publisher files into tidy domain tables."""

from __future__ import annotations

import csv
import math
import warnings
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from openpyxl import load_workbook

from housing_radar.paths import RAW, TIDY

CASH_FROM = date(2022, 1, 1)
LENDING_FROM = date(2019, 1, 1)
REGIONS = {
    "AUS": "Australia",
    "1": "New South Wales",
    "2": "Victoria",
    "3": "Queensland",
    "4": "South Australia",
    "5": "Western Australia",
    "6": "Tasmania",
    "7": "Northern Territory",
    "8": "Australian Capital Territory",
}
PURPOSE = {"TOT": "total", "DV5167": "owner_occupier", "DV5168": "investor"}
ADJUSTMENT = {"10": "original", "20": "seasonally_adjusted"}
QUARTER_COLUMNS = (
    ("2025-Q1", 1, 2),
    ("2025-Q2", 3, 4),
    ("2025-Q3", 5, 6),
    ("2025-Q4", 7, 8),
    ("2026-Q1", 9, 10),
)


def _write(path: Path, rows: list[dict], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: "" if row.get(key) is None else row.get(key) for key in columns})


def _rba_date(value: str) -> date | None:
    value = (value or "").strip()
    for fmt in ("%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _rows(path: Path) -> list[list[str]]:
    text = path.read_text(encoding="utf-8-sig")
    return list(csv.reader(text.splitlines()))


def _series_index(rows: list[list[str]]) -> dict[str, int]:
    for row in rows:
        if row and row[0] == "Series ID":
            return {series: index for index, series in enumerate(row)}
    raise ValueError(f"Series ID row not found in {rows[0][:1]}")


def _cell(row: list[str], index: int) -> str:
    if index >= len(row):
        return ""
    return row[index].strip()


def load_cash_rate(path: Path | None = None) -> list[dict]:
    """Daily cash-rate target. `source_change` is the publisher's change field and can be blank."""
    rows = _rows(path or RAW / "rba" / "f1-data.csv")
    index = _series_index(rows)
    target_at = index["FIRMMCRTD"]
    change_at = index["FIRMMCCRT"]
    loaded = []
    for row in rows:
        observed = _rba_date(row[0] if row else "")
        if observed is None or observed < CASH_FROM:
            continue
        raw_target = _cell(row, target_at)
        if raw_target == "":
            continue
        raw_change = _cell(row, change_at)
        loaded.append(
            {
                "date": observed,
                "target": Decimal(raw_target),
                "source_change": Decimal(raw_change) if raw_change else None,
            }
        )
    loaded.sort(key=lambda item: item["date"])
    return loaded


def load_lending_rates(path: Path | None = None) -> list[dict]:
    rows = _rows(path or RAW / "rba" / "f5-data.csv")
    index = _series_index(rows)
    wanted = {
        "discounted_owner_occupier": "FILRHLBVD",
        "standard_owner_occupier": "FILRHLBVS",
        "discounted_investor": "FILRHLBVDI",
        "fixed_3y_owner_occupier": "FILRHL3YF",
    }
    loaded = []
    for row in rows:
        observed = _rba_date(row[0] if row else "")
        if observed is None or observed < LENDING_FROM:
            continue
        record = {"month_end": observed}
        for name, series in wanted.items():
            raw = _cell(row, index[series])
            record[name] = Decimal(raw) if raw else None
        if record["discounted_owner_occupier"] is None:
            continue
        loaded.append(record)
    loaded.sort(key=lambda item: item["month_end"])
    return loaded


def _scale(value: str, multiplier: str) -> int:
    return int((Decimal(value) * (Decimal(10) ** int(multiplier))).to_integral_value())


def load_mean_prices(path: Path | None = None) -> list[dict]:
    measures = {"1": "stock_value_aud", "4": "dwelling_count", "5": "mean_price_aud"}
    combined: dict[tuple[str, str], dict] = {}
    with (path or RAW / "abs" / "res_dwell_st.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["MEASURE"] not in measures or row["REGION"] not in REGIONS:
                continue
            if not row["OBS_VALUE"]:
                continue
            key = (row["REGION"], row["TIME_PERIOD"])
            record = combined.setdefault(
                key,
                {
                    "region_code": row["REGION"],
                    "region_name": REGIONS[row["REGION"]],
                    "quarter": row["TIME_PERIOD"],
                    "mean_price_aud": "",
                    "dwelling_count": "",
                    "stock_value_aud": "",
                },
            )
            record[measures[row["MEASURE"]]] = _scale(row["OBS_VALUE"], row["UNIT_MULT"])
    rows = [combined[key] for key in sorted(combined) if combined[key]["mean_price_aud"] != ""]
    return rows


def load_commitments(path: Path | None = None) -> list[dict]:
    keyed: dict[tuple, dict] = {}
    with (path or RAW / "abs" / "lend_housing.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["DATA_ITEM"] != "NEWCOMMITS" or row["LOAN_PURPOSE"] != "TOTDWELL":
                continue
            if row["LENDER_TYPE"] != "TOT" or row["HOUSING_PURPOSE"] not in PURPOSE:
                continue
            if row["TSEST"] not in ADJUSTMENT or row["REGION"] not in REGIONS:
                continue
            if row["MEASURE"] not in {"FIN_NUM", "FIN_VAL"} or not row["OBS_VALUE"]:
                continue
            key = (row["TIME_PERIOD"], row["REGION"], row["HOUSING_PURPOSE"], row["TSEST"])
            record = keyed.setdefault(
                key,
                {
                    "quarter": row["TIME_PERIOD"],
                    "region_code": row["REGION"],
                    "region_name": REGIONS[row["REGION"]],
                    "housing_purpose": PURPOSE[row["HOUSING_PURPOSE"]],
                    "adjustment": ADJUSTMENT[row["TSEST"]],
                    "commitments": "",
                    "value_aud": "",
                },
            )
            amount = _scale(row["OBS_VALUE"], row["UNIT_MULT"])
            if row["MEASURE"] == "FIN_NUM":
                record["commitments"] = amount
            else:
                record["value_aud"] = amount
    rows = []
    for key in sorted(keyed):
        record = keyed[key]
        if record["commitments"] == "" or record["value_aud"] == "":
            continue
        rows.append(record)
    return rows


def _price(value) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return round(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if text in {"", "-", "NA", "N/A", "*", "^"}:
        return None
    try:
        return round(float(text))
    except ValueError:
        return None


def _low_sample(flag) -> int:
    return 1 if str(flag or "").strip() in {"^", "*"} else 0


def _place(name: str) -> str:
    return " ".join(part.capitalize() for part in " ".join(name.split()).split(" "))


def load_suburb_quarters(path: Path | None = None) -> list[dict]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import xlrd
    book = xlrd.open_workbook(path or RAW / "datavic" / "median-house-march-quarter-2026.xls")
    sheet = book.sheet_by_index(0)
    rows = []
    for index in range(7, sheet.nrows):
        locality = str(sheet.cell_value(index, 0)).strip()
        if not locality or locality.startswith("^") or "means" in locality.lower():
            continue
        sales = _price(sheet.cell_value(index, 11))
        for quarter, value_col, flag_col in QUARTER_COLUMNS:
            price = _price(sheet.cell_value(index, value_col))
            if price is None:
                continue
            rows.append(
                {
                    "locality": _place(locality),
                    "quarter": quarter,
                    "median_price": price,
                    "sales": sales if quarter == "2026-Q1" else "",
                    "low_sample": _low_sample(sheet.cell_value(index, flag_col)),
                }
            )
    rows.sort(key=lambda item: (item["locality"], item["quarter"]))
    return rows


def load_suburb_annual(path: Path | None = None) -> list[dict]:
    workbook = load_workbook(path or RAW / "datavic" / "houses-by-suburb-2015-2025.xlsx", read_only=True, data_only=True)
    try:
        sheet = workbook.active
        grid = list(sheet.iter_rows(values_only=True))
    finally:
        workbook.close()
    header = grid[1]
    year_columns = []
    index = 1
    while index < len(header):
        header_value = header[index]
        if isinstance(header_value, (int, float)) and not isinstance(header_value, bool) and float(header_value).is_integer():
            year_columns.append((int(header_value), index, index + 1))
            index += 2
        else:
            index += 1
    rows = []
    for record in grid[5:]:
        if not record or not isinstance(record[0], str):
            continue
        locality = record[0].strip()
        if not locality or locality.startswith("^"):
            continue
        for year, value_col, flag_col in year_columns:
            price = _price(record[value_col] if value_col < len(record) else None)
            if price is None:
                continue
            flag = record[flag_col] if flag_col < len(record) else ""
            rows.append(
                {
                    "locality": _place(locality),
                    "year": year,
                    "median_price": price,
                    "low_sample": _low_sample(flag),
                }
            )
    rows.sort(key=lambda item: (item["locality"], item["year"]))
    return rows


def _approvals_table(path: Path, vintage: str) -> tuple[list[dict], list[dict]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        grid = list(workbook["Data1"].iter_rows(values_only=True))
    finally:
        workbook.close()
    descriptions = grid[0]
    series_ids = grid[9]
    columns = []
    for index, description in enumerate(descriptions):
        if not isinstance(description, str) or "Total number of dwelling units" not in description:
            continue
        parts = [part.strip() for part in description.split(";") if part.strip()]
        if len(parts) != 3:
            raise ValueError(f"Unexpected Table 09 description: {description}")
        columns.append((index, series_ids[index], parts[1], parts[2]))
    if len(columns) != 27:
        raise ValueError(f"{path.name} resolved {len(columns)} series, expected 27")
    observations = []
    by_month: dict[date, dict[tuple[str, str], int]] = {}
    for record in grid[10:]:
        observed = record[0]
        if isinstance(observed, datetime):
            observed = observed.date()
        if not isinstance(observed, date):
            continue
        month_values: dict[tuple[str, str], int] = {}
        for index, series_id, dwelling_type, region in columns:
            value = record[index]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
                raise ValueError(f"{vintage} {series_id} {observed} is not an integer count")
            count = int(value)
            observations.append(
                {
                    "vintage": vintage,
                    "series_id": series_id,
                    "region": region,
                    "dwelling_type": dwelling_type,
                    "month": observed.isoformat(),
                    "value": count,
                }
            )
            month_values[(region, dwelling_type)] = count
        by_month[observed] = month_values
    findings = []
    dwelling_types = ["Houses", "Dwellings excluding houses", "Total (Type of Building)"]
    state_names = [name for name in REGIONS.values() if name != "Australia"]
    for observed, month_values in sorted(by_month.items()):
        for region in list(state_names) + ["Australia"]:
            houses = month_values[(region, dwelling_types[0])]
            other = month_values[(region, dwelling_types[1])]
            total = month_values[(region, dwelling_types[2])]
            if houses + other != total:
                findings.append(
                    {
                        "vintage": vintage,
                        "month": observed.isoformat(),
                        "region": region,
                        "dwelling_type": dwelling_types[2],
                        "rule": "houses_plus_other_equals_total",
                        "expected": houses + other,
                        "actual": total,
                    }
                )
        for dwelling_type in dwelling_types:
            expected = sum(month_values[(region, dwelling_type)] for region in state_names)
            actual = month_values[("Australia", dwelling_type)]
            if expected != actual:
                findings.append(
                    {
                        "vintage": vintage,
                        "month": observed.isoformat(),
                        "region": "Australia",
                        "dwelling_type": dwelling_type,
                        "rule": "states_sum_to_australia",
                        "expected": expected,
                        "actual": actual,
                    }
                )
    return observations, findings


def load_approvals() -> tuple[list[dict], list[dict]]:
    observations: list[dict] = []
    findings: list[dict] = []
    for vintage, name in (("2026-08", "8731009-aug-2026.xlsx"), ("2026-09", "8731009-sep-2026.xlsx")):
        observed, found = _approvals_table(RAW / "abs" / name, vintage)
        observations.extend(observed)
        findings.extend(found)
    observations.sort(key=lambda item: (item["vintage"], item["month"], item["region"], item["dwelling_type"]))
    findings.sort(key=lambda item: (item["vintage"], item["month"], item["region"], item["dwelling_type"], item["rule"]))
    return observations, findings


def _rate(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.quantize(Decimal("0.01")), "f")


def prepare(tidy_dir: Path | None = None) -> dict:
    """Write tidy CSVs. Returns row counts."""
    destination = Path(tidy_dir) if tidy_dir else TIDY
    cash = load_cash_rate()
    lending = load_lending_rates()
    prices = load_mean_prices()
    commitments = load_commitments()
    quarters = load_suburb_quarters()
    annual = load_suburb_annual()
    approvals, findings = load_approvals()
    _write(
        destination / "cash_rate.csv",
        [{"date": row["date"].isoformat(), "cash_rate_target": _rate(row["target"])} for row in cash],
        ["date", "cash_rate_target"],
    )
    _write(
        destination / "lending_rates.csv",
        [
            {
                "month_end": row["month_end"].isoformat(),
                "discounted_owner_occupier": _rate(row["discounted_owner_occupier"]),
                "standard_owner_occupier": _rate(row["standard_owner_occupier"]),
                "discounted_investor": _rate(row["discounted_investor"]),
                "fixed_3y_owner_occupier": _rate(row["fixed_3y_owner_occupier"]),
            }
            for row in lending
        ],
        [
            "month_end",
            "discounted_owner_occupier",
            "standard_owner_occupier",
            "discounted_investor",
            "fixed_3y_owner_occupier",
        ],
    )
    _write(
        destination / "mean_dwelling_price.csv",
        prices,
        ["region_code", "region_name", "quarter", "mean_price_aud", "dwelling_count", "stock_value_aud"],
    )
    _write(
        destination / "suburb_median.csv",
        quarters,
        ["locality", "quarter", "median_price", "sales", "low_sample"],
    )
    _write(destination / "suburb_annual.csv", annual, ["locality", "year", "median_price", "low_sample"])
    _write(
        destination / "loan_commitments.csv",
        commitments,
        ["quarter", "region_code", "region_name", "housing_purpose", "adjustment", "commitments", "value_aud"],
    )
    _write(
        destination / "building_approvals.csv",
        approvals,
        ["vintage", "series_id", "region", "dwelling_type", "month", "value"],
    )
    _write(
        destination / "approval_quality.csv",
        findings,
        ["vintage", "month", "region", "dwelling_type", "rule", "expected", "actual"],
    )
    return {
        "cash_rate": len(cash),
        "lending_rates": len(lending),
        "mean_dwelling_price": len(prices),
        "suburb_median": len(quarters),
        "suburb_annual": len(annual),
        "loan_commitments": len(commitments),
        "building_approvals": len(approvals),
        "approval_quality": len(findings),
        "tidy_dir": str(destination),
    }
