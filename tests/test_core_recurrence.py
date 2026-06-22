"""Pure unit tests for the RRULE-lite recurrence engine."""
from datetime import datetime

import pytest

from app.core.recurrence import expand_rrule


_START = datetime(2024, 1, 15, 9, 0, 0)  # Monday 2024-01-15


def test_count_zero_returns_empty():
    assert expand_rrule({"freq": "daily", "interval": 1}, _START, 0) == []


def test_daily_single_occurrence():
    result = expand_rrule({"freq": "daily", "interval": 1}, _START, 1)
    assert result == [datetime(2024, 1, 16, 9, 0, 0)]


def test_daily_multiple_occurrences():
    result = expand_rrule({"freq": "daily", "interval": 1}, _START, 3)
    assert result == [
        datetime(2024, 1, 16, 9, 0, 0),
        datetime(2024, 1, 17, 9, 0, 0),
        datetime(2024, 1, 18, 9, 0, 0),
    ]


def test_daily_interval_two():
    result = expand_rrule({"freq": "daily", "interval": 2}, _START, 2)
    assert result == [
        datetime(2024, 1, 17, 9, 0, 0),
        datetime(2024, 1, 19, 9, 0, 0),
    ]


def test_weekly_single():
    result = expand_rrule({"freq": "weekly", "interval": 1}, _START, 1)
    assert result == [datetime(2024, 1, 22, 9, 0, 0)]


def test_weekly_multiple():
    result = expand_rrule({"freq": "weekly", "interval": 1}, _START, 3)
    assert result == [
        datetime(2024, 1, 22, 9, 0, 0),
        datetime(2024, 1, 29, 9, 0, 0),
        datetime(2024, 2, 5, 9, 0, 0),
    ]


def test_weekly_interval_two():
    result = expand_rrule({"freq": "weekly", "interval": 2}, _START, 2)
    assert result == [
        datetime(2024, 1, 29, 9, 0, 0),
        datetime(2024, 2, 12, 9, 0, 0),
    ]


def test_monthly_single():
    result = expand_rrule({"freq": "monthly", "interval": 1}, _START, 1)
    assert result == [datetime(2024, 2, 15, 9, 0, 0)]


def test_monthly_multiple():
    result = expand_rrule({"freq": "monthly", "interval": 1}, _START, 3)
    assert result == [
        datetime(2024, 2, 15, 9, 0, 0),
        datetime(2024, 3, 15, 9, 0, 0),
        datetime(2024, 4, 15, 9, 0, 0),
    ]


def test_monthly_day_clamp_jan31():
    """Jan 31 + 1 month → Feb 28 (non-leap 2023)."""
    start = datetime(2023, 1, 31, 0, 0, 0)
    result = expand_rrule({"freq": "monthly", "interval": 1}, start, 1)
    assert result == [datetime(2023, 2, 28, 0, 0, 0)]


def test_monthly_day_clamp_leap_year():
    """Jan 31 + 1 month → Feb 29 in leap year 2024."""
    start = datetime(2024, 1, 31, 0, 0, 0)
    result = expand_rrule({"freq": "monthly", "interval": 1}, start, 1)
    assert result == [datetime(2024, 2, 29, 0, 0, 0)]


def test_monthly_year_rollover():
    """Dec 15 + 1 month → Jan 15 next year."""
    start = datetime(2024, 12, 15, 0, 0, 0)
    result = expand_rrule({"freq": "monthly", "interval": 1}, start, 2)
    assert result[0] == datetime(2025, 1, 15, 0, 0, 0)
    assert result[1] == datetime(2025, 2, 15, 0, 0, 0)


def test_monthly_interval_three():
    start = datetime(2024, 1, 1, 0, 0, 0)
    result = expand_rrule({"freq": "monthly", "interval": 3}, start, 2)
    assert result == [
        datetime(2024, 4, 1, 0, 0, 0),
        datetime(2024, 7, 1, 0, 0, 0),
    ]


def test_invalid_freq_raises():
    with pytest.raises(ValueError, match="unsupported freq"):
        expand_rrule({"freq": "hourly", "interval": 1}, _START, 1)


def test_zero_interval_raises():
    with pytest.raises(ValueError, match="interval must be a positive integer"):
        expand_rrule({"freq": "daily", "interval": 0}, _START, 1)


def test_negative_interval_raises():
    with pytest.raises(ValueError, match="interval must be a positive integer"):
        expand_rrule({"freq": "daily", "interval": -1}, _START, 1)


def test_default_interval_is_one():
    """When interval key is absent, defaults to 1."""
    result = expand_rrule({"freq": "daily"}, _START, 1)
    assert result == [datetime(2024, 1, 16, 9, 0, 0)]
