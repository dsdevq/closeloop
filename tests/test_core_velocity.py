"""Pure unit tests for app/core/velocity.py — deal velocity & stage-aging."""
from datetime import datetime, timedelta

import pytest

from app.core.velocity import (
    avg_days_per_stage,
    cycle_time_hours,
    is_deal_rotting,
    stage_sla_days,
    time_in_stage_hours,
)

_NOW = datetime(2024, 6, 1, 12, 0, 0)  # fixed reference point


def _t(to_stage: str, hours_ago: float, from_stage: str | None = None) -> dict:
    occurred = _NOW - timedelta(hours=hours_ago)
    return {"to_stage": to_stage, "from_stage": from_stage, "occurred_at": occurred.isoformat()}


# ── time_in_stage_hours ───────────────────────────────────────────────────────

def test_time_in_stage_returns_hours_since_last_entry():
    trans = [_t("lead", 48)]  # entered 48 hours ago
    result = time_in_stage_hours(trans, "lead", _NOW)
    assert result == pytest.approx(48.0)


def test_time_in_stage_uses_most_recent_entry():
    trans = [_t("lead", 100), _t("lead", 24)]  # re-entered 24h ago
    result = time_in_stage_hours(trans, "lead", _NOW)
    assert result == pytest.approx(24.0)


def test_time_in_stage_wrong_stage_returns_none():
    trans = [_t("lead", 48)]
    assert time_in_stage_hours(trans, "qualified", _NOW) is None


def test_time_in_stage_empty_transitions_returns_none():
    assert time_in_stage_hours([], "lead", _NOW) is None


def test_time_in_stage_zero_when_just_entered():
    trans = [_t("lead", 0)]
    result = time_in_stage_hours(trans, "lead", _NOW)
    assert result == pytest.approx(0.0, abs=0.01)


def test_time_in_stage_handles_tz_aware_timestamps():
    from datetime import timezone
    now_aware = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    trans = [{"to_stage": "lead", "from_stage": None, "occurred_at": "2024-06-01T10:00:00+00:00"}]
    result = time_in_stage_hours(trans, "lead", now_aware)
    assert result == pytest.approx(2.0)


# ── cycle_time_hours ──────────────────────────────────────────────────────────

def test_cycle_time_from_first_transition():
    trans = [_t("lead", 72), _t("qualified", 48), _t("proposal", 24)]
    result = cycle_time_hours(trans, _NOW)
    assert result == pytest.approx(72.0)


def test_cycle_time_empty_returns_none():
    assert cycle_time_hours([], _NOW) is None


def test_cycle_time_single_transition():
    trans = [_t("lead", 10)]
    assert cycle_time_hours(trans, _NOW) == pytest.approx(10.0)


# ── avg_days_per_stage ────────────────────────────────────────────────────────

def _t_at(to_stage: str, dt: datetime, from_stage: str | None = None) -> dict:
    return {"to_stage": to_stage, "from_stage": from_stage, "occurred_at": dt.isoformat()}


def test_avg_days_per_stage_single_deal():
    base = datetime(2024, 1, 1)
    trans = [
        _t_at("lead", base),
        _t_at("qualified", base + timedelta(days=5)),
        _t_at("won", base + timedelta(days=10)),
    ]
    result = avg_days_per_stage([trans])
    assert result["lead"] == pytest.approx(5.0)
    assert result["qualified"] == pytest.approx(5.0)
    assert "won" not in result  # terminal has no exit


def test_avg_days_per_stage_multiple_deals():
    base = datetime(2024, 1, 1)
    deal1 = [
        _t_at("lead", base),
        _t_at("won", base + timedelta(days=4)),
    ]
    deal2 = [
        _t_at("lead", base),
        _t_at("won", base + timedelta(days=8)),
    ]
    result = avg_days_per_stage([deal1, deal2])
    assert result["lead"] == pytest.approx(6.0)  # (4+8)/2


def test_avg_days_per_stage_empty_input():
    assert avg_days_per_stage([]) == {}


def test_avg_days_per_stage_no_terminal_in_result():
    base = datetime(2024, 1, 1)
    trans = [_t_at("won", base)]
    result = avg_days_per_stage([trans])
    assert "won" not in result
    assert "lost" not in result


# ── stage_sla_days ────────────────────────────────────────────────────────────

def test_stage_sla_days_has_open_stages():
    sla = stage_sla_days()
    assert "lead" in sla
    assert "qualified" in sla
    assert "proposal" in sla
    assert "negotiation" in sla


def test_stage_sla_days_no_terminal_stages():
    sla = stage_sla_days()
    assert "won" not in sla
    assert "lost" not in sla


def test_stage_sla_days_returns_copy():
    sla1 = stage_sla_days()
    sla2 = stage_sla_days()
    sla1["lead"] = 9999
    assert sla2["lead"] != 9999


# ── is_deal_rotting ───────────────────────────────────────────────────────────

def test_is_rotting_true_when_over_sla():
    sla = {"lead": 7}
    trans = [_t("lead", 8 * 24)]  # 8 days > 7 days SLA
    assert is_deal_rotting(trans, "lead", _NOW, sla_days=sla) is True


def test_is_rotting_false_when_under_sla():
    sla = {"lead": 7}
    trans = [_t("lead", 6 * 24)]  # 6 days < 7 days SLA
    assert is_deal_rotting(trans, "lead", _NOW, sla_days=sla) is False


def test_is_rotting_false_for_terminal_stage():
    sla = {"lead": 7}
    trans = [_t("won", 100 * 24)]
    assert is_deal_rotting(trans, "won", _NOW, sla_days=sla) is False
    assert is_deal_rotting(trans, "lost", _NOW, sla_days=sla) is False


def test_is_rotting_false_when_no_transition_for_stage():
    sla = {"lead": 7}
    trans = [_t("qualified", 10 * 24)]
    assert is_deal_rotting(trans, "lead", _NOW, sla_days=sla) is False


def test_is_rotting_false_when_stage_not_in_sla():
    # Stage not in the SLA map → never rotting
    trans = [_t("unknown_stage", 100 * 24)]
    assert is_deal_rotting(trans, "unknown_stage", _NOW) is False


def test_is_rotting_uses_default_sla_when_none_provided():
    # Default lead SLA is 7 days; 8 days should be rotting
    trans = [_t("lead", 8 * 24)]
    assert is_deal_rotting(trans, "lead", _NOW) is True


def test_is_rotting_boundary_exactly_at_sla_is_not_rotting():
    # At exactly the SLA threshold (not strictly over), should not rot
    sla = {"lead": 7}
    trans = [_t("lead", 7 * 24)]  # exactly 7 days
    assert is_deal_rotting(trans, "lead", _NOW, sla_days=sla) is False
