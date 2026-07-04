"""Integration tests for check_scheduled_rules in app/services/automations.py.

These tests exercise the full scan→due-check→execute→update cycle using the
in-memory SQLite DB (ADR-0005) shared by the client/db_session fixtures.
A FixedClock controls reference_time so timing assertions are deterministic.

Scheduling shape follows Salesforce Flow scheduled actions / HubSpot Workflows
delay-scheduling per .devclaw/research/workflow-automation.md §2.1-2.2.

Test axes:
  1. Timing      — fires when due, skips when not due
  2. Fail-closed — NULL/malformed schedule_config_json, corrupted last_fired_at,
                   inactive rules, and after_save rules are never executed
  3. Action      — notify_user action writes a Notification row; unknown kinds
                   don't; last_fired_at is updated to the reference time
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.automations import ScheduleConfig, schedule_config_to_json
from app.core.clock import Clock
from app.models import AutomationRule, Notification, User
from app.services.automations import check_scheduled_rules

_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


class FixedClock(Clock):
    """Clock that always returns one fixed datetime — keeps tests deterministic."""

    def __init__(self, dt: datetime) -> None:
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def _now_str() -> str:
    return datetime.now(_UTC).isoformat()


def _interval_cfg(interval_days: int = 7) -> str:
    return schedule_config_to_json(ScheduleConfig(mode="interval", interval_days=interval_days))


def _seed_rule(
    db: Session,
    *,
    name: str = "test-rule",
    trigger_type: str = "scheduled",
    is_active: int = 1,
    schedule_config_json: str | None = None,
    action_config: dict | None = None,
    last_fired_at: datetime | None = None,
) -> AutomationRule:
    """Insert an AutomationRule row and return it (commits so it is visible to queries)."""
    if schedule_config_json is None and trigger_type == "scheduled":
        schedule_config_json = _interval_cfg()
    if action_config is None:
        action_config = {"kind": "noop"}

    now = _now_str()
    rule = AutomationRule(
        name=name,
        entity_type="deal",
        trigger_type=trigger_type,
        is_active=is_active,
        conditions_json="[]",
        action_config_json=json.dumps(action_config),
        schedule_config_json=schedule_config_json,
        last_fired_at=last_fired_at.isoformat() if last_fired_at else None,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ---------------------------------------------------------------------------
# 1. Timing — fires when due, skips when not due
# ---------------------------------------------------------------------------


class TestScheduledRulesTiming:
    def test_never_fired_rule_fires_on_first_scan(self, client, db_session):
        """Interval rule with last_fired_at=None fires immediately — never-fired is always due."""
        rule = _seed_rule(db_session, last_fired_at=None)
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 1
        # last_fired_at must be updated to the reference time
        db_session.expire(rule)
        assert rule.last_fired_at is not None
        assert datetime.fromisoformat(rule.last_fired_at) == clk.now()

    def test_rule_not_due_is_skipped(self, client, db_session):
        """Rule with last_fired_at only 3 days ago (interval=7) is not yet due."""
        last = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        rule = _seed_rule(db_session, last_fired_at=last)
        original_ts = rule.last_fired_at
        # Only 3 days later — interval hasn't elapsed
        clk = FixedClock(last + timedelta(days=3))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0
        db_session.expire(rule)
        # last_fired_at must be unchanged
        assert rule.last_fired_at == original_ts

    def test_rule_fires_exactly_at_interval_boundary(self, client, db_session):
        """Rule fires when reference_time == last_fired_at + interval_days (inclusive boundary)."""
        last = datetime(2026, 6, 27, 12, 0, 0, tzinfo=_UTC)
        rule = _seed_rule(db_session, last_fired_at=last)
        clk = FixedClock(last + timedelta(days=7))  # exactly at boundary

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 1
        db_session.expire(rule)
        assert datetime.fromisoformat(rule.last_fired_at) == clk.now()

    def test_rule_not_due_one_second_before_boundary(self, client, db_session):
        """One second before the boundary the rule must not fire."""
        last = datetime(2026, 6, 27, 12, 0, 0, tzinfo=_UTC)
        _seed_rule(db_session, last_fired_at=last)
        clk = FixedClock(last + timedelta(days=7) - timedelta(seconds=1))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_inactive_rule_is_never_scanned(self, client, db_session):
        """is_active=0 rules are excluded from the query and never fire."""
        _seed_rule(db_session, is_active=0, last_fired_at=None)
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_multiple_due_rules_all_fire(self, client, db_session):
        """All due rules are fired in a single scan pass."""
        for i in range(3):
            _seed_rule(db_session, name=f"rule-{i}", last_fired_at=None)
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 3

    def test_only_due_rules_fire_in_mixed_set(self, client, db_session):
        """Due and not-due rules coexist — only the due rule fires."""
        last = datetime(2026, 7, 1, 12, 0, 0, tzinfo=_UTC)
        _seed_rule(db_session, name="due", last_fired_at=None)
        _seed_rule(db_session, name="not-due", last_fired_at=last)
        # 3 days after last — "not-due" interval (7 days) not elapsed
        clk = FixedClock(last + timedelta(days=3))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 1


# ---------------------------------------------------------------------------
# 2. Fail-closed — malformed / missing config → no execution
# ---------------------------------------------------------------------------


class TestScheduledRulesFailClosed:
    def test_null_schedule_config_json_skipped(self, client, db_session):
        """schedule_config_json=NULL on a scheduled rule → fail-closed, never fires."""
        rule = AutomationRule(
            name="null-config",
            entity_type="deal",
            trigger_type="scheduled",
            is_active=1,
            conditions_json="[]",
            action_config_json=json.dumps({"kind": "noop"}),
            schedule_config_json=None,  # explicitly NULL
            last_fired_at=None,
            created_at=_now_str(),
            updated_at=_now_str(),
        )
        db_session.add(rule)
        db_session.commit()
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_malformed_schedule_config_skipped(self, client, db_session):
        """schedule_config_json with missing required field → silently skipped."""
        # interval mode without interval_days — ScheduleConfig.__post_init__ will raise
        _seed_rule(db_session, schedule_config_json='{"mode": "interval"}')
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_invalid_json_in_schedule_config_skipped(self, client, db_session):
        """schedule_config_json containing syntactically invalid JSON → skipped."""
        _seed_rule(db_session, schedule_config_json="{not valid json")
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_corrupted_last_fired_at_skipped(self, client, db_session):
        """Rule with non-ISO last_fired_at is skipped rather than firing incorrectly."""
        now_str = _now_str()
        cfg = ScheduleConfig(mode="interval", interval_days=1)
        rule = AutomationRule(
            name="corrupted-ts",
            entity_type="deal",
            trigger_type="scheduled",
            is_active=1,
            conditions_json="[]",
            action_config_json=json.dumps({"kind": "noop"}),
            schedule_config_json=schedule_config_to_json(cfg),
            last_fired_at="not-a-timestamp",
            created_at=now_str,
            updated_at=now_str,
        )
        db_session.add(rule)
        db_session.commit()

        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))
        fired = check_scheduled_rules(db_session, clk)
        assert fired == 0

    def test_after_save_rule_never_scanned(self, client, db_session):
        """after_save rules are not included in the scheduled-rule query."""
        _seed_rule(db_session, trigger_type="after_save", schedule_config_json=None)
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0

    def test_empty_set_returns_zero(self, client, db_session):
        """No scheduled rules in DB → scanner returns 0, no errors."""
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 0


# ---------------------------------------------------------------------------
# 3. Action — execution effects and last_fired_at bookkeeping
# ---------------------------------------------------------------------------


class TestScheduledRulesAction:
    def test_notify_user_action_creates_notification_row(self, client, db_session):
        """notify_user action inserts a Notification row for the given recipient."""
        admin = db_session.query(User).first()
        rule = _seed_rule(
            db_session,
            action_config={"kind": "notify_user", "recipient_id": admin.id},
        )
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        check_scheduled_rules(db_session, clk)

        notifs = (
            db_session.query(Notification)
            .filter(
                Notification.recipient_id == admin.id,
                Notification.kind == "automation_fired",
            )
            .all()
        )
        assert len(notifs) == 1
        assert notifs[0].entity_type == "automation_rule"
        assert notifs[0].entity_id == rule.id

    def test_unknown_action_kind_no_notification(self, client, db_session):
        """Unknown action kind is silently skipped — no Notification row created."""
        _seed_rule(db_session, action_config={"kind": "send_carrier_pigeon"})
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        # Rule counts as fired (last_fired_at fenced) but no notification emitted
        assert fired == 1
        assert db_session.query(Notification).count() == 0

    def test_notify_user_missing_recipient_id_no_notification(self, client, db_session):
        """notify_user without recipient_id is a no-op — rule fires but no row created."""
        _seed_rule(db_session, action_config={"kind": "notify_user"})
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 1
        assert db_session.query(Notification).count() == 0

    def test_notify_user_nonexistent_recipient_no_notification(self, client, db_session):
        """notify_user with a recipient_id that doesn't exist creates no Notification."""
        _seed_rule(db_session, action_config={"kind": "notify_user", "recipient_id": 99999})
        clk = FixedClock(datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC))

        fired = check_scheduled_rules(db_session, clk)

        assert fired == 1
        assert db_session.query(Notification).count() == 0

    def test_last_fired_at_updated_to_reference_time(self, client, db_session):
        """last_fired_at is set to exactly the clock's reference time after firing."""
        rule = _seed_rule(db_session, last_fired_at=None)
        ref = datetime(2026, 7, 4, 15, 30, 45, tzinfo=_UTC)
        clk = FixedClock(ref)

        check_scheduled_rules(db_session, clk)

        db_session.expire(rule)
        assert datetime.fromisoformat(rule.last_fired_at) == ref

    def test_fired_rule_does_not_re_fire_before_next_interval(self, client, db_session):
        """After firing, last_fired_at prevents the rule from firing again until interval elapses."""
        rule = _seed_rule(db_session, last_fired_at=None)
        ref = datetime(2026, 7, 4, 12, 0, 0, tzinfo=_UTC)

        # First scan — fires
        fired1 = check_scheduled_rules(db_session, FixedClock(ref))
        assert fired1 == 1

        # Second scan at same time — interval not elapsed, must not fire again
        fired2 = check_scheduled_rules(db_session, FixedClock(ref))
        assert fired2 == 0
