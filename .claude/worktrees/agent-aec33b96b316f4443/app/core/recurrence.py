"""
Pure-function recurrence expansion for activity scheduling.

Supported frequencies: DAILY, WEEKLY, MONTHLY.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from calendar import monthrange


_VALID_FREQS = {"DAILY", "WEEKLY", "MONTHLY"}


def _add_months(dt: datetime, months: int) -> datetime:
    """Add ``months`` to ``dt``, clamping the day to the last valid day."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


def expand_recurrence(
    freq: str,
    interval: int,
    from_dt: datetime,
    until: datetime | None = None,
    count: int | None = None,
) -> list[datetime]:
    """
    Expand a recurrence rule into a list of datetimes.

    Parameters
    ----------
    freq:
        One of ``DAILY``, ``WEEKLY``, ``MONTHLY``.
    interval:
        Number of freq-units between occurrences (must be >= 1).
    from_dt:
        First occurrence (included in output).
    until:
        Upper bound (inclusive).  At least one of ``until``/``count`` required.
    count:
        Maximum number of occurrences to return.

    Raises
    ------
    ValueError
        If ``freq`` is unknown, ``interval`` < 1, or neither ``until`` nor
        ``count`` is supplied.
    """
    if freq not in _VALID_FREQS:
        raise ValueError(f"unknown recurrence freq: {freq!r}; must be one of {sorted(_VALID_FREQS)}")
    if interval < 1:
        raise ValueError(f"interval must be >= 1, got {interval!r}")
    if until is None and count is None:
        raise ValueError("at least one of 'until' or 'count' must be supplied")

    occurrences: list[datetime] = []
    current = from_dt
    idx = 0

    while True:
        # Check count limit
        if count is not None and idx >= count:
            break
        # Check until limit
        if until is not None and current > until:
            break

        occurrences.append(current)
        idx += 1

        # Advance to next occurrence
        if freq == "DAILY":
            current = current + timedelta(days=interval)
        elif freq == "WEEKLY":
            current = current + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            current = _add_months(current, interval)

    return occurrences
