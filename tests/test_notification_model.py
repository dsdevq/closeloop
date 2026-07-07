"""ORM-level unit tests for the Notification model and its state fields.

These tests go directly to the in-memory SQLite DB via db_session (ADR-0005) to
verify field invariants, read/unread state, nullable semantics, and cascade
behaviour — none of which is covered by the API tests in test_notifications.py.

Reference CRM design points exercised here:
  - read_at NULL = unread (HubSpot readAt / Attio pattern — NOT a boolean flag)
  - actor_id nullable for system-generated events (TaskOverdueEvent has no actor)
  - entity_type / entity_id nullable for system events (no linked entity)
  - ON DELETE CASCADE on recipient_id (user gone → all their notifications gone)
  - ON DELETE SET NULL on actor_id (actor gone → notification remains, actor cleared)
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.core.notifications import (
    DealAssignedEvent,
    MentionEvent,
    StageChangedEvent,
    TaskOverdueEvent,
    event_to_payload,
)
from app.core.security import hash_password
from app.models import Notification, User


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_user(db, *, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("pw"),
        role="rep",
        full_name="Test User",
        created_at=_now(),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_notification(
    db,
    *,
    recipient_id: int,
    event=None,
    actor_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    read_at: str | None = None,
) -> Notification:
    if event is None:
        event = DealAssignedEvent(deal_id=1, deal_title="Deal", actor_id=actor_id or 0)
    n = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        kind=event.kind,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=event_to_payload(event),
        read_at=read_at,
        created_at=_now(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


# ── Default unread state ──────────────────────────────────────────────────────


class TestReadAtField:
    def test_new_notification_is_unread_by_default(self, client, db_session):
        """read_at defaults to NULL — the unread indicator (HubSpot/Attio pattern)."""
        user = _seed_user(db_session, email="recv1@example.com")
        n = _seed_notification(db_session, recipient_id=user.id)
        assert n.read_at is None

    def test_setting_read_at_marks_notification_read(self, client, db_session):
        """Assigning an ISO-8601 string to read_at marks the notification as read."""
        user = _seed_user(db_session, email="recv2@example.com")
        n = _seed_notification(db_session, recipient_id=user.id)
        read_ts = "2026-07-05T12:00:00+00:00"
        n.read_at = read_ts
        db_session.commit()
        db_session.refresh(n)
        assert n.read_at == read_ts

    def test_read_at_is_not_a_boolean_column(self, client, db_session):
        """read_at stores the timestamp, not a boolean — enables read-time ordering."""
        user = _seed_user(db_session, email="recv3@example.com")
        ts = "2026-07-05T08:30:00"
        n = _seed_notification(db_session, recipient_id=user.id, read_at=ts)
        # Round-trip: the stored value is the exact string, not True/1
        assert isinstance(n.read_at, str)
        assert n.read_at == ts

    def test_unread_filter_uses_is_null(self, client, db_session):
        """WHERE read_at IS NULL returns only unread rows."""
        user = _seed_user(db_session, email="recv4@example.com")
        n_unread = _seed_notification(db_session, recipient_id=user.id)
        _seed_notification(db_session, recipient_id=user.id, read_at=_now())

        unread = (
            db_session.query(Notification)
            .filter(
                Notification.recipient_id == user.id,
                Notification.read_at.is_(None),
            )
            .all()
        )
        assert len(unread) == 1
        assert unread[0].id == n_unread.id


# ── actor_id: nullable for system events ─────────────────────────────────────


class TestActorId:
    def test_actor_id_nullable_for_system_events(self, client, db_session):
        """TaskOverdueEvent has no human actor; actor_id must be storable as NULL."""
        user = _seed_user(db_session, email="sysrec@example.com")
        event = TaskOverdueEvent(
            activity_id=10, activity_title="Call", due_at="2026-07-01T09:00:00"
        )
        n = _seed_notification(db_session, recipient_id=user.id, event=event, actor_id=None)
        assert n.actor_id is None

    def test_actor_id_set_for_user_triggered_events(self, client, db_session):
        """actor_id is populated when a human user is the source of the event."""
        actor = _seed_user(db_session, email="actor1@example.com")
        recip = _seed_user(db_session, email="recip1@example.com")
        event = DealAssignedEvent(deal_id=5, deal_title="Test", actor_id=actor.id)
        n = _seed_notification(
            db_session, recipient_id=recip.id, event=event, actor_id=actor.id
        )
        assert n.actor_id == actor.id


# ── entity_type / entity_id: nullable for system events ──────────────────────


class TestEntityFields:
    def test_entity_fields_nullable_for_system_events(self, client, db_session):
        """System events (e.g. TaskOverdueEvent) have no linked entity in the CRM."""
        user = _seed_user(db_session, email="sysent@example.com")
        event = TaskOverdueEvent(
            activity_id=3, activity_title="Follow up", due_at="2026-07-02T10:00:00"
        )
        n = _seed_notification(
            db_session, recipient_id=user.id, event=event,
            entity_type=None, entity_id=None,
        )
        assert n.entity_type is None
        assert n.entity_id is None

    def test_entity_fields_stored_for_deal_linked_events(self, client, db_session):
        """Deal-linked events carry entity_type='deal' and entity_id=<deal_pk>."""
        actor = _seed_user(db_session, email="actor2@example.com")
        recip = _seed_user(db_session, email="recip2@example.com")
        event = StageChangedEvent(
            deal_id=99, deal_title="Deal Y", actor_id=actor.id,
            from_stage="Prospecting", to_stage="Proposal",
        )
        n = _seed_notification(
            db_session, recipient_id=recip.id, event=event,
            actor_id=actor.id, entity_type="deal", entity_id=99,
        )
        assert n.entity_type == "deal"
        assert n.entity_id == 99

    def test_entity_fields_stored_for_activity_linked_events(self, client, db_session):
        """Activity-linked events carry entity_type='activity'."""
        actor = _seed_user(db_session, email="actor3@example.com")
        recip = _seed_user(db_session, email="recip3@example.com")
        event = MentionEvent(
            actor_id=actor.id, entity_type="activity", entity_id=7,
            snippet="take a look",
        )
        n = _seed_notification(
            db_session, recipient_id=recip.id, event=event,
            actor_id=actor.id, entity_type="activity", entity_id=7,
        )
        assert n.entity_type == "activity"
        assert n.entity_id == 7


# ── kind and payload_json fields ──────────────────────────────────────────────


class TestKindAndPayload:
    def test_kind_matches_event_kind(self, client, db_session):
        """kind column stores the exact Literal string from the event dataclass."""
        user = _seed_user(db_session, email="kind1@example.com")
        n = _seed_notification(
            db_session,
            recipient_id=user.id,
            event=DealAssignedEvent(deal_id=1, deal_title="X", actor_id=1),
        )
        assert n.kind == "deal_assigned"

    def test_all_four_kinds_round_trip(self, client, db_session):
        """Each of the four notification kinds persists and round-trips correctly."""
        user = _seed_user(db_session, email="kinds@example.com")
        events = [
            DealAssignedEvent(deal_id=1, deal_title="D", actor_id=1),
            StageChangedEvent(deal_id=2, deal_title="D", actor_id=1, from_stage="A", to_stage="B"),
            TaskOverdueEvent(activity_id=3, activity_title="T", due_at="2026-07-01T00:00:00"),
            MentionEvent(actor_id=1, entity_type="deal", entity_id=4, snippet="hi"),
        ]
        expected_kinds = {"deal_assigned", "stage_changed", "task_overdue", "mention"}
        stored_kinds = set()
        for ev in events:
            n = _seed_notification(db_session, recipient_id=user.id, event=ev)
            stored_kinds.add(n.kind)
        assert stored_kinds == expected_kinds

    def test_payload_json_is_stored_as_string(self, client, db_session):
        """payload_json is a TEXT column; round-trip preserves the JSON string."""
        user = _seed_user(db_session, email="payload@example.com")
        event = DealAssignedEvent(deal_id=42, deal_title="Acme", actor_id=7)
        expected_payload = event_to_payload(event)
        n = _seed_notification(db_session, recipient_id=user.id, event=event)
        assert n.payload_json == expected_payload


# ── recipient_id: ON DELETE CASCADE ──────────────────────────────────────────


class TestCascadeOnRecipientDelete:
    def test_notifications_deleted_when_recipient_is_deleted(self, client, db_session):
        """ON DELETE CASCADE: deleting the recipient removes their notifications."""
        user = _seed_user(db_session, email="cascade@example.com")
        uid = user.id
        _seed_notification(db_session, recipient_id=uid)
        _seed_notification(db_session, recipient_id=uid)

        before = db_session.query(Notification).filter_by(recipient_id=uid).count()
        assert before == 2

        db_session.delete(user)
        db_session.commit()

        after = db_session.query(Notification).filter_by(recipient_id=uid).count()
        assert after == 0

    def test_other_users_notifications_unaffected_by_recipient_delete(
        self, client, db_session
    ):
        """Cascade only removes the deleted user's notifications."""
        user_a = _seed_user(db_session, email="ca@example.com")
        user_b = _seed_user(db_session, email="cb@example.com")
        _seed_notification(db_session, recipient_id=user_a.id)
        n_b = _seed_notification(db_session, recipient_id=user_b.id)

        db_session.delete(user_a)
        db_session.commit()

        remaining = db_session.query(Notification).all()
        assert len(remaining) == 1
        assert remaining[0].id == n_b.id


