"""API integration tests for GET /notifications pull endpoints.

Notifications are created by inserting Notification rows directly via the
db_session fixture (trigger wiring belongs to a later slice).
All API calls go through the standard client fixture (authenticated as admin).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.notifications import (
    DealAssignedEvent,
    MentionEvent,
    StageChangedEvent,
    TaskOverdueEvent,
    event_to_payload,
)
from app.core.security import hash_password
from app.models import Notification, User


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_notification(
    db: Session,
    *,
    recipient_id: int,
    event,
    actor_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    read_at: str | None = None,
    created_at: str | None = None,
) -> Notification:
    n = Notification(
        recipient_id=recipient_id,
        actor_id=actor_id,
        kind=event.kind,
        entity_type=entity_type,
        entity_id=entity_id,
        payload_json=event_to_payload(event),
        read_at=read_at,
        created_at=created_at or _now(),
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


def _deal_assigned_event() -> DealAssignedEvent:
    return DealAssignedEvent(deal_id=1, deal_title="Big Deal", actor_id=2)


def _stage_event() -> StageChangedEvent:
    return StageChangedEvent(
        deal_id=1,
        deal_title="Big Deal",
        actor_id=2,
        from_stage="Qualification",
        to_stage="Proposal",
    )


def _task_event() -> TaskOverdueEvent:
    return TaskOverdueEvent(
        activity_id=5,
        activity_title="Follow up call",
        due_at="2026-07-01T09:00:00",
    )


def _mention_event() -> MentionEvent:
    return MentionEvent(actor_id=3, entity_type="deal", entity_id=7, snippet="check this")


# ── GET /notifications/unread-count ──────────────────────────────────────────


def test_unread_count_zero_when_no_notifications(client, db_session):
    # admin user has no notifications at all
    db_session  # ensure fixture is active
    r = client.get("/notifications/unread-count")
    assert r.status_code == 200
    assert r.json() == {"unread_count": 0}


def test_unread_count_reflects_unread_notifications(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_deal_assigned_event())
    _seed_notification(db_session, recipient_id=admin_id, event=_stage_event())
    r = client.get("/notifications/unread-count")
    assert r.json()["unread_count"] == 2


def test_unread_count_excludes_read_notifications(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(
        db_session,
        recipient_id=admin_id,
        event=_deal_assigned_event(),
        read_at=_now(),
    )
    _seed_notification(db_session, recipient_id=admin_id, event=_stage_event())
    r = client.get("/notifications/unread-count")
    assert r.json()["unread_count"] == 1


# ── GET /notifications ────────────────────────────────────────────────────────


def test_list_returns_empty_when_no_notifications(client, db_session):
    db_session  # active
    r = client.get("/notifications")
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_own_notifications(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_deal_assigned_event())
    r = client.get("/notifications")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["kind"] == "deal_assigned"
    assert "message" in data[0]
    assert data[0]["message"] != ""


def test_list_does_not_return_other_users_notifications(client, db_session):
    """Admin's list must not include notifications for a different recipient."""
    admin_id = _get_admin_id(client)
    other_user = _seed_user(db_session, email="other@example.com")
    # Only seed a notification for the OTHER user
    _seed_notification(db_session, recipient_id=other_user.id, event=_deal_assigned_event())
    r = client.get("/notifications")
    # Admin has no notifications, other_user's row must not appear
    assert r.json() == []


def test_list_includes_multiple_kinds(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_deal_assigned_event())
    _seed_notification(db_session, recipient_id=admin_id, event=_stage_event())
    _seed_notification(db_session, recipient_id=admin_id, event=_task_event())
    _seed_notification(db_session, recipient_id=admin_id, event=_mention_event())
    data = client.get("/notifications").json()
    kinds = {n["kind"] for n in data}
    assert kinds == {"deal_assigned", "stage_changed", "task_overdue", "mention"}


