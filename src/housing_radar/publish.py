"""Serialize dbt marts into the static dashboard JSON."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import duckdb

from housing_radar.badges import (
    price_change_badge,
    repayment_badge,
    revision_badge,
)
from housing_radar.paths import DASHBOARD_DATA, DUCKDB

STATE_ORDER = [
    "New South Wales",
    "Victoria",
    "Queensland",
    "South Australia",
    "Western Australia",
    "Tasmania",
    "Northern Territory",
    "Australian Capital Territory",
]
SHORT = {
    "New South Wales": "NSW",
    "Victoria": "Vic",
    "Queensland": "Qld",
    "South Australia": "SA",
    "Western Australia": "WA",
    "Tasmania": "Tas",
    "Northern Territory": "NT",
    "Australian Capital Territory": "ACT",
    "Australia": "Australia",
}
PAGES = ("overview", "prices", "credit", "supply", "suburbs", "actions")


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _iso(value) -> str:
    return _as_date(value).isoformat()


def _day(value) -> str:
    observed = _as_date(value)
    return f"{observed.day} {observed.strftime('%B %Y')}"


def _month(value) -> str:
    return _as_date(value).strftime("%B %Y")


def _mon(value) -> str:
    return _as_date(value).strftime("%b %Y")


def _quarter(value: str) -> str:
    year, quarter = value.split("-")
    names = {"Q1": "March quarter", "Q2": "June quarter", "Q3": "September quarter", "Q4": "December quarter"}
    return f"{names[quarter]} {year}"


def aud(value: float) -> str:
    return f"${round(value):,}"


def money_change(value: float) -> str:
    rounded = round(value)
    if rounded < 0:
        return f"down ${abs(rounded):,}"
    if rounded > 0:
        return f"up ${rounded:,}"
    return "unchanged"


def signed_pct(value: float, digits: int = 1) -> str:
    number = round(float(value), digits)
    text = f"{abs(number):.{digits}f}"
    if number < 0:
        return f"−{text}%"
    if number > 0:
        return f"+{text}%"
    return f"{text}%"


def rate_text(value: float) -> str:
    return f"{float(value):.2f}%"


def _and(items: list[str]) -> str:
    if not items:
        return "none of the states"
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def _places(names: list[str]) -> str:
    pretty = ["the ACT" if name == "Australian Capital Territory" else name for name in names]
    return _and(pretty)


def _rows(connection: duckdb.DuckDBPyConnection, sql: str) -> list[dict]:
    cursor = connection.execute(sql)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _stat(label: str, value: str, detail: str, status: str) -> dict:
    return {"label": label, "value": value, "detail": detail, "status": status}


def _news() -> dict:
    return {
        "status": "watch",
        "title": "October news, not these charts",
        "body": (
            "On 2 November, Cotality said national home values fell 1.2% in October, "
            "a seventh monthly fall, and were about 6.7% ($63,000) under the March peak. "
            "Capital-city values were down 8.1% in seven months. Sales over three months "
            "were about 23% lower than a year earlier. PropTrack published a smaller October fall. "
            "Those private indexes are not plotted here."
        ),
        "href": "https://www.abc.net.au/news/2026-11-02/house-prices-fall-in-october-biggest-downturn-40-years-cotality/107325214",
        "link": "ABC report, 2 Nov 2026",
    }


def build_pages(connection: duckdb.DuckDBPyConnection) -> dict[str, dict]:
    overview = _rows(connection, "select * from mart_overview")[0]
    monthly = _rows(connection, "select * from mart_cash_monthly order by month_start")
    decisions = _rows(
        connection,
        "select * from mart_cash_decisions where rate_date >= date '2026-01-01' order by rate_date",
    )
    prices = _rows(connection, "select * from mart_state_prices")
    suburbs = _rows(connection, "select * from mart_suburb_risk order by yoy_pct, locality")
    approvals = _rows(connection, "select * from mart_approval_yoy")
    metrics = _metrics(overview)
    fallen = [
        row["region_name"]
        for row in prices
        if row["region_code"] != "AUS" and float(row["qoq_pct"]) < 0
    ]
    fallen.sort(key=lambda name: STATE_ORDER.index(name))
    pages = {
        "overview": _overview(metrics, monthly, decisions, fallen),
        "prices": _prices(metrics, prices),
        "credit": _credit(metrics, monthly, decisions),
        "supply": _supply(metrics, approvals),
        "suburbs": _suburbs(metrics, suburbs),
        "actions": _actions(metrics, fallen),
    }
    for page in pages.values():
        page["metrics"] = metrics
    return pages


def _metrics(row: dict) -> dict:
    principal = int(row["loan_principal"])
    end_2025 = float(row["repayment_end_2025"])
    published = float(row["repayment_published"])
    scenario = float(row["repayment_scenario"])
    return {
        "cash_rate_target": round(float(row["cash_rate_target"]), 2),
        "cash_rate_date": _iso(row["cash_rate_date"]),
        "hikes_2026": int(row["hikes_2026"]),
        "cash_rate_end_2025": round(float(row["cash_rate_end_2025"]), 2),
        "discounted_rate_end_2025": round(float(row["discounted_rate_end_2025"]), 2),
        "discounted_rate_published": round(float(row["discounted_rate_published"]), 2),
        "discounted_rate_month": _iso(row["discounted_rate_month"]),
        "lending_rate_last_increased": _iso(row["lending_rate_last_increased"]),
        "passthrough_gap_pp": round(float(row["passthrough_gap_pp"]), 2),
        "scenario_rate": round(float(row["scenario_rate"]), 2),
        "loan_principal": principal,
        "loan_quarter": row["loan_quarter"],
        "repayment_end_2025": round(end_2025, 2),
        "repayment_published": round(published, 2),
        "repayment_scenario": round(scenario, 2),
        "extra_published": round(published - end_2025, 2),
        "extra_scenario": round(scenario - end_2025, 2),
        "mean_price_australia": int(row["mean_price_australia"]),
        "mean_price_quarter": row["mean_price_quarter"],
        "mean_price_qoq_pct": round(float(row["mean_price_qoq_pct"]), 2),
        "mean_price_yoy_pct": round(float(row["mean_price_yoy_pct"]), 2),
        "mean_price_versus_peak_pct": round(float(row["mean_price_versus_peak_pct"]), 2),
        "approvals_month": _iso(row["approvals_month"]),
        "approvals_australia": int(row["approvals_australia"]),
        "approvals_australia_yoy_pct": round(float(row["approvals_australia_yoy_pct"]), 2),
        "approvals_victoria": int(row["approvals_victoria"]),
        "approvals_victoria_year_ago": int(row["approvals_victoria_year_ago"]),
        "approvals_victoria_yoy_pct": round(float(row["approvals_victoria_yoy_pct"]), 2),
        "august_revision": int(row["august_revision"]),
        "commitments_quarter": row["commitments_quarter"],
        "commitments_number": int(row["commitments_number"]),
        "commitments_yoy_pct": round(float(row["commitments_yoy_pct"]), 2),
        "suburbs_compared": int(row["suburbs_compared"]),
        "suburbs_down": int(row["suburbs_down"]),
        "suburbs_act": int(row["suburbs_act"]),
        "suburb_median_yoy_pct": round(float(row["suburb_median_yoy_pct"]), 2),
    }


def _cash_chart(monthly: list[dict], decisions: list[dict]) -> dict:
    hike_months = {_as_date(row["rate_date"]).strftime("%Y-%m") for row in decisions}
    points = []
    for row in monthly:
        observed = _as_date(row["month_start"])
        points.append(
            {
                "label": _mon(observed) if observed.month in {1, 4, 7, 10, 11} else "",
                "y": round(float(row["cash_rate_target"]), 2),
                "marker": observed.strftime("%Y-%m") in hike_months or observed == _as_date(monthly[-1]["month_start"]),
            }
        )
    points[-1]["label"] = rate_text(points[-1]["y"])
    return {
        "kind": "line",
        "title": "Cash rate target since January 2025",
        "unit": "%",
        "points": points,
    }


def _overview(metrics: dict, monthly: list[dict], decisions: list[dict], fallen: list[str]) -> dict:
    extra = metrics["extra_scenario"]
    return {
        "id": "overview",
        "status": repayment_badge(extra),
        "title": (
            f"Budget a new loan at {rate_text(metrics['scenario_rate'])}, "
            f"not last December's {rate_text(metrics['discounted_rate_end_2025'])}."
        ),
        "summary": (
            f"On the average new loan of {aud(metrics['loan_principal'])}, that is "
            f"{aud(metrics['repayment_scenario'])} a month, {money_change(extra)} from December 2025, "
            f"if lenders pass on the remaining cash-rate rise. "
            f"The official mean home price is {aud(metrics['mean_price_australia'])}, "
            f"{signed_pct(metrics['mean_price_qoq_pct'])} in the June quarter. "
            f"Victoria's September approvals were {signed_pct(metrics['approvals_victoria_yoy_pct'])} on a year earlier."
        ),
        "stats": [
            _stat(
                "Cash rate",
                rate_text(metrics["cash_rate_target"]),
                f"From {_day(metrics['cash_rate_date'])}. {metrics['hikes_2026']} rises in 2026.",
                "act",
            ),
            _stat(
                "Monthly repayment",
                aud(metrics["repayment_scenario"]),
                f"{money_change(extra).capitalize()} from December, if the remaining rises pass through.",
                repayment_badge(extra),
            ),
            _stat(
                "Mean home price",
                aud(metrics["mean_price_australia"]),
                f"Australia, {_quarter(metrics['mean_price_quarter'])}. {signed_pct(metrics['mean_price_qoq_pct'])} in the quarter.",
                price_change_badge(metrics["mean_price_qoq_pct"], act_at=-2),
            ),
            _stat(
                "Victoria approvals",
                f"{metrics['approvals_victoria']:,}",
                f"September 2026, {signed_pct(metrics['approvals_victoria_yoy_pct'])} on last September.",
                price_change_badge(metrics["approvals_victoria_yoy_pct"], act_at=-10),
            ),
        ],
        "charts": [_cash_chart(monthly, decisions)],
        "table": {
            "caption": "What to read first",
            "columns": ["Question", "Reading", "Status"],
            "rows": [
                [
                    "Where is repayment pressure?",
                    f"National. The published bank rate is already {rate_text(metrics['discounted_rate_published'])}, and two cash-rate steps are not in that figure yet.",
                    "Act",
                ],
                [
                    "Where are prices turning?",
                    f"The June-quarter mean fell in {_places(fallen)}. The other states were still rising.",
                    "Watch",
                ],
                [
                    "Where is supply weakest?",
                    f"Victoria. Australia as a whole was only {signed_pct(metrics['approvals_australia_yoy_pct'])}.",
                    "Act",
                ],
            ],
        },
        "callout": _news(),
        "sources": [
            "RBA table F1 cash rate target and table F5 discounted owner-occupier variable rate.",
            "ABS mean residential dwelling price, June quarter 2026, and Building Approvals Table 09, September 2026 vintage.",
            "Repayment is 30-year principal and interest on the June quarter average new loan. It is not a bank quote.",
        ],
    }


def _prices(metrics: dict, prices: list[dict]) -> dict:
    states = [row for row in prices if row["region_code"] != "AUS"]
    states.sort(key=lambda row: STATE_ORDER.index(row["region_name"]))
    fallen = [row["region_name"] for row in states if float(row["qoq_pct"]) < 0]
    return {
        "id": "prices",
        "status": price_change_badge(metrics["mean_price_qoq_pct"], act_at=-2),
        "title": f"Official mean prices turned down in {_places(fallen)}.",
        "summary": (
            f"Australia's mean residential price was {aud(metrics['mean_price_australia'])} in the June quarter, "
            f"{signed_pct(metrics['mean_price_qoq_pct'])} on the March quarter and still "
            f"{signed_pct(metrics['mean_price_yoy_pct'])} on a year earlier. "
            "This is the ABS stock measure, not the monthly Cotality index."
        ),
        "stats": [
            _stat(
                "Australia",
                aud(metrics["mean_price_australia"]),
                f"{signed_pct(metrics['mean_price_yoy_pct'])} on a year ago.",
                price_change_badge(metrics["mean_price_qoq_pct"], act_at=-2),
            ),
            _stat(
                "June quarter",
                signed_pct(metrics["mean_price_qoq_pct"]),
                "Change in the national mean price.",
                price_change_badge(metrics["mean_price_qoq_pct"], act_at=-2),
            ),
            _stat(
                "From the recent peak",
                signed_pct(metrics["mean_price_versus_peak_pct"]),
                "Against the highest quarter in the series since 2018.",
                price_change_badge(metrics["mean_price_versus_peak_pct"], act_at=-2),
            ),
        ],
        "charts": [
            {
                "kind": "diverge",
                "title": "June quarter change in the mean home price",
                "items": [
                    {
                        "label": SHORT[row["region_name"]],
                        "value": round(float(row["qoq_pct"]), 2),
                        "display": signed_pct(float(row["qoq_pct"])),
                        "status": price_change_badge(float(row["qoq_pct"]), act_at=-2),
                    }
                    for row in states
                ],
            }
        ],
        "table": {
            "caption": "Latest official mean price",
            "columns": ["State", "Mean price", "In the quarter", "On a year ago", "Status"],
            "rows": [
                [
                    row["region_name"],
                    aud(row["mean_price_aud"]),
                    signed_pct(float(row["qoq_pct"])),
                    signed_pct(float(row["yoy_pct"])),
                    price_change_badge(float(row["qoq_pct"]), act_at=-2).title(),
                ]
                for row in states
            ],
        },
        "callout": _news(),
        "sources": [
            "ABS Residential Dwellings: Values, Mean Price and Number by State, dataflow RES_DWELL_ST, measure 5.",
            "Mean price is the value of the dwelling stock divided by the number of dwellings. It is not a median sale price.",
        ],
    }


def _credit(metrics: dict, monthly: list[dict], decisions: list[dict]) -> dict:
    extra_published = metrics["extra_published"]
    extra = metrics["extra_scenario"]
    items = [
        ("December 2025", metrics["repayment_end_2025"], metrics["discounted_rate_end_2025"], "good"),
        ("Published rate", metrics["repayment_published"], metrics["discounted_rate_published"], repayment_badge(extra_published)),
        ("If the rest passes on", metrics["repayment_scenario"], metrics["scenario_rate"], repayment_badge(extra)),
    ]
    return {
        "id": "credit",
        "status": repayment_badge(extra),
        "title": (
            f"The cash rate is {rate_text(metrics['cash_rate_target'])}. "
            f"The published discounted mortgage rate is still {rate_text(metrics['discounted_rate_published'])}."
        ),
        "summary": (
            f"That bank rate is the September figure. It last rose in {_month(metrics['lending_rate_last_increased'])}. "
            f"Since then the cash rate is up {metrics['passthrough_gap_pp']:.2f} percentage points. "
            f"Passed on in full, the discounted rate would be {rate_text(metrics['scenario_rate'])}. "
            f"New loan commitments in the June quarter were {signed_pct(metrics['commitments_yoy_pct'])} on a year ago, "
            "not the 23% sales drop in the market news."
        ),
        "stats": [
            _stat(
                "Cash rate",
                rate_text(metrics["cash_rate_target"]),
                f"Effective {_day(metrics['cash_rate_date'])}. It was {rate_text(metrics['cash_rate_end_2025'])} at the end of 2025.",
                "act",
            ),
            _stat(
                "Published mortgage rate",
                rate_text(metrics["discounted_rate_published"]),
                f"Discounted owner-occupier variable, {_month(metrics['discounted_rate_month'])}.",
                repayment_badge(extra_published),
            ),
            _stat(
                "Scenario repayment",
                aud(metrics["repayment_scenario"]),
                f"{money_change(extra).capitalize()} a month from December, on a {aud(metrics['loan_principal'])} loan.",
                repayment_badge(extra),
            ),
        ],
        "charts": [
            {
                "kind": "compare",
                "title": "Monthly repayment on the average new loan",
                "items": [
                    {
                        "label": f"{label} · {rate_text(rate)}",
                        "value": round(amount, 2),
                        "display": aud(amount),
                        "status": status,
                    }
                    for label, amount, rate, status in items
                ],
            },
            _cash_chart(monthly, decisions),
        ],
        "table": {
            "caption": "Cash-rate steps in 2026",
            "columns": ["Effective", "New target", "Change"],
            "rows": [
                [_day(row["rate_date"]), rate_text(row["cash_rate_target"]), f"{float(row['change_pp']):+.2f} pp"]
                for row in decisions
            ],
        },
        "sources": [
            "RBA F1 daily cash rate target, published 5 November 2026. The 30 September step is read from the target level.",
            "RBA F5 discounted owner-occupier variable rate, series FILRHLBVD. The standard variable rate is higher and is not used here.",
            f"Loan size is the ABS seasonally adjusted average new commitment for total dwellings, excluding refinancing, {metrics['loan_quarter']}.",
            "The scenario adds the cash-rate rise since the discounted rate last moved. Banks may not pass it on in full.",
        ],
    }


def _supply(metrics: dict, approvals: list[dict]) -> dict:
    states = [row for row in approvals if row["region"] != "Australia"]
    states.sort(key=lambda row: STATE_ORDER.index(row["region"]))
    revision = metrics["august_revision"]
    return {
        "id": "supply",
        "status": price_change_badge(metrics["approvals_victoria_yoy_pct"], act_at=-10),
        "title": (
            f"Victoria approved {metrics['approvals_victoria']:,} homes in September, "
            f"{signed_pct(metrics['approvals_victoria_yoy_pct'])} on a year ago."
        ),
        "summary": (
            f"Australia approved {metrics['approvals_australia']:,}, only "
            f"{signed_pct(metrics['approvals_australia_yoy_pct'])} on last September. "
            f"The September release also revised August's national total "
            f"{'+' if revision > 0 else ''}{revision:,}. A revision is not a new month."
        ),
        "stats": [
            _stat(
                "Victoria",
                f"{metrics['approvals_victoria']:,}",
                f"Was {metrics['approvals_victoria_year_ago']:,} in September 2025.",
                price_change_badge(metrics["approvals_victoria_yoy_pct"], act_at=-10),
            ),
            _stat(
                "Australia",
                f"{metrics['approvals_australia']:,}",
                f"{signed_pct(metrics['approvals_australia_yoy_pct'])} on last September.",
                price_change_badge(metrics["approvals_australia_yoy_pct"], act_at=-10),
            ),
            _stat(
                "August revision",
                f"{revision:+,}",
                "Australia total, same month, newer release.",
                revision_badge(revision),
            ),
        ],
        "charts": [
            {
                "kind": "diverge",
                "title": "Change in September approvals from a year earlier",
                "items": [
                    {
                        "label": SHORT[row["region"]],
                        "value": int(row["change_count"]),
                        "display": f"{int(row['change_count']):+,}",
                        "status": price_change_badge(float(row["yoy_pct"]), act_at=-10),
                    }
                    for row in states
                ],
            }
        ],
        "table": {
            "caption": "Original total dwelling approvals, September",
            "columns": ["State", "Sep 2026", "Sep 2025", "Change", "Status"],
            "rows": [
                [
                    row["region"],
                    f"{int(row['approvals']):,}",
                    f"{int(row['approvals_year_ago']):,}",
                    signed_pct(float(row["yoy_pct"])),
                    price_change_badge(float(row["yoy_pct"]), act_at=-10).title(),
                ]
                for row in states
            ],
        },
        "sources": [
            "ABS Building Approvals Table 09, original counts, September 2026 release. Counts are dwelling units, not finished homes.",
            "Compare a month with the same month a year earlier. Original figures jump around from month to month.",
            "The August revision compares the August release with the September release for August 2026.",
        ],
    }


def _suburbs(metrics: dict, suburbs: list[dict]) -> dict:
    weakest = suburbs[:8]
    steepest = suburbs[0]
    steep_sales = steepest["sales_2026_q1"]
    steep_sales_text = "sales not published" if steep_sales is None else f"{int(steep_sales)} sales"
    up = metrics["suburbs_compared"] - metrics["suburbs_down"]
    return {
        "id": "suburbs",
        "status": "watch" if metrics["suburbs_down"] else "good",
        "title": (
            f"The typical Victorian suburb median was still {signed_pct(metrics['suburb_median_yoy_pct'])} "
            "in the March quarter."
        ),
        "summary": (
            f"Of {metrics['suburbs_compared']} suburbs with enough sales in both March quarters, "
            f"{up} were up and {metrics['suburbs_down']} were down. "
            f"{metrics['suburbs_act']} fell by more than 5%. "
            "The steep falls are concentrated in expensive inner-Melbourne suburbs. "
            "This file does not yet include the October news."
        ),
        "stats": [
            _stat(
                "Typical suburb",
                signed_pct(metrics["suburb_median_yoy_pct"]),
                "Median of suburb changes, March 2026 against March 2025.",
                price_change_badge(metrics["suburb_median_yoy_pct"], act_at=-5),
            ),
            _stat(
                "Suburbs down",
                str(metrics["suburbs_down"]),
                f"Out of {metrics['suburbs_compared']} with 10 or more sales in both quarters.",
                "watch" if metrics["suburbs_down"] else "good",
            ),
            _stat(
                steepest["locality"],
                signed_pct(float(steepest["yoy_pct"])),
                f"{aud(steepest['price_2025_q1'])} to {aud(steepest['price_2026_q1'])}. {steep_sales_text}.",
                price_change_badge(float(steepest["yoy_pct"]), act_at=-5),
            ),
        ],
        "charts": [
            {
                "kind": "diverge",
                "title": "Largest falls in the March-quarter median",
                "items": [
                    {
                        "label": row["locality"],
                        "value": round(float(row["yoy_pct"]), 2),
                        "display": signed_pct(float(row["yoy_pct"])),
                        "status": price_change_badge(float(row["yoy_pct"]), act_at=-5),
                    }
                    for row in weakest
                ],
            }
        ],
        "table": {
            "caption": "Those falls, with the sales count beside them",
            "columns": ["Suburb", "Mar 2025", "Mar 2026", "Change", "Sales"],
            "rows": [
                [
                    row["locality"],
                    aud(row["price_2025_q1"]),
                    aud(row["price_2026_q1"]),
                    signed_pct(float(row["yoy_pct"])),
                    "—" if row["sales_2026_q1"] is None else f"{int(row['sales_2026_q1'])}",
                ]
                for row in weakest
            ],
        },
        "sources": [
            "Valuer-General Victoria, median house prices by suburb, March quarter 2026 release.",
            "Suburbs with fewer than 10 sales in either March quarter are left out. A large fall on 12 sales is a thin sample.",
            "Repayment pressure from the cash rate applies on top of these price moves. It is national, so it does not change the ranking.",
        ],
    }


def _actions(metrics: dict, fallen: list[str]) -> dict:
    return {
        "id": "actions",
        "status": "act",
        "title": "Three checks before the next decision.",
        "summary": "These are monitoring prompts, not a recommendation to buy, lend or approve.",
        "cards": [
            {
                "status": "act",
                "kicker": "Buyer and lender risk",
                "title": f"Price the loan at {rate_text(metrics['scenario_rate'])}.",
                "body": (
                    f"December's discounted variable rate was {rate_text(metrics['discounted_rate_end_2025'])}. "
                    f"The latest published rate is {rate_text(metrics['discounted_rate_published'])}. "
                    f"The cash rate has since risen {metrics['passthrough_gap_pp']:.2f} percentage points. "
                    f"On a {aud(metrics['loan_principal'])} loan that is "
                    f"{money_change(metrics['extra_scenario'])} a month from December, "
                    f"{aud(metrics['repayment_scenario'])} in total. "
                    f"The official price weakness so far is in {_places(fallen)}, not in every state."
                ),
            },
            {
                "status": "act",
                "kicker": "Supply and approvals",
                "title": "Read Victoria separately from Australia.",
                "body": (
                    f"Victoria's September approvals were {metrics['approvals_victoria']:,}, "
                    f"down from {metrics['approvals_victoria_year_ago']:,} a year earlier. "
                    f"Australia was {metrics['approvals_australia']:,}, only "
                    f"{signed_pct(metrics['approvals_australia_yoy_pct'])}. "
                    f"Also separate the revision: August's national total was revised "
                    f"{metrics['august_revision']:+,} in the September release."
                ),
            },
            {
                "status": "watch",
                "kicker": "Suburb watchlist",
                "title": "Do not treat the March quarter as the October headline.",
                "body": (
                    f"In the latest Valuer-General quarter, the typical Victorian suburb was still "
                    f"{signed_pct(metrics['suburb_median_yoy_pct'])}. "
                    f"{metrics['suburbs_act']} suburbs fell more than 5%, led by high-priced inner suburbs "
                    "with modest sales counts. The October Cotality fall is newer and is a different series."
                ),
            },
        ],
        "sources": [
            "Not financial, credit or planning advice. Rates, loan size and approvals are the published series named on the other pages.",
        ],
    }


def publish(output_dir: Path | None = None, database: Path | None = None) -> dict[str, dict]:
    database = Path(database) if database else DUCKDB
    if not database.exists():
        raise FileNotFoundError(f"Missing {database}. Run housing-radar build first.")
    destination = Path(output_dir) if output_dir else DASHBOARD_DATA
    destination.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        pages = build_pages(connection)
    finally:
        connection.close()
    for name in PAGES:
        text = json.dumps(pages[name], indent=2, ensure_ascii=False) + "\n"
        (destination / f"{name}.json").write_text(text, encoding="utf-8")
    return pages
