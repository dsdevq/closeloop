"""RRULE-lite recurrence engine.

Supported rule shape::

    {"freq": "daily"|"weekly"|"monthly", "interval": 1, "count": N}

- ``freq``: recurrence frequency — ``daily``, ``weekly``, or ``monthly``.
- ``interval``: step between occurrences (default 1). E.g. interval=2 with
  freq=weekly means every two weeks.
- ``count``: maximum number of occurrences to generate (default 1).

Month arithmetic: the next occurrence is computed by advancing the month by
``interval``, clamping the day to the last day of the target month to avoid
invalid dates (e.g. Jan 31 + 1 month → Feb 28/29).
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

_SUPPORTED_FREQS = {"daily", "weekly", "monthly"}


def expand_rrule(rule: dict, start: datetime, count: int) -> list[datetime]:
    """
    Generate ``count`` future occurrences after ``start`` from ``rule``.

    Returns a list of ``datetime`` objects (same tzinfo as ``start``).
    Raises ``ValueError`` for unknown freq or invalid interval/count.
    Validation always runs, even when count=0.
    """
    freq = rule.get("freq", "")
    if freq not in _SUPPORTED_FREQS:
        raise ValueError(f"unsupported freq: {freq!r}; must be one of {sorted(_SUPPORTED_FREQS)}")

    interval = int(rule.get("interval", 1))
    if interval <= 0:
        raise ValueError(f"interval must be a positive integer, got {interval}")

    if count <= 0:
        return []

    results: list[datetime] = []
    current = start

    for _ in range(count):
        current = _advance(current, freq, interval)
        results.append(current)

    return results


def _advance(dt: datetime, freq: str, interval: int) -> datetime:
    if freq == "daily":
        return dt + timedelta(days=interval)
    if freq == "weekly":
        return dt + timedelta(weeks=interval)
    # monthly: advance by interval months, clamping day to month-end
    month = dt.month + interval
    year = dt.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    max_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, max_day)
    return dt.replace(year=year, month=month, day=day)
