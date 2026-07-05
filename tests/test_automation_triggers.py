"""Tests for the scheduled AutomationRule trigger type.

Covers:
  - _parse_schedule_config: valid/invalid interval_minutes, run_once_at, missing config
  - is_due: interval rules (never-fired, before/at/after interval), run_once_at rules
    (before/at/after time, already-fired expiry), unknown kind → False
  - run_scheduled_automations: fires when due, skips when not due, skips malformed
    schedule_config_json (fail-closed), skips missing config, skips inactive rules,
    ignores after_save rules, updates last_triggered_at after firing, handles a mix
    of malformed and valid rules
  - Commit-guard regression: claim is committed even when conditions evaluate false,
    so the next poll cycle does not re-treat the rule as due
  - Concurrency / race condition: two workers racing on the same due rule fire it
    exactly once (CAS claim prevents double-fire)

Fast-forwarding reference time via FixedClock — tests never depend on wall-clock,
per ADR-0006.  No mocking of the database — in-memory SQLite via the `client`
fixture, per ADR-0005.

The fail-closed tests (test_malformed_schedule_config_fails_closed,
test_missing_schedule_config_fails_closed, test_expired_run_once_rule_does_not_refire)
MUST fail on pre-change code (where ScheduleConfigParseError / is_due / trigger_type
do not exist) and pass after.

test_claim_persisted_when_conditions_fail MUST fail against the pre-fix code (where
db.commit() was only called inside 'if fired:' — so a conditions=false outcome rolled
back the CAS claim and re-exposed the rule as due on every poll cycle) and pass after.

test_concurrent_workers_fire_exactly_once MUST fail against code without the CAS
claim (both workers fire the rule → total_fired == 2) and pass after the fix
(CAS rowcount == 0 for the second worker → total_fired == 1).
"""
import threading
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
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
        _parse_schedule_config("not valid json")


def test_parse_schedule_config_array_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config("[1, 2, 3]")


def test_parse_schedule_config_missing_kind_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"foo": "bar"}')


def test_parse_schedule_config_interval_zero_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": 0}')


def test_parse_schedule_config_interval_negative_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": -5}')


def test_parse_schedule_config_interval_float_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": 1.5}')


def test_parse_schedule_config_interval_bool_raises():
    """bool is a subclass of int in Python; True == 1 but must be rejected."""
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"interval_minutes": true}')


def test_parse_schedule_config_valid_interval():
    result = _parse_schedule_config('{"interval_minutes": 60}')
    assert result == {"interval_minutes": 60}


def test_parse_schedule_config_valid_run_once_at():
    result = _parse_schedule_config('{"run_once_at": "2026-01-01T12:00:00"}')
    assert result == {"run_once_at": datetime(2026, 1, 1, 12, 0, 0)}


def test_parse_schedule_config_invalid_run_once_at_raises():
    with pytest.raises(ScheduleConfigParseError):
        _parse_schedule_config('{"run_once_at": "not-a-date"}')


def test_parse_schedule_config_error_is_not_recoverable():
    """ScheduleConfigParseError is a ValueError; callers must not swallow it silently."""
    try:
        _parse_schedule_config(None)
    except ScheduleConfigParseError as exc:
        assert isinstance(exc, ValueError)
    else:
        pytest.fail("Expected ScheduleConfigParseError to be raised")


# ── is_due unit tests ──────────────────────────────────────────────────────────


def test_is_due_interval_never_fired_is_always_due():
    config = {"interval_minutes": 60}
    assert is_due(config, None, _T0) is True


def test_is_due_interval_before_interval_elapsed():
    config = {"interval_minutes": 60}
    last = _T0 - timedelta(minutes=30)
    assert is_due(config, last, _T0) is False


def test_is_due_interval_exactly_at_interval_boundary():
    config = {"interval_minutes": 60}
    last = _T0 - timedelta(minutes=60)
    assert is_due(config, last, _T0) is True


def test_is_due_interval_after_interval_elapsed():
    config = {"interval_minutes": 60}
    last = _T0 - timedelta(minutes=90)
    assert is_due(config, last, _T0) is True


def test_is_due_run_once_before_scheduled_time():
    target = _T0 + timedelta(hours=1)
    config = {"run_once_at": target}
    assert is_due(config, None, _T0) is False


def test_is_due_run_once_at_scheduled_time():
    config = {"run_once_at": _T0}
    assert is_due(config, None, _T0) is True


def test_is_due_run_once_after_scheduled_time():
    target = _T0 - timedelta(hours=1)
    config = {"run_once_at": target}
    assert is_due(config, None, _T0) is True


def test_is_due_run_once_already_fired_is_expired():
    """run_once_at rules are one-shot; once fired they must never re-fire."""
    config = {"run_once_at": _T0 - timedelta(hours=1)}
    last = _T0 - timedelta(minutes=5)
    assert is_due(config, last, _T0) is False


