"""Direct unit tests for app/services/notifications.py.

`create_notification` and `resolve_mentioned_users` are tested here with the
in-memory SQLite via db_session (ADR-0005 — no DB mocking).  The trigger
wiring in test_notification_triggers.py and test_mention_triggers.py exercises
these functions end-to-end through the API; these tests exercise the service
contract directly.

Delivery model recap (notifications-engine.md §3 / ADR-0025):
  - create_notification() is the single dispatch entry point. It calls db.add()
    but does NOT commit — caller owns the transaction (same pattern as
    record_history() in app/services/history.py and execute_automation_rules()
    in app/services/automations.py).
  - resolve_mentioned_users() is the I/O counterpart to the pure parse_mentions():
    it maps @token strings to active User rows by ILIKE against email local-part.

Reference CRM patterns:
  - Attio: actor_id derived from the event's structured payload, nullable for
    system-generated events (TaskOverdueEvent has no human actor).
  - Salesforce: notification creation is an internal operation, never a public
    REST endpoint.
  - Zoho: @mention token matched case-insensitively against user identity.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.notifications import (
    DealAssignedEvent,
    MentionEvent,
    StageChangedEvent,
    TaskOverdueEvent,
    event_from_payload,
)
from app.core.security import hash_password
from app.models import Notification, User
from app.services.notifications import create_notification, resolve_mentioned_users


# ── Fixed reference time (ADR-0006: injected clock) ──────────────────────────

_T0 = datetime(2026, 7, 5, 12, 0, 0, tzinfo=timezone.utc)
_T0_ISO = _T0.isoformat()


class FixedClock:
    """Minimal Clock implementation with a pinned time for deterministic tests."""

    def __init__(self, fixed: datetime = _T0) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _seed_user(db: Session, *, email: str, is_active: int = 1) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("pw"),
        role="rep",
        full_name="Test User",
        created_at=_T0_ISO,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── create_notification ───────────────────────────────────────────────────────


class TestCreateNotification:
    def test_returns_notification_with_correct_kind(self, client, db_session):
        """The returned Notification's kind matches the event's kind field."""
        actor = _seed_user(db_session, email="actor_r1@example.com")
        recip = _seed_user(db_session, email="r1@example.com")
        event = DealAssignedEvent(deal_id=5, deal_title="Acme", actor_id=actor.id)
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type="deal",
            entity_id=5,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.kind == "deal_assigned"

    def test_recipient_id_set_correctly(self, client, db_session):
        recip = _seed_user(db_session, email="r2@example.com")
        event = StageChangedEvent(
            deal_id=3, deal_title="Deal X", actor_id=1,
            from_stage="Prospecting", to_stage="Proposal",
        )
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type="deal",
            entity_id=3,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.recipient_id == recip.id

    def test_actor_id_derived_from_event_for_user_triggered_event(self, client, db_session):
        """Attio pattern: actor_id is set from event.actor_id, not from a separate argument."""
        actor = _seed_user(db_session, email="actor@example.com")
        recip = _seed_user(db_session, email="recip@example.com")
        event = DealAssignedEvent(deal_id=7, deal_title="Deal Y", actor_id=actor.id)
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type="deal",
            entity_id=7,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.actor_id == actor.id

    def test_actor_id_none_for_system_event(self, client, db_session):
        """TaskOverdueEvent has no human actor (no actor_id field) → actor_id is NULL.

        Attio: system-generated notifications have actor_id=None.
        """
        recip = _seed_user(db_session, email="sysrecip@example.com")
        event = TaskOverdueEvent(
            activity_id=10, activity_title="Follow up", due_at="2026-07-05T09:00:00"
        )
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type=None,
            entity_id=None,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.actor_id is None

    def test_entity_type_and_entity_id_stored(self, client, db_session):
        """entity_type and entity_id are persisted verbatim — Pipedrive / Attio pattern."""
        recip = _seed_user(db_session, email="ent@example.com")
        event = MentionEvent(actor_id=1, entity_type="activity", entity_id=42, snippet="hi")
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type="activity",
            entity_id=42,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.entity_type == "activity"
        assert n.entity_id == 42

    def test_entity_fields_none_for_system_events(self, client, db_session):
        recip = _seed_user(db_session, email="sysent2@example.com")
        event = TaskOverdueEvent(
            activity_id=3, activity_title="Call", due_at="2026-07-05T00:00:00"
        )
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type=None,
            entity_id=None,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.entity_type is None
        assert n.entity_id is None

    def test_created_at_matches_injected_clock(self, client, db_session):
        """ADR-0006: created_at is set from the injected clock, never from wall time."""
        recip = _seed_user(db_session, email="clk@example.com")
        event = DealAssignedEvent(deal_id=1, deal_title="D", actor_id=1)
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            clk=FixedClock(_T0),
        )
        db_session.commit()
        assert n.created_at == _T0_ISO

    def test_payload_json_round_trips(self, client, db_session):
        """The payload_json stored in the row is a valid serialised event."""
        actor = _seed_user(db_session, email="actor_payload@example.com")
        recip = _seed_user(db_session, email="payload@example.com")
        event = StageChangedEvent(
            deal_id=99, deal_title="Mega Deal", actor_id=actor.id,
            from_stage="Qualification", to_stage="Proposal",
        )
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            entity_type="deal",
            entity_id=99,
            clk=FixedClock(),
        )
        db_session.commit()
        reconstructed = event_from_payload(n.payload_json)
        assert reconstructed == event

    def test_read_at_is_null_on_creation(self, client, db_session):
        """New notifications are unread: read_at is NULL (HubSpot/Attio pattern)."""
        recip = _seed_user(db_session, email="unread@example.com")
        event = DealAssignedEvent(deal_id=2, deal_title="D2", actor_id=1)
        n = create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            clk=FixedClock(),
        )
        db_session.commit()
        assert n.read_at is None

    def test_does_not_commit(self, client, db_session):
        """create_notification calls db.add() but does NOT commit — caller owns the
        transaction.  Rolling back after the call must leave no notification rows.

        This is the same contract as record_history() and execute_automation_rules():
        all three are written before the single db.commit() in the route handler.
        """
        recip = _seed_user(db_session, email="nocommit@example.com")
        event = DealAssignedEvent(deal_id=3, deal_title="Rollback Deal", actor_id=1)
        create_notification(
            db_session,
            recipient_id=recip.id,
            event=event,
            clk=FixedClock(),
        )
        # Rollback without committing — notification must not be persisted
        db_session.rollback()

        count = db_session.query(Notification).filter_by(recipient_id=recip.id).count()
        assert count == 0

    def test_multiple_notifications_for_same_recipient(self, client, db_session):
        """Each create_notification call adds an independent row — no upsert."""
        recip = _seed_user(db_session, email="multi@example.com")
        event_a = DealAssignedEvent(deal_id=1, deal_title="D1", actor_id=1)
        event_b = StageChangedEvent(
            deal_id=2, deal_title="D2", actor_id=1,
            from_stage="A", to_stage="B",
        )
        create_notification(db_session, recipient_id=recip.id, event=event_a, clk=FixedClock())
        create_notification(db_session, recipient_id=recip.id, event=event_b, clk=FixedClock())
        db_session.commit()

        rows = db_session.query(Notification).filter_by(recipient_id=recip.id).all()
        assert len(rows) == 2
        kinds = {r.kind for r in rows}
        assert kinds == {"deal_assigned", "stage_changed"}


# ── resolve_mentioned_users ───────────────────────────────────────────────────


class TestResolveMentionedUsers:
    def test_empty_tokens_returns_empty_list(self, client, db_session):
        """No tokens → empty result without any DB query."""
        result = resolve_mentioned_users(db_session, [])
        assert result == []

    def test_resolves_token_by_email_local_part(self, client, db_session):
        """@alice resolves to the user with email alice@closeloop.com.

        Zoho @mention / Salesforce Chatter pattern: token is matched against the
        local part of User.email (the portion before the first '@').
        """
        alice = _seed_user(db_session, email="alice@closeloop.com")
        result = resolve_mentioned_users(db_session, ["alice"])
        assert len(result) == 1
        assert result[0].id == alice.id

    def test_resolution_is_case_insensitive(self, client, db_session):
        """@ALICE resolves to alice@closeloop.com (ILIKE match)."""
        alice = _seed_user(db_session, email="alice2@closeloop.com")
        result = resolve_mentioned_users(db_session, ["ALICE2"])
        assert len(result) == 1
        assert result[0].id == alice.id

    def test_unknown_token_silently_skipped(self, client, db_session):
        """A token with no matching active user is silently skipped."""
        result = resolve_mentioned_users(db_session, ["nobody_here"])
        assert result == []

    def test_inactive_user_not_resolved(self, client, db_session):
        """is_active=0 users are excluded from resolution — no ping to deactivated accounts."""
        _seed_user(db_session, email="inactive@closeloop.com", is_active=0)
        result = resolve_mentioned_users(db_session, ["inactive"])
        assert result == []

    def test_multiple_unique_tokens_resolved(self, client, db_session):
        """Multiple tokens resolve to their respective users in token order."""
        alice = _seed_user(db_session, email="alice3@closeloop.com")
        bob = _seed_user(db_session, email="bob3@closeloop.com")
        result = resolve_mentioned_users(db_session, ["alice3", "bob3"])
        assert len(result) == 2
        assert result[0].id == alice.id
        assert result[1].id == bob.id

    def test_duplicate_token_returns_user_once(self, client, db_session):
        """A token appearing twice in the list resolves to the user only once."""
        alice = _seed_user(db_session, email="alice4@closeloop.com")
        result = resolve_mentioned_users(db_session, ["alice4", "alice4"])
        assert len(result) == 1
        assert result[0].id == alice.id

    def test_token_order_preserved(self, client, db_session):
        """Users are returned in the same order as their corresponding tokens."""
        alice = _seed_user(db_session, email="alice5@closeloop.com")
        bob = _seed_user(db_session, email="bob5@closeloop.com")
        result_ab = resolve_mentioned_users(db_session, ["alice5", "bob5"])
        result_ba = resolve_mentioned_users(db_session, ["bob5", "alice5"])
        assert result_ab[0].id == alice.id
        assert result_ab[1].id == bob.id
        assert result_ba[0].id == bob.id
        assert result_ba[1].id == alice.id

    def test_mix_of_known_and_unknown_tokens(self, client, db_session):
        """Unknown tokens are skipped; known tokens still resolve."""
        alice = _seed_user(db_session, email="alice6@closeloop.com")
        result = resolve_mentioned_users(db_session, ["nobody", "alice6", "ghost"])
        assert len(result) == 1
        assert result[0].id == alice.id
