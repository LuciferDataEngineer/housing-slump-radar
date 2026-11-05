"""Offline tests for repayments, badges, pinned sources and tidy contracts."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from housing_radar.badges import price_change_badge, repayment_badge, revision_badge
from housing_radar.contracts import validate_all
from housing_radar.paths import ROOT, TIDY
from housing_radar.prepare import load_approvals, load_cash_rate, prepare
from housing_radar.repayments import monthly_repayment
from housing_radar.sources import SOURCES


def test_standard_repayment_matches_the_six_percent_example():
    # $100,000 at 6% for 30 years is a widely published $599.55 payment.
    assert round(monthly_repayment(100_000, 6), 2) == 599.55


def test_badges_use_the_published_thresholds():
    assert price_change_badge(-2.4, act_at=-2) == "act"
    assert price_change_badge(-0.7, act_at=-2) == "watch"
    assert price_change_badge(1.4, act_at=-2) == "good"
    assert price_change_badge(-5, act_at=-5) == "act"
    assert repayment_badge(358) == "act"
    assert repayment_badge(20) == "watch"
    assert revision_badge(206) == "watch"
    assert revision_badge(4) == "good"


def test_pinned_checksums():
    import hashlib

    for source in SOURCES:
        path = ROOT / source["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == source["sha256"]


def test_cash_rate_includes_the_november_hike_and_the_blank_september_field():
    rows = {row["date"]: row for row in load_cash_rate()}
    assert rows[date(2026, 11, 4)]["target"] == Decimal("4.85")
    assert rows[date(2026, 9, 30)]["target"] == Decimal("4.60")
    assert rows[date(2026, 9, 30)]["source_change"] is None
    assert rows[date(2026, 11, 4)]["source_change"] == Decimal("0.25")


def test_recent_approval_arithmetic_is_clean_and_august_was_revised():
    observations, findings = load_approvals()
    recent = [row for row in findings if row["month"] >= "2011-01-01"]
    assert recent == []
    assert findings, "historical ABS arithmetic gaps should stay visible"

    def value(vintage, month):
        return next(
            row["value"]
            for row in observations
            if row["vintage"] == vintage
            and row["month"] == month
            and row["region"] == "Australia"
            and row["dwelling_type"] == "Total (Type of Building)"
        )

    assert value("2026-09", "2026-09-01") == 18318
    assert value("2026-09", "2026-08-01") - value("2026-08", "2026-08-01") == 206


def test_prepare_matches_the_committed_tidy_tables(tmp_path: Path):
    prepare(tmp_path)
    for path in sorted(tmp_path.glob("*.csv")):
        committed = (TIDY / path.name).read_text(encoding="utf-8")
        assert path.read_text(encoding="utf-8") == committed


def test_domain_contracts_cover_prices_credit_and_supply():
    results = validate_all()
    assert {row["domain"] for row in results} == {"prices", "credit", "supply"}
    assert sum(row["rows"] for row in results) > 1000


def test_dashboard_pages_are_separate_and_local():
    names = ["index.html", "prices.html", "credit.html", "supply.html", "suburbs.html", "actions.html"]
    for name in names:
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        assert "assets/site.js" in text
        assert "assets/site.css" in text
        for other in names:
            assert f'href="{other}"' in text
        assert "cdn." not in text
        assert "http://localhost" not in text


def test_published_repayment_matches_the_formula():
    path = ROOT / "docs" / "data" / "overview.json"
    if not path.exists():
        pytest.skip("dashboard JSON is written by housing-radar build")
    import json

    page = json.loads(path.read_text(encoding="utf-8"))
    metrics = page["metrics"]
    for key, rate_key in (
        ("repayment_end_2025", "discounted_rate_end_2025"),
        ("repayment_published", "discounted_rate_published"),
        ("repayment_scenario", "scenario_rate"),
    ):
        expected = monthly_repayment(metrics["loan_principal"], metrics[rate_key])
        assert metrics[key] == pytest.approx(expected, abs=0.05)
    assert metrics["cash_rate_target"] == 4.85
    assert metrics["hikes_2026"] == 5
    assert metrics["august_revision"] == 206
    suburb = json.loads((ROOT / "docs" / "data" / "suburbs.json").read_text(encoding="utf-8"))
    labels = [row[0] for row in suburb["table"]["rows"]]
    assert "Toorak" in labels
