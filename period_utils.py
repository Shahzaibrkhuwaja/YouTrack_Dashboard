# period_utils.py
"""
Utilities to resolve period keys into concrete date ranges
and to build YouTrack query fragments for date fields.
"""

from __future__ import annotations
from datetime import date, timedelta
from config import PERIOD_KEYS


# Internal helpers

def _first_day_of_month(d: date) -> date:
    return d.replace(day=1)

def _last_day_of_month(d: date) -> date:
    if d.month == 12:
        nxt = d.replace(year=d.year + 1, month=1, day=1)
    else:
        nxt = d.replace(month=d.month + 1, day=1)
    return nxt - timedelta(days=1)


# Main period resolver (single function to maintain)

def get_period_range(period_key: str, today: date | None = None) -> tuple[date, date]:
    """
    Given a period key (e.g. 'current_month'), return (start_date, end_date) inclusive.
    Based on Created Date semantics (but usable for any date field).
    """
    if today is None:
        today = date.today()

    resolvers = {
        "current_month": lambda d: (
            _first_day_of_month(d),
            _last_day_of_month(d),
        ),
        "previous_month": lambda d: (
            _first_day_of_month((_first_day_of_month(d) - timedelta(days=1))),
            _last_day_of_month((_first_day_of_month(d) - timedelta(days=1))),
        ),
        "last_6_months": lambda d: (
            # first day of month, 5 months ago
            _first_day_of_month(
                date(
                    d.year - ((d.month - 5) <= 0),
                    ((d.month - 5 - 1) % 12) + 1,
                    1,
                )
            ),
            _last_day_of_month(d),
        ),
        "last_1_year": lambda d: (
            # same month last year, first day
            date(d.year - 1, d.month, 1),
            _last_day_of_month(d),
        ),
    }

    if period_key not in resolvers:
        raise ValueError(
            f"Unknown period key: {period_key!r}. Expected one of {PERIOD_KEYS}"
        )

    return resolvers[period_key](today)


# Generic YouTrack query helpers (avoid repeating formatting)

def get_field_period_filter(field: str, period_key: str) -> str:
    """
    Build a YouTrack query fragment for any date field with the given period.
    Example:
        get_field_period_filter("created", "current_month")
        → 'created: {2025-08-01} .. {2025-08-31}'
    """
    start, end = get_period_range(period_key)
    return f"{field}: {{{start.isoformat()}}} .. {{{end.isoformat()}}}"

def get_created_filter(period_key: str) -> str:
    """
    Shortcut for the common case: filter by Created Date.
    Example:
        get_created_filter("previous_month")
        → 'created: {2025-07-01} .. {2025-07-31}'
    """
    return get_field_period_filter("created", period_key)


# Self-test (optional)

if __name__ == "__main__":
    for k in PERIOD_KEYS:
        s, e = get_period_range(k)
        print(f"{k:15} → {s} .. {e} | {get_created_filter(k)}")
