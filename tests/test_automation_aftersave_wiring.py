"""Integration tests for after-save automation rule wiring.

Verifies that execute_automation_rules() is called inline at each of the 8
trigger sites (deal_created, deal_stage_changed, deal_assigned, deal_updated,
contact_created, contact_updated, activity_created, activity_completed) by
planting an active AutomationRule with a notify action and asserting that a
Notification row is created as a side-effect of the mutation API call.

Design choices:
- Uses the `client` fixture (in-memory SQLite, admin auth) and `db_session`
  for direct seed/query access — no mocking, per ADR-0005.
- Every test plants a second (rep) user as the notification recipient so that
  self-notification suppression (actor_id == recipient_id) doesn't interfere.
- Rules use recipient_id (static) so tests don't depend on dynamic context
  field resolution.
- Tests assert Notification count increments, verifying the action fired; they
  do not exhaustively test condition evaluation (that's covered in
  test_core_automations.py).
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    AutomationRule,
    Contact,
    Notification,
    PipelineStage,
    User,
)

_T0_ISO = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _seed_rep(db: Session) -> User:
    rep = User(
        email="rep@closeloop.com",
        hashed_password=hash_password("password"),
        role="rep",
        full_name="Rep User",
        created_at=_T0_ISO,
        is_active=1,
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return rep


def _seed_contact(db: Session, owner_id: int) -> Contact:
    c = Contact(
        name="Test Contact",
        email="testcontact@example.com",
        lead_score=0.0,
        owner_id=owner_id,
        created_at=_T0_ISO,
        updated_at=_T0_ISO,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_stage(db: Session, name: str = "Prospecting", position: int = 0) -> PipelineStage:
    s = PipelineStage(
        name=name,
        position=position,
        probability=10,
        is_default=1,
        created_at=_T0_ISO,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_rule(
    db: Session,
    *,
    trigger_event: str,
    recipient_id: int,
    conditions_json: str | None = None,
) -> AutomationRule:
    import json
    rule = AutomationRule(
        name=f"Test rule: {trigger_event}",
        trigger_type="after_save",
        trigger_event=trigger_event,
        conditions_json=conditions_json,
        action_type="notify",
        action_config_json=json.dumps({"recipient_id": recipient_id}),
        is_active=1,
        created_at=_T0_ISO,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _notification_count(db: Session) -> int:
    return db.query(Notification).count()


# ── deal_created ──────────────────────────────────────────────────────────────


def test_deal_created_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session)
    _seed_rule(db_session, trigger_event="deal_created", recipient_id=rep.id)

    before = _notification_count(db_session)
    resp = client.post("/deals", json={"title": "Automation Test Deal", "contact_id": contact.id})
    assert resp.status_code == 201

    assert _notification_count(db_session) == before + 1
    notif = db_session.query(Notification).order_by(Notification.id.desc()).first()
    assert notif.recipient_id == rep.id
    assert notif.kind == "automation"


def test_deal_created_inactive_rule_does_not_fire(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session)
    rule = _seed_rule(db_session, trigger_event="deal_created", recipient_id=rep.id)
    rule.is_active = 0
    db_session.commit()

    before = _notification_count(db_session)
    resp = client.post("/deals", json={"title": "No automation", "contact_id": contact.id})
    assert resp.status_code == 201
    assert _notification_count(db_session) == before


def test_deal_created_condition_mismatch_does_not_fire(client, db_session):
    import json
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session)
    # Condition: stage == "won" — but newly created deals are "lead"
    _seed_rule(
        db_session,
        trigger_event="deal_created",
        recipient_id=rep.id,
        conditions_json=json.dumps([{"field": "stage", "op": "eq", "value": "won"}]),
    )

    before = _notification_count(db_session)
    resp = client.post("/deals", json={"title": "No match", "contact_id": contact.id})
    assert resp.status_code == 201
    assert _notification_count(db_session) == before


# ── deal_stage_changed (via PATCH /{id}/stage) ────────────────────────────────


def test_deal_stage_changed_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session, name="Prospecting", position=0)
    _seed_stage(db_session, name="Qualification", position=1)
    _seed_rule(db_session, trigger_event="deal_stage_changed", recipient_id=rep.id)

    resp = client.post("/deals", json={"title": "Stage Test", "contact_id": contact.id})
    assert resp.status_code == 201
    deal_id = resp.json()["id"]

    before = _notification_count(db_session)
    resp = client.patch(f"/deals/{deal_id}/stage", json={"stage": "qualified"})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 1


def test_deal_stage_changed_with_matching_condition(client, db_session):
    import json
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session, name="Prospecting", position=0)
    _seed_stage(db_session, name="Qualification", position=1)
    _seed_rule(
        db_session,
        trigger_event="deal_stage_changed",
        recipient_id=rep.id,
        conditions_json=json.dumps([{"field": "stage", "op": "eq", "value": "qualified"}]),
    )

    resp = client.post("/deals", json={"title": "Cond Match", "contact_id": contact.id})
    deal_id = resp.json()["id"]
    before = _notification_count(db_session)
    resp = client.patch(f"/deals/{deal_id}/stage", json={"stage": "qualified"})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 1


# ── deal_assigned (via PATCH /{id}) ───────────────────────────────────────────


def test_deal_assigned_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session)
    _seed_rule(db_session, trigger_event="deal_assigned", recipient_id=rep.id)

    resp = client.post("/deals", json={"title": "Assign Test", "contact_id": contact.id})
    assert resp.status_code == 201
    deal_id = resp.json()["id"]

    before = _notification_count(db_session)
    # admin (acting user) reassigns to rep — rep receives:
    # 1. hardcoded DealAssignedEvent notification (existing trigger wiring in deals.py)
    # 2. automation rule notification (new after-save wiring)
    resp = client.patch(f"/deals/{deal_id}", json={"owner_id": rep.id})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 2

    notifs = (
        db_session.query(Notification)
        .filter(Notification.recipient_id == rep.id)
        .all()
    )
    kinds = {n.kind for n in notifs}
    assert "deal_assigned" in kinds  # hardcoded trigger
    assert "automation" in kinds     # automation rule


# ── deal_updated (via PATCH /{id} non-structural fields) ──────────────────────


def test_deal_updated_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_stage(db_session)
    _seed_rule(db_session, trigger_event="deal_updated", recipient_id=rep.id)

    resp = client.post("/deals", json={"title": "Update Test", "contact_id": contact.id})
    deal_id = resp.json()["id"]

    before = _notification_count(db_session)
    resp = client.patch(f"/deals/{deal_id}", json={"title": "New Title"})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 1


# ── contact_created ───────────────────────────────────────────────────────────


def test_contact_created_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    _seed_rule(db_session, trigger_event="contact_created", recipient_id=rep.id)

    before = _notification_count(db_session)
    resp = client.post("/contacts", json={"name": "New Contact"})
    assert resp.status_code == 201
    assert _notification_count(db_session) == before + 1


# ── contact_updated ───────────────────────────────────────────────────────────


def test_contact_updated_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_rule(db_session, trigger_event="contact_updated", recipient_id=rep.id)

    before = _notification_count(db_session)
    resp = client.patch(f"/contacts/{contact.id}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 1


def test_contact_updated_empty_payload_does_not_fire(client, db_session):
    rep = _seed_rep(db_session)
    contact = _seed_contact(db_session, owner_id=rep.id)
    _seed_rule(db_session, trigger_event="contact_updated", recipient_id=rep.id)

    before = _notification_count(db_session)
    resp = client.patch(f"/contacts/{contact.id}", json={})
    assert resp.status_code == 200
    assert _notification_count(db_session) == before  # guard: empty payload → no fire


# ── activity_created ──────────────────────────────────────────────────────────


def test_activity_created_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    _seed_rule(db_session, trigger_event="activity_created", recipient_id=rep.id)

    before = _notification_count(db_session)
    resp = client.post("/activities", json={"title": "Call Alice", "type": "call"})
    assert resp.status_code == 201
    assert _notification_count(db_session) == before + 1


def test_activity_created_type_condition_fires(client, db_session):
    import json
    rep = _seed_rep(db_session)
    _seed_rule(
        db_session,
        trigger_event="activity_created",
        recipient_id=rep.id,
        conditions_json=json.dumps([{"field": "activity_type", "op": "eq", "value": "call"}]),
    )

    before = _notification_count(db_session)
    client.post("/activities", json={"title": "Call", "type": "call"})
    assert _notification_count(db_session) == before + 1


def test_activity_created_type_condition_no_fire(client, db_session):
    import json
    rep = _seed_rep(db_session)
    _seed_rule(
        db_session,
        trigger_event="activity_created",
        recipient_id=rep.id,
        conditions_json=json.dumps([{"field": "activity_type", "op": "eq", "value": "call"}]),
    )

    before = _notification_count(db_session)
    client.post("/activities", json={"title": "Email", "type": "email"})
    assert _notification_count(db_session) == before  # email doesn't match "call"


# ── activity_completed ────────────────────────────────────────────────────────


def test_activity_completed_fires_automation(client, db_session):
    rep = _seed_rep(db_session)
    _seed_rule(db_session, trigger_event="activity_completed", recipient_id=rep.id)

    resp = client.post("/activities", json={"title": "Task", "type": "call"})
    assert resp.status_code == 201
    activity_id = resp.json()["id"]

    before = _notification_count(db_session)
    resp = client.post(f"/activities/{activity_id}/complete")
    assert resp.status_code == 200
    assert _notification_count(db_session) == before + 1


def test_activity_completed_already_completed_does_not_double_fire(client, db_session):
    rep = _seed_rep(db_session)
    _seed_rule(db_session, trigger_event="activity_completed", recipient_id=rep.id)

    resp = client.post("/activities", json={"title": "Task", "type": "call"})
    activity_id = resp.json()["id"]

    client.post(f"/activities/{activity_id}/complete")
    before = _notification_count(db_session)
    # Second complete should 400 and not fire the rule again
    resp = client.post(f"/activities/{activity_id}/complete")
    assert resp.status_code == 400
    assert _notification_count(db_session) == before
