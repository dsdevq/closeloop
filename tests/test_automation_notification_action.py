"""Tests for the 'notify' action type wired into execute_automation_rules and
run_scheduled_automations (app/services/automations.py).

Covers:
  - _parse_notify_config: valid, empty/None, malformed JSON, non-object
  - _resolve_notify_recipient: static recipient_id, dynamic recipient_field,
    missing key, invalid types
  - _execute_notify_action: creates AutomationEvent Notification for resolved
    recipient; suppresses self-notifications; passes actor_id and entity context
    through; no-op on empty config; no-op on malformed config
  - execute_automation_rules integration: conditional rule fires and creates
    the expected Notification row; non-matching conditions produce no notification
  - run_scheduled_automations integration: a due scheduled rule creates a
    Notification row and commits it (actor_id is None — no human actor)

Reference CRMs cited:
  - HubSpot: server-side automation notification (category-keyed, not REST) →
    recipient_id / recipient_field resolution in action_config_json.
  - Salesforce: Custom Notification Type (structured payload, typed event) →
    AutomationEvent dataclass with rule_id / rule_name payload.
  - Attio: actor_id as first-class field on the notification → actor_id from
    context flows to Notification.actor_id; nullable for scheduled (system) rules.
  - Pipedrive: entity_type + entity_id on each notification for frontend
    navigation → context['entity_type'] / context['entity_id'] forwarded.

Rejected patterns (see .devclaw/research/notifications-engine.md §3):
  - Pre-rendered message string: AutomationEvent stores rule_id/rule_name,
    rendered at read time by render_notification().
  - Embedding a domain event type (StageChangedEvent etc.) in the automation
    action — would couple action_config_json to specific domain shapes.
  - Background worker for dispatch — action fires inline in execute_automation_rules,
    same transaction pattern as After-Save triggers in routers/deals.py.

Fast-forwarding reference time via FixedClock (ADR-0006).
No DB mocking — in-memory SQLite via client/db_session fixtures (ADR-0005).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.notifications import AutomationEvent, event_from_payload, render_notification
from app.core.security import hash_password
from app.models import AutomationRule, Notification, User
from app.services.automations import (
    ActionConfigParseError,
    _parse_notify_config,
    _resolve_notify_recipient,
    execute_automation_rules,
    run_scheduled_automations,
)

_T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
_T0_ISO = _T0.isoformat()


class FixedClock:
    """Injected clock with a fixed time — replaces app.core.clock.Clock in tests."""

    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _seed_user(db: Session, *, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("password"),
        role="rep",
        full_name="Test User",
        created_at=_T0_ISO,
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_after_save_rule(
    db: Session,
    *,
    name: str = "Notify Rule",
    trigger_event: str = "deal_stage_changed",
    action_config_json: str = "{}",
    conditions_json: str | None = None,
    is_active: int = 1,
) -> AutomationRule:
    rule = AutomationRule(
        name=name,
        trigger_type="after_save",
        trigger_event=trigger_event,
        conditions_json=conditions_json,
        action_type="notify",
        action_config_json=action_config_json,
        is_active=is_active,
        created_at=_T0_ISO,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _seed_scheduled_rule(
    db: Session,
    *,
    action_config_json: str = "{}",
    conditions_json: str | None = None,
) -> AutomationRule:
    rule = AutomationRule(
        name="Scheduled Notify Rule",
        trigger_type="scheduled",
        trigger_event="",
        conditions_json=conditions_json,
        action_type="notify",
        action_config_json=action_config_json,
        schedule_config_json='{"interval_minutes": 60}',
        last_triggered_at=None,
        is_active=1,
        created_at=_T0_ISO,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _notifications_for(db: Session, recipient_id: int) -> list[Notification]:
    return db.query(Notification).filter_by(recipient_id=recipient_id).all()


# ── _parse_notify_config unit tests ──────────────────────────────────────────


def test_parse_notify_config_none_returns_empty():
    assert _parse_notify_config(None) == {}


def test_parse_notify_config_empty_string_returns_empty():
    assert _parse_notify_config("") == {}


def test_parse_notify_config_whitespace_returns_empty():
    assert _parse_notify_config("   ") == {}


def test_parse_notify_config_empty_object_returns_empty_dict():
    assert _parse_notify_config("{}") == {}


def test_parse_notify_config_recipient_id():
    result = _parse_notify_config('{"recipient_id": 42}')
    assert result == {"recipient_id": 42}


def test_parse_notify_config_recipient_field():
    result = _parse_notify_config('{"recipient_field": "owner_id"}')
    assert result == {"recipient_field": "owner_id"}


def test_parse_notify_config_invalid_json_raises():
    with pytest.raises(ActionConfigParseError):
        _parse_notify_config("not valid json")


def test_parse_notify_config_array_raises():
    with pytest.raises(ActionConfigParseError):
        _parse_notify_config("[1, 2, 3]")


def test_parse_notify_config_scalar_raises():
    with pytest.raises(ActionConfigParseError):
        _parse_notify_config('"just a string"')


def test_parse_notify_config_error_is_value_error():
    with pytest.raises(ActionConfigParseError) as exc_info:
        _parse_notify_config("not valid json")
    assert isinstance(exc_info.value, ValueError)


# ── _resolve_notify_recipient unit tests ──────────────────────────────────────


def test_resolve_recipient_static_id():
    assert _resolve_notify_recipient({"recipient_id": 5}, {}) == 5


def test_resolve_recipient_static_id_zero_rejected():
    assert _resolve_notify_recipient({"recipient_id": 0}, {}) is None


def test_resolve_recipient_static_id_bool_rejected():
    """bool is a subclass of int; True == 1 but must be rejected."""
    assert _resolve_notify_recipient({"recipient_id": True}, {}) is None


def test_resolve_recipient_static_id_negative_rejected():
    assert _resolve_notify_recipient({"recipient_id": -1}, {}) is None


def test_resolve_recipient_static_id_string_rejected():
    assert _resolve_notify_recipient({"recipient_id": "5"}, {}) is None


def test_resolve_recipient_field_from_context():
    context = {"owner_id": 7, "stage": "won"}
    assert _resolve_notify_recipient({"recipient_field": "owner_id"}, context) == 7


def test_resolve_recipient_field_missing_in_context():
    assert _resolve_notify_recipient({"recipient_field": "owner_id"}, {}) is None


def test_resolve_recipient_field_non_integer_in_context():
    assert _resolve_notify_recipient({"recipient_field": "owner_id"}, {"owner_id": "abc"}) is None


def test_resolve_recipient_no_keys_returns_none():
    assert _resolve_notify_recipient({}, {}) is None


def test_resolve_recipient_unknown_key_returns_none():
    assert _resolve_notify_recipient({"something_else": 99}, {}) is None


# ── AutomationEvent render unit test ─────────────────────────────────────────


def test_automation_event_render_notification():
    event = AutomationEvent(rule_id=1, rule_name="My Rule", actor_id=None)
    assert render_notification(event) == 'Automation rule "My Rule" was triggered'


def test_automation_event_round_trip():
    """AutomationEvent serialises and deserialises correctly via event_to_payload."""
    from app.core.notifications import event_to_payload
    event = AutomationEvent(rule_id=3, rule_name="Round Trip Rule", actor_id=5)
    payload = event_to_payload(event)
    recovered = event_from_payload(payload)
    assert isinstance(recovered, AutomationEvent)
    assert recovered.rule_id == 3
    assert recovered.rule_name == "Round Trip Rule"
    assert recovered.actor_id == 5
    assert recovered.kind == "automation"


# ── execute_automation_rules integration tests ────────────────────────────────


def test_notify_action_static_recipient_creates_notification(client, db_session):
    """A rule with recipient_id in action_config_json creates an AutomationEvent row.

    Borrowed: HubSpot automation engine creates in-app notification server-side
    (not via REST endpoint); Salesforce Custom Notification Type carries structured
    typed payload.
    """
    recipient = _seed_user(db_session, email="recip1@test.com")
    rule = _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"stage": "won"},
        clk=FixedClock(_T0),
    )
    db_session.commit()  # caller (router) owns the transaction

    assert fired == 1
    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "automation"
    assert n.read_at is None       # unread on creation
    assert n.actor_id is None      # no actor_id in context

    event = event_from_payload(n.payload_json)
    assert isinstance(event, AutomationEvent)
    assert event.rule_id == rule.id
    assert event.rule_name == rule.name


def test_notify_action_recipient_field_resolves_from_context(client, db_session):
    """recipient_field in config resolves the recipient from the context dict.

    Borrowed: HubSpot 'internal notification' action allows targeting the
    deal owner (a context-resolved field) rather than a hardcoded user.
    """
    recipient = _seed_user(db_session, email="recip2@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json='{"recipient_field": "owner_id"}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"stage": "won", "owner_id": recipient.id},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    assert notifs[0].kind == "automation"


def test_notify_action_actor_id_stored_on_notification(client, db_session):
    """actor_id from context flows through to the Notification row.

    Borrowed: Attio exposes who triggered the notification as a first-class
    field (actor_id); Salesforce surfaces the triggering user on each notification.
    """
    actor = _seed_user(db_session, email="actor@test.com")
    recipient = _seed_user(db_session, email="recip3@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"actor_id": actor.id},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    assert notifs[0].actor_id == actor.id


def test_notify_action_self_notification_suppressed(client, db_session):
    """No notification when actor_id == recipient_id.

    Same suppression guard as the After-Save triggers in app/routers/deals.py
    (Salesforce workflow-rule pattern: avoid pinging yourself).
    """
    user = _seed_user(db_session, email="self@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {user.id}}}',
    )

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"actor_id": user.id},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    assert fired == 1  # rule fired (conditions passed); action suppressed self-notification
    assert _notifications_for(db_session, recipient_id=user.id) == []


def test_notify_action_no_actor_creates_notification(client, db_session):
    """No actor_id in context → notification still created with actor_id=None."""
    recipient = _seed_user(db_session, email="recip4@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={},  # no actor_id — system-level trigger context
        clk=FixedClock(_T0),
    )
    db_session.commit()

    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    assert notifs[0].actor_id is None


def test_notify_action_entity_type_and_id_from_context(client, db_session):
    """entity_type and entity_id from context are stored on the Notification row.

    Borrowed: Pipedrive and Attio include entity_type + entity_id on every
    notification so the frontend can navigate to the correct detail page.
    """
    recipient = _seed_user(db_session, email="recip5@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"entity_type": "deal", "entity_id": 42},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.entity_type == "deal"
    assert n.entity_id == 42


def test_notify_action_empty_config_no_crash_no_notification(client, db_session):
    """Empty action_config_json '{}' → no recipient → no notification and no crash.

    '{}' is the standard test-placeholder value in existing automation tests.
    The rule counts as 'fired' (conditions passed), but the action is a no-op.
    This preserves backward compatibility with all existing test_core_automations.py
    and test_automation_triggers.py fixtures that use action_config_json='{}',
    """
    recipient = _seed_user(db_session, email="recip6@test.com")
    _seed_after_save_rule(db_session, action_config_json="{}")

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    assert fired == 1  # conditions passed; action executed (no-op)
    assert db_session.query(Notification).count() == 0


def test_notify_action_malformed_config_no_crash_no_notification(client, db_session):
    """Malformed action_config_json → action logs warning, no notification, no crash.

    Fail-closed: corrupted JSON must never silently dispatch a notification to an
    unintended recipient (same contract as ConditionsParseError and
    ScheduleConfigParseError for their respective fields).
    """
    _seed_after_save_rule(db_session, action_config_json="not valid json")

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    assert fired == 1  # action_config corruption does not block the fired count
    assert db_session.query(Notification).count() == 0


def test_notify_action_recipient_field_missing_in_context_no_notification(client, db_session):
    """recipient_field not present in context → no notification."""
    _seed_user(db_session, email="recip7@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json='{"recipient_field": "owner_id"}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"stage": "won"},  # owner_id not in context
        clk=FixedClock(_T0),
    )
    db_session.commit()

    assert db_session.query(Notification).count() == 0


def test_notify_conditional_rule_creates_notification_only_when_conditions_match(
    client, db_session
):
    """Conditional notify rule fires (and creates notification) only when conditions match.

    Non-matching context → no notification; matching context → one notification.
    """
    recipient = _seed_user(db_session, email="recip8@test.com")
    _seed_after_save_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
        conditions_json='[{"field": "stage", "op": "eq", "value": "won"}]',
    )

    # Non-matching context → no notification
    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"stage": "lead"},
        clk=FixedClock(_T0),
    )
    db_session.commit()
    assert _notifications_for(db_session, recipient_id=recipient.id) == []

    # Matching context → one notification
    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={"stage": "won"},
        clk=FixedClock(_T0),
    )
    db_session.commit()
    assert len(_notifications_for(db_session, recipient_id=recipient.id)) == 1


def test_notify_action_payload_degradation_guard(client, db_session):
    """AutomationEvent payload stores rule_id and rule_name, not a pre-rendered string.

    Rejected pattern (HubSpot / Pipedrive): storing a pre-rendered message
    in the DB causes stale text if the rule is renamed.  CloseLoop stores the
    structured payload and renders at read time via render_notification().
    """
    recipient = _seed_user(db_session, email="recip9@test.com")
    rule = _seed_after_save_rule(
        db_session,
        name="My Named Rule",
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    execute_automation_rules(
        db_session,
        trigger_event="deal_stage_changed",
        context={},
        clk=FixedClock(_T0),
    )
    db_session.commit()

    n = _notifications_for(db_session, recipient_id=recipient.id)[0]
    event = event_from_payload(n.payload_json)
    # payload carries the structured event, not a string
    assert isinstance(event, AutomationEvent)
    assert event.rule_id == rule.id
    assert event.rule_name == "My Named Rule"
    # render_notification produces the human-readable string at read time
    assert render_notification(event) == 'Automation rule "My Named Rule" was triggered'


# ── run_scheduled_automations integration tests ───────────────────────────────


def test_scheduled_notify_rule_creates_notification(client, db_session):
    """A due scheduled 'notify' rule creates a Notification row when it fires.

    Borrowed: Salesforce Scheduled Actions allow time-based notification dispatch
    without a human actor; CloseLoop mirrors this with actor_id=None for
    system-generated (scheduled) notifications.
    """
    recipient = _seed_user(db_session, email="recip10@test.com")
    _seed_scheduled_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))

    assert fired == 1
    notifs = _notifications_for(db_session, recipient_id=recipient.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "automation"
    assert n.actor_id is None  # scheduled rules have no human actor
    assert n.read_at is None


def test_scheduled_notify_rule_payload_is_automation_event(client, db_session):
    """Notification row from a scheduled rule contains a valid AutomationEvent payload."""
    recipient = _seed_user(db_session, email="recip11@test.com")
    rule = _seed_scheduled_rule(
        db_session,
        action_config_json=f'{{"recipient_id": {recipient.id}}}',
    )

    run_scheduled_automations(db_session, clk=FixedClock(_T0))

    n = _notifications_for(db_session, recipient_id=recipient.id)[0]
    event = event_from_payload(n.payload_json)
    assert isinstance(event, AutomationEvent)
    assert event.rule_id == rule.id
    assert event.rule_name == rule.name
    assert event.actor_id is None


def test_scheduled_notify_rule_empty_config_fires_no_notification(client, db_session):
    """Scheduled rule with '{}' config fires (claims slot) but creates no Notification."""
    _seed_scheduled_rule(db_session, action_config_json="{}")

    fired = run_scheduled_automations(db_session, clk=FixedClock(_T0))

    assert fired == 1  # rule fired and claimed its slot
    assert db_session.query(Notification).count() == 0
