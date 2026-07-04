"""Tests for the scheduled AutomationRule trigger type.

Covers:
  - _parse_schedule_config: valid/invalid interval_minutes, run_once_at, missing config
  - is_due: interval rules (never-fired, before/at/after interval), run_once_at rules
    (before/at/after time, already-fired expiry), unknown kind → False
  - run_scheduled_automations: fires when due, skips when not due, skips malformed
    schedule_config_json (fail-closed), skips missing config, skips inactive rules,
    ignores after_save rules, updates last_triggered_at after firing, handles a mix
    of malformed and valid rules

Fast-forwarding reference time via FixedClock — tests never depend on wall-clock,
per ADR-0006.  No mocking of the database — in-memory SQLite via the `client`
fixture, per ADR-0005.

The fail-closed tests (test_malformed_schedule_config_fails_closed,
test_missing_schedule_config_fails_closed, test_expired_run_once_rule_does_not_refire)
MUST fail on pre-change code (where ScheduleConfigParseError / is_due / trigger_type
do not exist) and pass after.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import AutomationRule
from app.services.automations import (
    ScheduleConfigParseError,
    _parse_schedule_config,
    is_due,
    run_scheduled_automations,
)

# ── Fixed reference datetimes (timezone-aware UTC) used across all tests ──────

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_T0_ISO = _T0.isoformat()


class FixedClock:
    """Injected clock with a fixed time — replaces app.core.clock.Clock in tests."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


def _seed_scheduled_rule(
    db: Session,
    *,
    name: str = "Test Scheduled Rule",
    schedule_config_json: str | None = None,
    last_triggered_at: str | None = None,
    conditions_json: str | None = None,
    is_active: int = 1,
) -> AutomationRule:
    rule = AutomationRule(
        name=name,
        trigger_type="scheduled",
        trigger_event="",  # unused for scheduled rules
        conditions_json=conditions_json,
        action_type="notify",
        action_config_json="{}",
        schedule_config_json=schedule_config_json,
        last_triggered_at=last_triggered_at,
        is_active=is_active,
        created_at=_T0_ISO,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ── _parse_schedule_config unit tests ─────────────────────────────────────────


def test_parse_schedule_config_none_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config(None)


def test_parse_schedule_config_empty_string_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config("")


def test_parse_schedule_config_whitespace_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config("   ")


def test_parse_schedule_config_invalid_json_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config("not json")


def test_parse_schedule_config_array_raises():
    """JSON array is not a valid schedule config object."""
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('["interval_minutes", 60]')


def test_parse_schedule_config_missing_kind_raises():
    """Object without interval_minutes or run_once_at raises."""
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"unknown_key": 60}')


def test_parse_schedule_config_interval_zero_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": 0}')


def test_parse_schedule_config_interval_negative_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": -10}')


def test_parse_schedule_config_interval_float_raises():
    """Fractional minutes must be rejected — must be a whole positive integer."""
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": 1.5}')


def test_parse_schedule_config_valid_interval():
    result = _parse_schedule_config('{"interval_minutes": 60}')
    assert result == {"interval_minutes": 60}


def test_parse_schedule_config_valid_run_once_at():
    result = _parse_schedule_config('{"run_once_at": "2026-07-10T00:00:00+00:00"}')
    assert "run_once_at" in result
    assert isinstance(result["run_once_at"], datetime)


def test_parse_schedule_config_invalid_run_once_at_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"run_once_at": "not-a-datetime"}')


def test_parse_schedule_config_error_is_not_recoverable():
    """Callers must not be able to silently recover from a parse error by
    treating None or [] as a valid schedule — ScheduleConfigParseError is the
    only signal."""
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config("{{corrupt}}")


# ── is_due unit tests ──────────────────────────────────────────────────────────


def test_is_due_interval_never_fired_is_always_due():
    """A never-fired interval rule is immediately due on the first poll."""
    config = {"interval_minutes": 60}
    assert is_due(config, None, _T0) is True


def test_is_due_interval_before_interval_elapsed():
    """Not due if < interval minutes have passed since last fire."""
    config = {"interval_minutes": 60}
    last = _T0
    ref = _T0 + timedelta(minutes=30)
    assert is_due(config, last, ref) is False


def test_is_due_interval_exactly_at_interval_boundary():
    """Due at exactly the interval boundary (>=, not >)."""
    config = {"interval_minutes": 60}
    last = _T0
    ref = _T0 + timedelta(minutes=60)
    assert is_due(config, last, ref) is True


def test_is_due_interval_after_interval_elapsed():
    """Due when more than interval minutes have passed."""
    config = {"interval_minutes": 60}
    last = _T0
    ref = _T0 + timedelta(minutes=90)
    assert is_due(config, last, ref) is True


def test_is_due_run_once_before_scheduled_time():
    """run_once_at rule is not due before its scheduled time."""
    target = _T0 + timedelta(hours=2)
    config = {"run_once_at": target}
    assert is_due(config, None, _T0) is False


def test_is_due_run_once_at_scheduled_time():
    """run_once_at rule is due at exactly its scheduled time."""
    config = {"run_once_at": _T0}
    assert is_due(config, None, _T0) is True


def test_is_due_run_once_after_scheduled_time():
    """run_once_at rule is due when polled after the scheduled time (late poll)."""
    target = _T0
    config = {"run_once_at": target}
    ref = _T0 + timedelta(hours=1)
    assert is_due(config, None, ref) is True


def test_is_due_run_once_already_fired_is_expired():
    """A run_once_at rule that already fired must never fire again (expired)."""
    config = {"run_once_at": _T0}
    last = _T0  # already fired at T0
    ref = _T0 + timedelta(hours=1)
    assert is_due(config, last, ref) is False