def test_is_due_unknown_kind_returns_false():
    config = {"some_unknown_key": 42}
    assert is_due(config, None, _T0) is False


def test_is_due_handles_timezone_aware_datetimes():
    config = {"interval_minutes": 60}
    last = _T0 - timedelta(minutes=90)
    ref = _T0.replace(tzinfo=timezone.utc)
    assert is_due(config, last, ref) is True


def test_is_due_handles_mixed_naive_aware_datetimes():
    """Naive last_triggered_at with aware reference_time must not crash."""
    config = {"interval_minutes": 60}
    last_naive = datetime(2026, 1, 1, 10, 0, 0)  # no tzinfo
    ref_aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert is_due(config, last_naive, ref_aware) is True


# ── run_scheduled_automations integration tests ────────────────────────────────


def test_scheduled_interval_rule_fires_when_due(client, db_session):
    """A scheduled interval rule with no prior trigger fires on first poll."""
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1
    db_session.refresh(rule)
    assert rule.last_triggered_at == _T0_ISO


def test_scheduled_interval_rule_does_not_fire_before_due(client, db_session):
    """A scheduled interval rule that fired 30 minutes ago is not yet due."""
    last = (_T0 - timedelta(minutes=30)).isoformat()
    _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=last,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_scheduled_interval_rule_fires_after_interval_elapsed(client, db_session):
    """A scheduled interval rule that fired exactly 60 minutes ago is due."""
    last = (_T0 - timedelta(minutes=60)).isoformat()
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=last,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1
    db_session.refresh(rule)
    assert rule.last_triggered_at == _T0_ISO


def test_run_once_rule_fires_at_scheduled_time(client, db_session):
    """A run_once_at rule fires when now >= run_once_at and has not fired before."""
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{_T0_ISO}"}}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 1
    db_session.refresh(rule)
    assert rule.last_triggered_at == _T0_ISO


def test_run_once_rule_does_not_fire_before_time(client, db_session):
    """A run_once_at rule does not fire when now < run_once_at."""
    future = (_T0 + timedelta(hours=1)).isoformat()
    _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{future}"}}',
        last_triggered_at=None,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0


def test_expired_run_once_rule_does_not_refire(client, db_session):
    """A run_once_at rule that has already fired is expired and must not re-fire.

    This is the key one-shot invariant: once last_triggered_at is set the rule
    is permanently expired regardless of how far in the past run_once_at is.
    """
    past = (_T0 - timedelta(hours=2)).isoformat()
    already_fired_at = (_T0 - timedelta(hours=1)).isoformat()
    rule = _seed_scheduled_rule(
        db_session,
        schedule_config_json=f'{{"run_once_at": "{past}"}}',
        last_triggered_at=already_fired_at,
    )
    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))
    assert fired == 0
    db_session.refresh(rule)
    assert rule.last_triggered_at == already_fired_at  # unchanged


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


# ── Commit-guard regression test ──────────────────────────────────────────────