def test_list_ordered_newest_first(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(
        db_session, recipient_id=admin_id, event=_deal_assigned_event(),
        created_at="2026-07-01T10:00:00",
    )
    _seed_notification(
        db_session, recipient_id=admin_id, event=_stage_event(),
        created_at="2026-07-01T12:00:00",
    )
    data = client.get("/notifications").json()
    assert data[0]["kind"] == "stage_changed"
    assert data[1]["kind"] == "deal_assigned"


def test_list_unread_only_excludes_read(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(
        db_session, recipient_id=admin_id, event=_deal_assigned_event(),
        read_at=_now(),
    )
    _seed_notification(db_session, recipient_id=admin_id, event=_stage_event())
    data = client.get("/notifications?unread_only=true").json()
    assert len(data) == 1
    assert data[0]["kind"] == "stage_changed"


def test_list_unread_only_false_returns_all(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_deal_assigned_event(), read_at=_now())
    _seed_notification(db_session, recipient_id=admin_id, event=_stage_event())
    data = client.get("/notifications?unread_only=false").json()
    assert len(data) == 2


def test_list_limit_caps_results(client, db_session):
    admin_id = _get_admin_id(client)
    for _ in range(5):
        _seed_notification(db_session, recipient_id=admin_id, event=_task_event())
    data = client.get("/notifications?limit=3").json()
    assert len(data) == 3


def test_list_limit_zero_returns_422(client, db_session):
    r = client.get("/notifications?limit=0")
    assert r.status_code == 422


def test_list_response_shape(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(
        db_session,
        recipient_id=admin_id,
        event=_deal_assigned_event(),
        actor_id=admin_id,
        entity_type="deal",
        entity_id=1,
    )
    n = client.get("/notifications").json()[0]
    assert set(n.keys()) == {"id", "kind", "entity_type", "entity_id", "actor_id", "message", "read_at", "created_at"}
    assert n["read_at"] is None
    assert n["entity_type"] == "deal"
    assert n["entity_id"] == 1
    assert n["actor_id"] == admin_id


# ── POST /notifications/{id}/read ─────────────────────────────────────────────


def test_mark_read_sets_read_at(client, db_session):
    admin_id = _get_admin_id(client)
    n = _seed_notification(db_session, recipient_id=admin_id, event=_deal_assigned_event())
    r = client.post(f"/notifications/{n.id}/read")
    assert r.status_code == 200
    data = r.json()
    assert data["read_at"] is not None
    assert data["id"] == n.id


def test_mark_read_idempotent(client, db_session):
    admin_id = _get_admin_id(client)
    first_read_at = "2026-07-01T10:00:00"
    n = _seed_notification(
        db_session, recipient_id=admin_id, event=_deal_assigned_event(),
        read_at=first_read_at,
    )
    r = client.post(f"/notifications/{n.id}/read")
    assert r.status_code == 200
    # read_at must not be changed for an already-read notification
    assert r.json()["read_at"] == first_read_at


def test_mark_read_404_for_missing_notification(client):
    r = client.post("/notifications/99999/read")
    assert r.status_code == 404


def test_mark_read_404_for_other_users_notification(client, db_session):
    other_user = _seed_user(db_session, email="other2@example.com")
    n = _seed_notification(db_session, recipient_id=other_user.id, event=_task_event())
    # Authenticated as admin; other_user's notification must not be accessible
    r = client.post(f"/notifications/{n.id}/read")
    assert r.status_code == 404


# ── POST /notifications/read-all ─────────────────────────────────────────────


def test_mark_all_read_returns_204(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_task_event())
    r = client.post("/notifications/read-all")
    assert r.status_code == 204


def test_mark_all_read_clears_unread_count(client, db_session):
    admin_id = _get_admin_id(client)
    _seed_notification(db_session, recipient_id=admin_id, event=_task_event())
    _seed_notification(db_session, recipient_id=admin_id, event=_mention_event())
    client.post("/notifications/read-all")
    assert client.get("/notifications/unread-count").json()["unread_count"] == 0


def test_mark_all_read_does_not_affect_other_users_notifications(client, db_session):
    other_user = _seed_user(db_session, email="other3@example.com")
    _seed_notification(db_session, recipient_id=other_user.id, event=_task_event())

    # Admin marks all their (empty) list as read
    client.post("/notifications/read-all")

    # Other user's notification must still be unread
    n = db_session.query(Notification).filter_by(recipient_id=other_user.id).first()
    assert n is not None
    assert n.read_at is None


def test_mark_all_read_empty_list_is_no_op(client, db_session):
    db_session  # active
    r = client.post("/notifications/read-all")
    assert r.status_code == 204
    assert client.get("/notifications/unread-count").json()["unread_count"] == 0


# ── Corrupt payload graceful degradation ─────────────────────────────────────


def test_list_malformed_payload_json_returns_empty_message(client, db_session):
    """GET /notifications with a corrupt payload_json returns message='' not a 500.

    The router's _to_out() function catches ValueError/TypeError from
    event_from_payload() and falls back to message="" so a single malformed
    row does not crash the entire notification list.  This is the defensive
    degradation path — the notification is still returned with correct
    metadata; only the rendered message is empty.
    """
    admin_id = _get_admin_id(client)
    now = datetime.now(timezone.utc).isoformat()
    corrupt = Notification(
        recipient_id=admin_id,
        actor_id=None,
        kind="deal_assigned",
        entity_type="deal",
        entity_id=1,
        payload_json='{"kind": "unknown_garbage", "junk": true}',
        read_at=None,
        created_at=now,
    )
    db_session.add(corrupt)
    db_session.commit()
    db_session.refresh(corrupt)

    r = client.get("/notifications")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == corrupt.id
    assert data[0]["kind"] == "deal_assigned"
    assert data[0]["message"] == ""


# ── Route isolation: /read-all is not matched as /{id}/read ──────────────────


def test_read_all_route_is_not_treated_as_notification_id(client):
    """POST /notifications/read-all must NOT match /{notification_id:int}/read.

    FastAPI rejects non-integer path segments for int parameters, so
    'read-all' correctly falls through to the literal route.  This test
    would get a 404 (from /{id}/read with invalid ID) if routing broke.
    """
    r = client.post("/notifications/read-all")
    assert r.status_code == 204  # correct literal route, not a path-param route


# ── Private helpers ───────────────────────────────────────────────────────────


def _get_admin_id(client) -> int:
    """Return the ID of the seeded admin user by calling GET /auth/me."""
    r = client.get("/auth/me")
    assert r.status_code == 200, f"GET /auth/me failed: {r.text}"
    return r.json()["id"]


def _seed_user(db: Session, *, email: str, role: str = "rep") -> User:
    now = datetime.now(timezone.utc).isoformat()
    user = User(
        email=email,
        hashed_password=hash_password("password"),
        role=role,
        full_name="Test User",
        created_at=now,
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
