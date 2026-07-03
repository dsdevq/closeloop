"""Tests for slice 3: @mention parsing trigger wiring in app/routers/activities.py.

Each test makes a real API call and asserts that the correct Notification rows
are (or are not) created in the DB.  The db_session fixture provides direct DB
access, sharing the same in-memory SQLite as the client fixture (ADR-0005).

Reference CRM patterns exercised here:
  - Zoho @mention first-class notification kind (notifications-engine.md §2.5)
    → POST/PATCH /activities with type="note" and @token in body fires
      MentionEvent to the resolved user.
  - Salesforce Chatter-style @mention convention
    → token matched against User.email local-part (case-insensitive).
  - Self-mention suppression (consistent with slice 2 self-notification rule)
    → actor == recipient → no notification.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.notifications import MentionEvent, event_from_payload
from app.core.security import hash_password
from app.models import Activity, Contact, Notification, User


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_user(
    db: Session, *, email: str, role: str = "rep", is_active: int = 1
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("password"),
        role=role,
        full_name="Test User",
        created_at=_now(),
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_contact(db: Session) -> Contact:
    c = Contact(name="Mention Test Contact", created_at=_now(), updated_at=_now())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _get_admin_id(client) -> int:
    r = client.get("/auth/me")
    assert r.status_code == 200
    return r.json()["id"]


def _notifications_for(db: Session, recipient_id: int) -> list[Notification]:
    return db.query(Notification).filter_by(recipient_id=recipient_id).all()


def _all_notifications(db: Session) -> list[Notification]:
    return db.query(Notification).all()


# ── POST /activities — MentionEvent on note creation ─────────────────────────


def test_note_with_mention_creates_notification(client, db_session):
    """Creating a note with @email-prefix fires MentionEvent to that user."""
    rep = _seed_user(db_session, email="alice@closeloop.com")

    r = client.post("/activities", json={
        "type": "note",
        "title": "Meeting note",
        "body": "Hey @alice, can you review the proposal?",
    })
    assert r.status_code == 201

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "mention"
    assert n.entity_type == "activity"
    assert n.entity_id == r.json()["id"]
    assert n.read_at is None

    event = event_from_payload(n.payload_json)
    assert isinstance(event, MentionEvent)
    assert event.entity_type == "activity"
    assert event.entity_id == r.json()["id"]
    assert "review the proposal" in event.snippet


def test_note_mention_sets_actor_id(client, db_session):
    """actor_id on the Notification row matches the user who wrote the note."""
    admin_id = _get_admin_id(client)
    rep = _seed_user(db_session, email="bob@closeloop.com")

    client.post("/activities", json={
        "type": "note",
        "title": "Note",
        "body": "@bob please check this",
    })

    n = _notifications_for(db_session, recipient_id=rep.id)[0]
    assert n.actor_id == admin_id


def test_self_mention_in_note_creates_no_notification(client, db_session):
    """No MentionEvent when the note author @mentions themselves."""
    admin_id = _get_admin_id(client)
    # The seeded admin email is admin@closeloop.com; @admin matches the local part.
    r = client.get("/auth/me")
    admin_email = r.json()["email"]
    admin_local = admin_email.split("@")[0]

    client.post("/activities", json={
        "type": "note",
        "title": "Self-mention note",
        "body": f"Reminder to myself: @{admin_local} review this tomorrow",
    })

    assert _notifications_for(db_session, recipient_id=admin_id) == []


def test_non_note_activity_with_mention_body_creates_no_notification(client, db_session):
    """@mention in a call/email/meeting body does NOT fire a notification.

    Only activities with type=='note' trigger mention parsing (Attio
    comment_mention / Zoho note-body pattern, not all activity types).
    Reps commonly write email addresses or Zoom links in meeting bodies;
    restricting to notes avoids spurious pings.
    """
    rep = _seed_user(db_session, email="carol@closeloop.com")

    for activity_type in ("call", "email", "meeting"):
        r = client.post("/activities", json={
            "type": activity_type,
            "title": f"{activity_type} with Carol",
            "body": "@carol discussed pricing",
        })
        assert r.status_code == 201

    assert _notifications_for(db_session, recipient_id=rep.id) == []


def test_mention_of_unknown_user_creates_no_notification(client, db_session):
    """@mention of a token with no matching User email is silently ignored."""
    r = client.post("/activities", json={
        "type": "note",
        "title": "Note",
        "body": "@nobody_here please review",
    })
    assert r.status_code == 201
    assert _all_notifications(db_session) == []


def test_mention_of_inactive_user_creates_no_notification(client, db_session):
    """@mention of an inactive user (is_active=0) is not resolved."""
    _seed_user(db_session, email="dave@closeloop.com", is_active=0)

    client.post("/activities", json={
        "type": "note",
        "title": "Note",
        "body": "@dave can you review?",
    })

    assert _all_notifications(db_session) == []


def test_multiple_mentions_create_multiple_notifications(client, db_session):
    """Each unique @mention in a note body fires one MentionEvent."""
    alice = _seed_user(db_session, email="alice2@closeloop.com")
    bob = _seed_user(db_session, email="bob2@closeloop.com")

    r = client.post("/activities", json={
        "type": "note",
        "title": "Group note",
        "body": "@alice2 and @bob2 should both review this proposal.",
    })
    assert r.status_code == 201

    alice_notifs = _notifications_for(db_session, recipient_id=alice.id)
    bob_notifs = _notifications_for(db_session, recipient_id=bob.id)
    assert len(alice_notifs) == 1
    assert len(bob_notifs) == 1
    assert alice_notifs[0].kind == "mention"
    assert bob_notifs[0].kind == "mention"


def test_duplicate_mention_in_body_creates_one_notification(client, db_session):
    """Mentioning the same user twice in one note fires only one notification."""
    rep = _seed_user(db_session, email="eve@closeloop.com")

    client.post("/activities", json={
        "type": "note",
        "title": "Dup note",
        "body": "@eve please see this. Again, @eve can you confirm?",
    })

    assert len(_notifications_for(db_session, recipient_id=rep.id)) == 1


def test_note_without_body_creates_no_notification(client, db_session):
    """No notification when the note body is absent."""
    _seed_user(db_session, email="frank@closeloop.com")

    r = client.post("/activities", json={
        "type": "note",
        "title": "Empty note",
    })
    assert r.status_code == 201
    assert _all_notifications(db_session) == []


def test_mention_snippet_truncated_to_120_chars(client, db_session):
    """The MentionEvent snippet is at most 120 characters."""
    rep = _seed_user(db_session, email="grace@closeloop.com")
    long_body = "@grace " + "x" * 200

    client.post("/activities", json={
        "type": "note",
        "title": "Long note",
        "body": long_body,
    })

    n = _notifications_for(db_session, recipient_id=rep.id)[0]
    event = event_from_payload(n.payload_json)
    assert isinstance(event, MentionEvent)
    assert len(event.snippet) <= 120


def test_mention_token_is_case_insensitive(client, db_session):
    """@ALICE resolves to the user with email alice@... (case-insensitive)."""
    rep = _seed_user(db_session, email="henry@closeloop.com")

    client.post("/activities", json={
        "type": "note",
        "title": "Caps note",
        "body": "Hey @HENRY, check this out",
    })

    assert len(_notifications_for(db_session, recipient_id=rep.id)) == 1


# ── PATCH /activities/{id} — MentionEvent on note body update ────────────────


def test_updating_note_body_with_mention_fires_notification(client, db_session):
    """PATCH /activities/{id} with a new body containing @mention fires MentionEvent."""
    rep = _seed_user(db_session, email="iris@closeloop.com")

    create_r = client.post("/activities", json={
        "type": "note",
        "title": "Initial note",
        "body": "No mentions here",
    })
    assert create_r.status_code == 201
    activity_id = create_r.json()["id"]

    # Confirm no notifications from the initial create
    assert _notifications_for(db_session, recipient_id=rep.id) == []

    patch_r = client.patch(f"/activities/{activity_id}", json={
        "body": "@iris please review the updated note",
    })
    assert patch_r.status_code == 200

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    assert notifs[0].kind == "mention"
    assert notifs[0].entity_id == activity_id


def test_updating_note_title_only_fires_no_notification(client, db_session):
    """PATCH with only title (no body field) does not re-parse mentions."""
    rep = _seed_user(db_session, email="jack@closeloop.com")

    create_r = client.post("/activities", json={
        "type": "note",
        "title": "Note with @jack in title",
        "body": "@jack is mentioned",
    })
    activity_id = create_r.json()["id"]
    # Clear notifications from create
    initial_count = len(_notifications_for(db_session, recipient_id=rep.id))
    assert initial_count == 1

    client.patch(f"/activities/{activity_id}", json={"title": "Renamed note"})

    # Count must not increase — no new notifications from a title-only patch
    assert len(_notifications_for(db_session, recipient_id=rep.id)) == 1


def test_updating_non_note_to_have_mention_in_body_fires_no_notification(client, db_session):
    """PATCH body on a call/email/meeting activity never fires a MentionEvent."""
    rep = _seed_user(db_session, email="kate@closeloop.com")

    create_r = client.post("/activities", json={
        "type": "call",
        "title": "Sales call",
        "body": "Initial notes",
    })
    activity_id = create_r.json()["id"]

    client.patch(f"/activities/{activity_id}", json={"body": "@kate can you follow up?"})

    assert _notifications_for(db_session, recipient_id=rep.id) == []


def test_editing_note_without_changing_mentions_fires_no_duplicate_notification(client, db_session):
    """Re-patching a note body that still mentions the same user produces no new notification.

    Covers the typo-fix scenario: the mention was already notified on the first
    write; subsequent edits that keep the same @token must not re-ping the user.
    """
    rep = _seed_user(db_session, email="liam@closeloop.com")

    create_r = client.post("/activities", json={
        "type": "note",
        "title": "Initial note",
        "body": "@liam please review this draft",
    })
    assert create_r.status_code == 201
    activity_id = create_r.json()["id"]

    # One notification from the initial create
    assert len(_notifications_for(db_session, recipient_id=rep.id)) == 1

    # Patch the body — @liam still present; only wording changed
    patch_r = client.patch(f"/activities/{activity_id}", json={
        "body": "@liam please review this updated draft (typo fixed)",
    })
    assert patch_r.status_code == 200

    # Still exactly one notification — no duplicate
    assert len(_notifications_for(db_session, recipient_id=rep.id)) == 1


def test_editing_note_to_add_new_mention_fires_only_for_new_user(client, db_session):
    """Patching a note to add a new @mention fires exactly one notification for the new user only.

    The already-notified user from the original write must NOT receive a second
    notification; only the newly-added user should receive one.
    """
    existing = _seed_user(db_session, email="mia@closeloop.com")
    added = _seed_user(db_session, email="noah@closeloop.com")

    create_r = client.post("/activities", json={
        "type": "note",
        "title": "Collab note",
        "body": "@mia can you review this?",
    })
    assert create_r.status_code == 201
    activity_id = create_r.json()["id"]

    assert len(_notifications_for(db_session, recipient_id=existing.id)) == 1
    assert len(_notifications_for(db_session, recipient_id=added.id)) == 0

    # Edit adds @noah while keeping @mia
    patch_r = client.patch(f"/activities/{activity_id}", json={
        "body": "@mia and @noah both need to review this",
    })
    assert patch_r.status_code == 200

    # @mia: still exactly one notification (no duplicate)
    assert len(_notifications_for(db_session, recipient_id=existing.id)) == 1
    # @noah: exactly one new notification
    noah_notifs = _notifications_for(db_session, recipient_id=added.id)
    assert len(noah_notifs) == 1
    assert noah_notifs[0].kind == "mention"
    assert noah_notifs[0].entity_id == activity_id
