"""Pure unit tests for app/core/automations.py.

No DB fixtures needed — all functions are pure and operate on plain values.
Tests cover ScheduleConfig validation, JSON round-trips, and is_rule_due()
timing logic for both interval and field_offset modes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.automations import (
    SCHEDULE_MODE_FIELD_OFFSET,
    SCHEDULE_MODE_INTERVAL,
    TRIGGER_AFTER_SAVE,
    TRIGGER_SCHEDULED,
    VALID_SCHEDULE_MODES,
    VALID_TRIGGER_TYPES,
    ScheduleConfig,
    is_rule_due,
    schedule_config_from_json,
    schedule_config_to_json,
)


# ── Constants ─────────────────────────────────────────────────────────────────


def test_valid_trigger_types_contains_expected():
    assert VALID_TRIGGER_TYPES == frozenset({"after_save", "scheduled"})


def test_valid_schedule_modes_contains_expected():
    assert VALID_SCHEDULE_MODES == frozenset({"interval", "field_offset"})


# ── ScheduleConfig — interval mode ────────────────────────────────────────────


class TestScheduleConfigInterval:
    def test_valid_interval_config(self):
        cfg = ScheduleConfig(mode="interval", interval_days=7)
        assert cfg.mode == SCHEDULE_MODE_INTERVAL
        assert cfg.interval_days == 7
        assert cfg.anchor_field is None
        assert cfg.offset_days is None

    def test_interval_requires_interval_days(self):
        with pytest.raises(ValueError, match="interval_days"):
            ScheduleConfig(mode="interval")

    def test_interval_days_must_be_positive(self):
        with pytest.raises(ValueError, match="interval_days"):
            ScheduleConfig(mode="interval", interval_days=0)

    def test_interval_days_must_be_at_least_one(self):
        with pytest.raises(ValueError, match="interval_days"):
            ScheduleConfig(mode="interval", interval_days=-3)

    def test_interval_days_one_is_valid(self):
        cfg = ScheduleConfig(mode="interval", interval_days=1)
        assert cfg.interval_days == 1


# ── ScheduleConfig — field_offset mode ───────────────────────────────────────


class TestScheduleConfigFieldOffset:
    def test_valid_field_offset_positive(self):
        cfg = ScheduleConfig(
            mode="field_offset", anchor_field="expected_close_date", offset_days=7
        )
        assert cfg.anchor_field == "expected_close_date"
        assert cfg.offset_days == 7

    def test_valid_field_offset_negative(self):
        cfg = ScheduleConfig(
            mode="field_offset", anchor_field="expected_close_date", offset_days=-3
        )
        assert cfg.offset_days == -3

    def test_valid_field_offset_zero(self):
        cfg = ScheduleConfig(
            mode="field_offset", anchor_field="expected_close_date", offset_days=0
        )
        assert cfg.offset_days == 0

    def test_field_offset_requires_anchor_field(self):
        with pytest.raises(ValueError, match="anchor_field"):
            ScheduleConfig(mode="field_offset", offset_days=7)

    def test_field_offset_empty_anchor_field_rejected(self):
        with pytest.raises(ValueError, match="anchor_field"):
            ScheduleConfig(mode="field_offset", anchor_field="", offset_days=7)

    def test_field_offset_requires_offset_days(self):
        with pytest.raises(ValueError, match="offset_days"):
            ScheduleConfig(mode="field_offset", anchor_field="expected_close_date")


# ── ScheduleConfig — unknown mode ─────────────────────────────────────────────


def test_schedule_config_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown schedule mode"):
        ScheduleConfig(mode="cron")  # type: ignore[arg-type]


# ── schedule_config_to_json / schedule_config_from_json ───────────────────────


class TestScheduleConfigJsonRoundTrip:
    def test_interval_round_trip(self):
        original = ScheduleConfig(mode="interval", interval_days=14)
        restored = schedule_config_from_json(schedule_config_to_json(original))
        assert restored.mode == "interval"
        assert restored.interval_days == 14
        assert restored.anchor_field is None
        assert restored.offset_days is None

    def test_field_offset_round_trip(self):
        original = ScheduleConfig(
            mode="field_offset", anchor_field="expected_close_date", offset_days=-5
        )
        restored = schedule_config_from_json(schedule_config_to_json(original))
        assert restored.mode == "field_offset"
        assert restored.anchor_field == "expected_close_date"
        assert restored.offset_days == -5
        assert restored.interval_days is None

    def test_from_json_malformed_json_raises(self):
        with pytest.raises(ValueError, match="invalid schedule config JSON"):
            schedule_config_from_json("{not valid}")

    def test_from_json_non_string_raises(self):
        with pytest.raises(ValueError, match="invalid schedule config JSON"):
            schedule_config_from_json(None)  # type: ignore[arg-type]

    def test_from_json_missing_required_field_raises(self):
        # interval mode missing interval_days
        with pytest.raises(ValueError, match="malformed schedule config"):
            schedule_config_from_json('{"mode": "interval"}')

    def test_from_json_unknown_mode_raises(self):
        with pytest.raises(ValueError, match="malformed schedule config"):
            schedule_config_from_json('{"mode": "cron", "interval_days": null, "anchor_field": null, "offset_days": null}')


# ── is_rule_due — interval mode ───────────────────────────────────────────────

_UTC = timezone.utc


class TestIsRuleDueInterval:
    def _cfg(self, interval_days: int = 7) -> ScheduleConfig:
        return ScheduleConfig(mode="interval", interval_days=interval_days)

    def test_never_fired_is_always_due(self):
        cfg = self._cfg()
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC)
        assert is_rule_due(cfg, now, last_fired_at=None) is True

    def test_not_due_when_interval_not_elapsed(self):
        cfg = self._cfg(interval_days=7)
        last = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        now = last + timedelta(days=3)  # only 3 days later
        assert is_rule_due(cfg, now, last_fired_at=last) is False

    def test_due_exactly_at_interval_boundary(self):
        cfg = self._cfg(interval_days=7)
        last = datetime(2026, 6, 27, 12, 0, 0, tzinfo=_UTC)
        now = last + timedelta(days=7)  # exactly 7 days later
        assert is_rule_due(cfg, now, last_fired_at=last) is True

    def test_due_after_interval_elapsed(self):
        cfg = self._cfg(interval_days=7)
        last = datetime(2026, 6, 20, 12, 0, 0, tzinfo=_UTC)
        now = last + timedelta(days=10)  # 10 days later, more than 7
        assert is_rule_due(cfg, now, last_fired_at=last) is True

    def test_not_due_one_second_before_boundary(self):
        cfg = self._cfg(interval_days=7)
        last = datetime(2026, 6, 27, 12, 0, 0, tzinfo=_UTC)
        now = last + timedelta(days=7) - timedelta(seconds=1)
        assert is_rule_due(cfg, now, last_fired_at=last) is False


# ── is_rule_due — field_offset mode ──────────────────────────────────────────


class TestIsRuleDueFieldOffset:
    def _cfg(self, offset_days: int, anchor: str = "expected_close_date") -> ScheduleConfig:
        return ScheduleConfig(
            mode="field_offset", anchor_field=anchor, offset_days=offset_days
        )

    def test_due_when_offset_passed(self):
        cfg = self._cfg(offset_days=3)
        anchor = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        now = anchor + timedelta(days=4)  # 1 day after offset
        assert is_rule_due(cfg, now, anchor_field_value=anchor) is True

    def test_not_due_before_offset(self):
        cfg = self._cfg(offset_days=3)
        anchor = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        now = anchor + timedelta(days=2)  # 1 day before offset
        assert is_rule_due(cfg, now, anchor_field_value=anchor) is False

    def test_due_at_exact_boundary(self):
        cfg = self._cfg(offset_days=3)
        anchor = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        now = anchor + timedelta(days=3)  # exactly at offset
        assert is_rule_due(cfg, now, anchor_field_value=anchor) is True

    def test_negative_offset_before_anchor(self):
        cfg = self._cfg(offset_days=-3)
        anchor = datetime(2026, 7, 10, 12, 0, 0, tzinfo=_UTC)
        # Due 3 days BEFORE anchor: anchor - 3 = 2026-07-07
        now_due = anchor - timedelta(days=3)
        now_early = anchor - timedelta(days=4)
        assert is_rule_due(cfg, now_due, anchor_field_value=anchor) is True
        assert is_rule_due(cfg, now_early, anchor_field_value=anchor) is False

    def test_field_offset_requires_anchor_field_value(self):
        cfg = self._cfg(offset_days=3)
        now = datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC)
        with pytest.raises(ValueError, match="anchor_field_value"):
            is_rule_due(cfg, now)  # no anchor_field_value supplied