# ── actor_id: ON DELETE SET NULL ─────────────────────────────────────────────


class TestSetNullOnActorDelete:
    def test_actor_id_set_null_when_actor_is_deleted(self, client, db_session):
        """ON DELETE SET NULL: deleting the actor clears actor_id, notification survives."""
        actor = _seed_user(db_session, email="actor_del@example.com")
        recip = _seed_user(db_session, email="recip_del@example.com")
        event = DealAssignedEvent(deal_id=1, deal_title="D", actor_id=actor.id)
        n = _seed_notification(
            db_session, recipient_id=recip.id, event=event, actor_id=actor.id
        )
        nid = n.id

        db_session.delete(actor)
        db_session.commit()

        surviving = db_session.get(Notification, nid)
        assert surviving is not None, "notification must survive actor deletion"
        assert surviving.actor_id is None


# ── Multiple notifications per recipient ──────────────────────────────────────


class TestMultipleNotifications:
    def test_recipient_can_have_many_notifications(self, client, db_session):
        """A single recipient can accumulate multiple notification rows."""
        user = _seed_user(db_session, email="multi@example.com")
        for i in range(5):
            _seed_notification(db_session, recipient_id=user.id)
        count = db_session.query(Notification).filter_by(recipient_id=user.id).count()
        assert count == 5

    def test_unread_count_is_independent_per_recipient(self, client, db_session):
        """Unread count query is scoped per-recipient; rows of other users don't bleed."""
        user_a = _seed_user(db_session, email="ua@example.com")
        user_b = _seed_user(db_session, email="ub@example.com")
        _seed_notification(db_session, recipient_id=user_a.id)
        _seed_notification(db_session, recipient_id=user_a.id)
        _seed_notification(db_session, recipient_id=user_b.id, read_at=_now())

        count_a = (
            db_session.query(Notification)
            .filter(Notification.recipient_id == user_a.id, Notification.read_at.is_(None))
            .count()
        )
        count_b = (
            db_session.query(Notification)
            .filter(Notification.recipient_id == user_b.id, Notification.read_at.is_(None))
            .count()
        )
        assert count_a == 2
        assert count_b == 0
