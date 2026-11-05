"""Standard principal-and-interest mortgage repayment.

The result is illustrative. It ignores fees, offsets, interest-only periods and
the difference between a bank's advertised rate and the rate a borrower is offered.
"""

from __future__ import annotations


def monthly_repayment(principal: float, annual_percent: float, years: int = 30) -> float:
    """Monthly payment that amortises `principal` over `years` at a fixed annual rate."""
    if principal < 0:
        raise ValueError("principal must be non-negative")
    if years <= 0:
        raise ValueError("years must be positive")
    if annual_percent < 0:
        raise ValueError("annual_percent must be non-negative")
    payments = years * 12
    if annual_percent == 0:
        return principal / payments
    monthly_rate = annual_percent / 100 / 12
    growth = (1 + monthly_rate) ** payments
    return principal * monthly_rate * growth / (growth - 1)