def test_is_due_unknown_kind_returns_false():
    """An unrecognised schedule kind is never due (safe default)."""
    config = {"weekly": True}
    assert is_due(config, None, _T0) is False


def test_is_due_handles_timezone_aware_datetimes():
    """is_due correctly compares timezone-aware datetimes without raising."""
    config = {"interval_minutes": 60}
    last = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    ref = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
    assert is_due(config, last, ref) is True


def test_is_due_handles_mixed_naive_aware_datetimes():
    """is_due normalises tz-aware and tz-naive datetimes so comparison never raises."""
    config = {"interval_minutes": 60}
    last_naive = datetime(2026, 1, 1, 11, 0, 0)  # naive
    ref_aware = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)
    assert is_due(config, last_naive, ref_aware) is True


# ── run_scheduled_automations integration tests ───────────────────────────────


def test_scheduled_interval_rule_fires_when_due(client, db_session):
    """A never-fired interval rule fires immediately on the first poll."""
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1
    db_session.refresh(rule)
    assert rule.last_triggered_at is not None


def test_scheduled_interval_rule_does_not_fire_before_due(client, db_session):
    """An interval rule does not fire if the interval has not elapsed."""
    last_fire = (_T0 - timedelta(minutes=30)).isoformat()
    _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=last_fire,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_scheduled_interval_rule_fires_after_interval_elapsed(client, db_session):
    """An interval rule fires once the interval has elapsed since last fire."""
    last_fire = (_T0 - timedelta(minutes=61)).isoformat()
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=last_fire,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1
    db_session.refresh(rule)
    assert rule.last_triggered_at == _T0_ISO


def test_run_once_rule_fires_at_scheduled_time(client, db_session):
    """A run_once_at rule fires when reference_time >= run_once_at."""
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{_T0_ISO}"}}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1


def test_run_once_rule_does_not_fire_before_time(client, db_session):
    """A run_once_at rule does not fire before its scheduled time."""
    future = (_T0 + timedelta(hours=2)).isoformat()
    _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{future}"}}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_expired_run_once_rule_does_not_refire(client, db_session):
    """An expired run_once_at rule (last_triggered_at set) never re-fires.

    This is the critical guard for one-shot scheduled rules: once fired, the
    rule must be treated as expired and skipped on all subsequent polls even
    if the reference time is past the run_once_at time.
    """
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{_T0_ISO}"}}',
        last_triggered_at=_T0_ISO,  # already fired
    )
    later = _T0 + timedelta(hours=1)
    fired = run_scheduled_automations(db_session, clk=FixedClock(later))
    assert fired == 0, (
        "An expired run_once_at rule must never re-fire. "
        "If this fails, is_due() is not checking last_triggered_at for one-shot rules."
    )


def test_malformed_schedule_config_fails_closed(client, db_session):
    """A scheduled rule with malformed schedule_config_json is skipped — fail-closed.

    This is the critical guard for the scheduled trigger path, mirroring the
    malformed-conditions_json test for after_save rules (PR #53).
    """
    _seed_scheduled_rule(db_session, schedule_config_json="not valid json")
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0, (
        "A rule with malformed schedule_config_json must be skipped, not fired. "
        "If this fails, _parse_schedule_config is not raising ScheduleConfigParseError."
    )


def test_missing_schedule_config_fails_closed(client, db_session):
    """A scheduled rule with no schedule_config_json is skipped — fail-closed."""
    _seed_scheduled_rule(db_session, schedule_config_json=None)
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0, (
        "A scheduled rule with schedule_config_json=NULL must be skipped, not fired."
    )


def test_inactive_scheduled_rule_never_fires(client, db_session):
    """Inactive scheduled rules are always skipped regardless of timing."""
    _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        is_active=0,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_after_save_rules_not_evaluated_by_scheduler(client, db_session):
    """run_scheduled_automations must ignore after_save rules."""
    rule = AutomationRule(
        name="After-Save Rule",
        trigger_type="after_save",
        trigger_event="deal.stage_changed",
        conditions_json=None,
        action_type="notify",
        action_config_json="{}",
        schedule_config_json=None,
        last_triggered_at=None,
        is_active=1,
        created_at=_T0_ISO,
    )
    db_session.add(rule)
    db_session.commit()

    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_scheduler_updates_last_triggered_at(client, db_session):
    """After a rule fires, last_triggered_at is persisted to the DB."""
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=None,
    )
    run_scheduled_automations(db_session, clk=FixedClock(_T0))
    db_session.refresh(rule)
    assert rule.last_triggered_at == _T0_ISO


def test_mixed_malformed_and_valid_scheduled_rules(client, db_session):
    """Only the valid rule fires when one scheduled rule is malformed."""
    _seed_scheduled_rule(db_session, name="Malformed", schedule_config_json="{{bad}}")
    _seed_scheduled_rule(
        db_session,
        name="Good",
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1


def test_unconditional_scheduled_rule_fires(client, db_session):
    """A scheduled rule with conditions_json=NULL fires unconditionally."""
    _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        conditions_json=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1


def test_scheduled_rule_with_field_condition_and_empty_context_skips(client, db_session):
    """A scheduled rule with entity-field conditions does not fire (empty context).

    Scheduled rules currently receive an empty context dict — field-level conditions
    (e.g. stage == won) will never match.  This is the expected fail-safe behaviour
    for slice 2; entity scanning is deferred to a future slice.
    """
    _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        conditions_json='[{"field": "stage", "op": "eq", "value": "won"}]',
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0
