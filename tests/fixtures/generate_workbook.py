"""Build a byte-reproducible, fictional ABS Table 09-shaped workbook.

Only the public series identifiers and schema mirror ABS. Every numeric value
is generated for tests and must not be presented as a real approval statistic.
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from openpyxl import Workbook

REGIONS = (
    ("NSW", "New South Wales"), ("VIC", "Victoria"), ("QLD", "Queensland"),
    ("SA", "South Australia"), ("WA", "Western Australia"), ("TAS", "Tasmania"),
    ("NT", "Northern Territory"), ("ACT", "Australian Capital Territory"), ("AUS", "Australia"),
)
DWELLINGS = (
    ("houses", "Houses", ("A418511A", "A418596X", "A418675W", "A418757A", "A418839F", "A418920R", "A419010W", "A419079V", "A418427K")),
    ("other", "Dwellings excluding houses", ("A421353R", "A421445X", "A421536F", "A421628R", "A421720F", "A421807W", "A421889L", "A421971X", "A421262J")),
    ("total", "Total (Type of Building)", ("A422166A", "A422266K", "A422366V", "A422466C", "A422566L", "A422666W", "A422766F", "A422863J", "A422064L")),
)
SERIES = tuple(
    (identifiers[index], region, region_name, dwelling, description)
    for dwelling, description, identifiers in DWELLINGS
    for index, (region, region_name) in enumerate(REGIONS)
)


def month_sequence(end: str, months: int) -> list[datetime]:
    """Return contiguous month starts ending at the supplied YYYY-MM."""
    year, month = map(int, end.split("-"))
    last = year * 12 + month - 1
    return [datetime(value // 12, value % 12 + 1, 1) for value in range(last - months + 1, last + 1)]


def build_workbook(path: str | Path, *, end: str = "2026-09", months: int = 24,
                   adjustments: dict[tuple[str, str], int] | None = None,
                   zero_months: set[str] | None = None) -> Path:
    """Create a complete fixture; adjustments alter state houses and its totals.

    An adjustment key is (YYYY-MM, state abbreviation), for example
    {("2025-12", "NSW"): 5}. National totals are recalculated consistently.
    """
    if months < 1:
        raise ValueError("months must be positive")
    adjustments, zero_months = adjustments or {}, zero_months or set()
    dates = month_sequence(end, months)
    workbook = Workbook()
    workbook.active.title = "Index"
    workbook.active["A1"] = "SYNTHETIC TEST DATA — fictional values shaped like ABS Table 09"
    worksheet = workbook.create_sheet("Data1")
    metadata = ("Unit", "Series Type", "Data Type", "Frequency", "Collection Month", "Series Start", "Series End", "No. Obs", "Series ID")
    for row, label in enumerate(metadata, start=2):
        worksheet.cell(row, 1, label)
    for column, (series_id, region, region_name, dwelling, description) in enumerate(SERIES, start=2):
        worksheet.cell(1, column, f"Total number of dwelling units ;  {description} ;  {region_name} ;")
        values = ("Number", "Original", "FLOW", "Month", 1, dates[0], dates[-1], len(dates), series_id)
        for row, value in enumerate(values, start=2):
            worksheet.cell(row, column, value)
    origin = 2024 * 12 + 9
    for row, observed in enumerate(dates, start=11):
        worksheet.cell(row, 1, observed)
        offset = observed.year * 12 + observed.month - 1 - origin
        month = observed.strftime("%Y-%m")
        houses, other = [], []
        for index, (region, _) in enumerate(REGIONS[:-1]):
            houses.append(0 if month in zero_months else 100 + 10 * index + 2 * offset + adjustments.get((month, region), 0))
            other.append(0 if month in zero_months else 50 + 5 * index + offset)
        houses.append(sum(houses))
        other.append(sum(other))
        totals = [house + unit for house, unit in zip(houses, other)]
        for column, value in enumerate(houses + other + totals, start=2):
            worksheet.cell(row, column, value)
    payload = BytesIO()
    workbook.save(payload)
    workbook.close()
    # XLSX is a ZIP archive. Normalize ZIP and document metadata timestamps so
    # rebuilding the same fixture gives the same source checksum on every run.
    normalized = BytesIO()
    with ZipFile(BytesIO(payload.getvalue())) as source, ZipFile(normalized, "w", compression=ZIP_DEFLATED) as target:
        for filename in sorted(source.namelist()):
            contents = source.read(filename)
            if filename == "docProps/core.xml":
                contents = re.sub(rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*(</dcterms:(?:created|modified)>)", rb"\g<1>2024-01-01T00:00:00Z\g<2>", contents)
            item = ZipInfo(filename, date_time=(2024, 1, 1, 0, 0, 0))
            item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o600 << 16
            target.writestr(item, contents)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(normalized.getvalue())
    return destination