def test_claim_persisted_when_conditions_fail(tmp_path):
    """CAS claim is committed even when conditions evaluate false.

    Regression test for the commit-guard gap closed by the PR #57 audit
    (68fb92bd): run_scheduled_automations originally called db.commit() only
    inside 'if fired:'.  When a due rule had conditions that evaluated false,
    fired stayed 0, so the CAS claim UPDATE (last_triggered_at) was never
    committed and was rolled back when the session closed.  On every subsequent
    poll cycle the rule still appeared due — silently defeating the exactly-once
    guarantee for conditioned scheduled rules.

    Fix: db.commit() is called immediately after rowcount == 1 is confirmed,
    before condition evaluation, so the claim lands in the DB regardless of
    whether the action subsequently fires.

    Uses two independent sessions via a file-based SQLite DB (tmp_path) so
    that session-cache effects cannot mask an uncommitted UPDATE.  The first
    session is closed after the initial poll (its context manager exit triggers
    rollback of any uncommitted transaction), and the second session reads the
    DB from scratch to verify the claim actually landed.

    This test MUST fail against the pre-fix code (claim rolled back → second
    poll re-treats rule as due) and pass after the fix.
    """
    db_path = str(tmp_path / "commit_guard.db")

    setup_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=setup_engine)
    SetupSession = sessionmaker(bind=setup_engine)

    with SetupSession() as s:
        rule = AutomationRule(
            name="Conditions-False Rule",
            trigger_type="scheduled",
            trigger_event="",
            # Condition that never matches: scheduled rules get an empty context,
            # so field-based conditions always evaluate false.
            conditions_json='[{"field": "stage", "op": "eq", "value": "won"}]',
            action_type="notify",
            action_config_json="{}",
            schedule_config_json='{"interval_minutes": 60}',
            last_triggered_at=None,
            is_active=1,
            created_at=_T0_ISO,
        )
        s.add(rule)
        s.commit()
        s.refresh(rule)
        rule_id = rule.id
    setup_engine.dispose()

    clk = FixedClock(_T0)

    # ── Poll 1: rule is due (last_triggered_at=None), but conditions fail ─────
    # Session 1 is opened, the CAS UPDATE is issued, and then the session is
    # closed.  With the fix, db.commit() runs before condition evaluation, so
    # the UPDATE is committed before the session closes.  Without the fix, the
    # UPDATE is only committed inside 'if fired:', which is never reached here,
    # so closing the session rolls it back.
    engine1 = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Session1 = sessionmaker(bind=engine1)
    with Session1() as s1:
        fired1 = run_scheduled_automations(s1, clk=clk)
    engine1.dispose()

    assert fired1 == 0, "conditions evaluate false — no action should fire"

    # ── Verify the claim landed via a fresh session ───────────────────────────
    # A completely independent engine + session ensures we read the actual DB
    # state, not any in-session cached value.
    engine2 = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Session2 = sessionmaker(bind=engine2)
    with Session2() as s2:
        stored = s2.get(AutomationRule, rule_id)
        assert stored.last_triggered_at == _T0_ISO, (
            "last_triggered_at must be committed after the CAS claim even when "
            "conditions evaluate false.  Without the fix, the UPDATE is rolled "
            "back and every subsequent poll re-treats the rule as due."
        )

        # ── Poll 2: rule must NOT be due (60-minute interval, now == _T0) ─────
        # Since last_triggered_at == _T0 and the interval is 60 minutes, the
        # rule is not due at _T0 again.  If the fix is absent (claim not
        # committed), the DB would still show last_triggered_at=NULL and the
        # second poll would (incorrectly) re-claim the rule.
        fired2 = run_scheduled_automations(s2, clk=clk)
    engine2.dispose()

    assert fired2 == 0, (
        "Second poll at the same timestamp must not re-claim the rule — "
        "the committed last_triggered_at means the 60-minute interval has "
        "not elapsed yet."
    )


# ── Concurrency / race condition test ─────────────────────────────────────────


def test_concurrent_workers_fire_exactly_once(tmp_path):
    """CAS claim prevents double-fire when two workers race on the same due rule.

    Simulates the Gunicorn multi-worker race: Gunicorn spawns WEB_CONCURRENCY
    worker processes, each running its own asyncio poller that calls
    run_scheduled_automations() independently.  Both workers can SELECT the same
    due rule (last_triggered_at IS NULL) before either commits the claim.

    Without CAS both workers call _execute_action() → fired == 2 (the bug).
    With CAS the first worker's UPDATE wins; the second gets rowcount == 0 and
    skips → fired == 1 (the fix).

    Uses a file-based SQLite DB (tmp_path) so two independent engine instances
    share the same underlying file and SQLite's write lock serialises concurrent
    updates.  A threading.Barrier(2) ensures both workers enter
    run_scheduled_automations at the same time, maximising the chance that both
    complete their SELECT before either commits the CAS UPDATE.

    This test MUST fail against code without the CAS claim (total_fired == 2)
    and MUST pass after the fix (total_fired == 1).
    Follow-up to the PR #56 audit — closes the multi-worker last_triggered_at
    race condition identified in that review.
    """
    db_path = str(tmp_path / "race.db")

    # Create schema once so both engines see the same tables
    setup_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=setup_engine)

    SetupSession = sessionmaker(bind=setup_engine)
    with SetupSession() as s:
        rule = AutomationRule(
            name="Race Rule",
            trigger_type="scheduled",
            trigger_event="",
            conditions_json=None,
            action_type="notify",
            action_config_json="{}",
            schedule_config_json='{"interval_minutes": 60}',
            last_triggered_at=None,
            is_active=1,
            created_at=_T0_ISO,
        )
        s.add(rule)
        s.commit()
    setup_engine.dispose()

    clk = FixedClock(_T0)
    results: list[int] = []
    errors: list[Exception] = []

    # Barrier ensures both workers enter run_scheduled_automations simultaneously,
    # so both are likely to SELECT the rule before either commits the CAS UPDATE.
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            eng = create_engine(
                f"sqlite:///{db_path}",
                connect_args={"check_same_thread": False, "timeout": 30},
            )
            WorkerSession = sessionmaker(bind=eng)
            with WorkerSession() as s:
                barrier.wait()
                fired = run_scheduled_automations(s, clk=clk)
                results.append(fired)
            eng.dispose()
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    assert not errors, f"Worker thread(s) raised exceptions: {errors}"
    total_fired = sum(results)
    assert total_fired == 1, (
        f"Expected exactly one worker to fire the rule; got {total_fired}. "
        "Without the CAS claim, both workers see last_triggered_at=NULL and both "
        "fire — this is the race condition closed by the compare-and-swap UPDATE."
    )
