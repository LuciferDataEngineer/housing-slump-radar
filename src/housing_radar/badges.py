"""Monitoring badges for the dashboard.

These thresholds are this project's plain-language rules. They are not ABS,
RBA or bank classifications.
"""

from __future__ import annotations

STATUS_LABEL = {"good": "Good", "watch": "Watch", "act": "Act"}


def price_change_badge(change_pct: float, *, act_at: float) -> str:
    """Badge a percentage change. Falls at or below `act_at` are Act."""
    if change_pct <= act_at:
        return "act"
    if change_pct < 0:
        return "watch"
    return "good"


def repayment_badge(extra_dollars_per_month: float) -> str:
    """Badge the rise in a monthly repayment against December 2025."""
    if extra_dollars_per_month >= 300:
        return "act"
    if extra_dollars_per_month > 0:
        return "watch"
    return "good"


def revision_badge(change_in_count: int) -> str:
    """A large revision is something to read, not itself a supply collapse."""
    if abs(change_in_count) >= 50:
        return "watch"
    return "good"
