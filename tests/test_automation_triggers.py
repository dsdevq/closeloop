"""API integration tests for workflow automation trigger wiring (slice 1).

Each test seeds an AutomationRule directly via db_session (no CRUD API in
slice 1 — that's slice 2), performs a real API call through the TestClient,
then asserts the resulting Notification rows.

Pattern borrowed from tests/test_notification_triggers.py: seed via db_session,
call via client, inspect via db_session.  All tests use the shared in-memory
SQLite (ADR-0005).

Reference CRM patterns exercised:
- Salesforce After-Save / Pipedrive event-based: rule fires on deal_created,
  deal_stage_changed when trigger + conditions match.
- HubSpot enrollment criteria: rule skips when a condition does not match.
- Attio / Zoho: inactive rules (is_active=0) are never evaluated.
- HubSpot / Zoho: self-notification suppression — actor == recipient → no notification.
"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.notifications import AutomationTriggeredEvent, event_from_payload
from app.core.security import hash_password
from app.models import (
    AutomationRule,
    Contact,
    Deal,
    Notification,
    PipelineStage,
    StageTransition,
    User,
)


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_user(db: Session, *, email: str, role: str = "rep") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("password"),
        role=role,
        full_name="Test User",
        created_at=_now(),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_contact(db: Session, *, name: str = "Automation Test Contact") -> Contact:
    c = Contact(name=name, created_at=_now(), updated_at=_now())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_pipeline_stage(db: Session, *, name: str, position: int = 99) -> PipelineStage:
    stage = PipelineStage(name=name, position=position, probability=50, created_at=_now())
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


def _seed_deal(
    db: Session,
    *,
    owner_id: int,
    contact_id: int,
    stage: str = "lead",
    value: float = 1000.0,
) -> Deal:
    now = _now()
    deal = Deal(
        title="Automation Test Deal",
        contact_id=contact_id,
        stage=stage,
        value=value,
        probability=0.1,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )
    db.add(deal)
    db.flush()
    db.add(StageTransition(deal_id=deal.id, from_stage=None, to_stage=stage, occurred_at=now))
    db.commit()
    db.refresh(deal)
    return deal


def _seed_rule(
    db: Session,
    *,
    entity_type: str,
    trigger_kind: str,
    action_kind: str = "notify_user",
    recipient_id: int,
    conditions_json: str = "[]",
    message_template: str = "Rule fired",
    is_active: int = 1,
    name: str = "Test Rule",
) -> AutomationRule:
    now = _now()
    rule = AutomationRule(
        name=name,
        entity_type=entity_type,
        trigger_kind=trigger_kind,
        conditions_json=conditions_json,
        action_kind=action_kind,
        action_params_json=json.dumps({
            "recipient_id": recipient_id,
            "message_template": message_template,
        }),
        is_active=is_active,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _get_admin_id(client) -> int:
    r = client.get("/auth/me")
    assert r.status_code == 200
    return r.json()["id"]


def _notifs_for(db: Session, recipient_id: int) -> list[Notification]:
    return db.query(Notification).filter_by(recipient_id=recipient_id).all()


# ── deal_created trigger ──────────────────────────────────────────────────────


def test_deal_created_fires_notify_user_rule(client, db_session):
    """notify_user rule with no conditions fires on POST /deals."""
    rep = _seed_user(db_session, email="auto_rep1@test.com")
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id, message_template="New deal: {title}")

    r = client.post("/deals", json={"title": "Acme Deal", "contact_id": contact.id})
    assert r.status_code == 201

    notifs = _notifs_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "automation_triggered"
    event = event_from_payload(n.payload_json)
    assert isinstance(event, AutomationTriggeredEvent)
    assert event.message == "New deal: Acme Deal"


def test_deal_created_rule_condition_matches(client, db_session):
    """Rule with matching condition fires."""
    rep = _seed_user(db_session, email="auto_rep2@test.com")
    contact = _seed_contact(db_session)
    conds = json.dumps([{"field": "stage", "op": "eq", "value": "lead"}])
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id, conditions_json=conds)

    r = client.post("/deals", json={"title": "Lead Deal", "contact_id": contact.id})
    assert r.status_code == 201

    assert len(_notifs_for(db_session, recipient_id=rep.id)) == 1


def test_deal_created_rule_condition_no_match(client, db_session):
    """Rule with non-matching condition does NOT fire."""
    rep = _seed_user(db_session, email="auto_rep3@test.com")
    contact = _seed_contact(db_session)
    conds = json.dumps([{"field": "stage", "op": "eq", "value": "won"}])
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id, conditions_json=conds)

    # create_deal always sets stage="lead", so stage != "won" → rule should not fire
    r = client.post("/deals", json={"title": "Lead Deal", "contact_id": contact.id})
    assert r.status_code == 201

    assert _notifs_for(db_session, recipient_id=rep.id) == []


def test_inactive_rule_does_not_fire(client, db_session):
    """Rules with is_active=0 are never evaluated."""
    rep = _seed_user(db_session, email="auto_rep4@test.com")
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id, is_active=0)

    client.post("/deals", json={"title": "Deal X", "contact_id": contact.id})

    assert _notifs_for(db_session, recipient_id=rep.id) == []


def test_self_notification_suppressed(client, db_session):
    """No notification when recipient_id == actor.id (admin creates deal, admin is recipient)."""
    admin_id = _get_admin_id(client)
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=admin_id)

    client.post("/deals", json={"title": "Self Deal", "contact_id": contact.id})

    assert _notifs_for(db_session, recipient_id=admin_id) == []


# ── deal_stage_changed trigger via PATCH /deals/{id}/stage ───────────────────


def test_deal_stage_changed_fires_rule(client, db_session):
    """notify_user rule fires when PATCH /deals/{id}/stage changes the stage."""
    rep = _seed_user(db_session, email="auto_rep5@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_stage_changed",
               recipient_id=rep.id, message_template="Stage changed to {stage}")

    r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
    assert r.status_code == 200

    notifs = _notifs_for(db_session, recipient_id=rep.id)
    # The stage-change notification from the hardcoded trigger (kind=stage_changed)
    # and the automation trigger (kind=automation_triggered) may both be present.
    # Assert the automation_triggered one exists.
    auto_notifs = [n for n in notifs if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1
    event = event_from_payload(auto_notifs[0].payload_json)
    assert isinstance(event, AutomationTriggeredEvent)
    assert "qualified" in event.message


def test_deal_stage_changed_rule_with_value_condition(client, db_session):
    """Rule with value > 5000 condition fires when deal value matches."""
    rep = _seed_user(db_session, email="auto_rep6@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id, value=10000.0)
    conds = json.dumps([{"field": "value", "op": "gt", "value": 5000}])
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_stage_changed",
               recipient_id=rep.id, conditions_json=conds)

    client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1


def test_deal_stage_changed_rule_value_condition_no_match(client, db_session):
    """Rule with value > 5000 does not fire when deal value is below threshold."""
    rep = _seed_user(db_session, email="auto_rep7@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id, value=100.0)
    conds = json.dumps([{"field": "value", "op": "gt", "value": 5000}])
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_stage_changed",
               recipient_id=rep.id, conditions_json=conds)

    client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert auto_notifs == []


def test_deal_stage_unchanged_rule_does_not_fire(client, db_session):
    """Rule does not fire when PATCH /deals/{id}/stage sends the same stage (no-op)."""
    rep = _seed_user(db_session, email="auto_rep8@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_stage_changed",
               recipient_id=rep.id)

    # lead → lead: validate_transition allows it but stage doesn't actually change
    client.patch(f"/deals/{deal.id}/stage", json={"stage": "lead"})

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert auto_notifs == []


# ── contact_created trigger ───────────────────────────────────────────────────


def test_contact_created_fires_rule(client, db_session):
    """Rule fires on POST /contacts."""
    rep = _seed_user(db_session, email="auto_rep9@test.com")
    _seed_rule(db_session, entity_type="contact", trigger_kind="contact_created",
               recipient_id=rep.id, message_template="New contact: {name}")

    r = client.post("/contacts", json={"name": "Jane Doe"})
    assert r.status_code == 201

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1
    event = event_from_payload(auto_notifs[0].payload_json)
    assert event.message == "New contact: Jane Doe"


def test_contact_updated_fires_rule(client, db_session):
    """Rule fires on PATCH /contacts/{id} when payload is non-empty."""
    rep = _seed_user(db_session, email="auto_rep10@test.com")
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="contact", trigger_kind="contact_updated",
               recipient_id=rep.id)

    r = client.patch(f"/contacts/{contact.id}", json={"company": "Acme"})
    assert r.status_code == 200

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1


# ── activity_created trigger ──────────────────────────────────────────────────


def test_activity_created_fires_rule(client, db_session):
    """Rule fires on POST /activities."""
    rep = _seed_user(db_session, email="auto_rep11@test.com")
    _seed_rule(db_session, entity_type="activity", trigger_kind="activity_created",
               recipient_id=rep.id)

    r = client.post("/activities", json={"type": "call", "title": "Discovery call"})
    assert r.status_code == 201

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1


def test_activity_created_type_condition(client, db_session):
    """Rule with type=note condition only fires for note activities."""
    rep = _seed_user(db_session, email="auto_rep12@test.com")
    conds = json.dumps([{"field": "type", "op": "eq", "value": "note"}])
    _seed_rule(db_session, entity_type="activity", trigger_kind="activity_created",
               recipient_id=rep.id, conditions_json=conds)

    # call activity — should not fire
    client.post("/activities", json={"type": "call", "title": "A call"})
    assert _notifs_for(db_session, rep.id) == []

    # note activity — should fire
    client.post("/activities", json={"type": "note", "title": "A note"})
    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1


# ── activity_completed trigger ────────────────────────────────────────────────


def test_activity_completed_fires_rule(client, db_session):
    """Rule fires on POST /activities/{id}/complete."""
    rep = _seed_user(db_session, email="auto_rep13@test.com")
    _seed_rule(db_session, entity_type="activity", trigger_kind="activity_completed",
               recipient_id=rep.id, message_template="Activity completed: {title}")

    # Create activity first via API
    r = client.post("/activities", json={"type": "call", "title": "Follow-up call"})
    assert r.status_code == 201
    activity_id = r.json()["id"]

    r = client.post(f"/activities/{activity_id}/complete")
    assert r.status_code == 200

    auto_notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(auto_notifs) == 1
    event = event_from_payload(auto_notifs[0].payload_json)
    assert "Follow-up call" in event.message


# ── multiple rules for same trigger ──────────────────────────────────────────


def test_multiple_rules_same_trigger_all_fire(client, db_session):
    """All active matching rules fire independently when the same trigger occurs."""
    rep1 = _seed_user(db_session, email="auto_rep14@test.com")
    rep2 = _seed_user(db_session, email="auto_rep15@test.com")
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep1.id, name="Rule A")
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep2.id, name="Rule B")

    client.post("/deals", json={"title": "Multi-Rule Deal", "contact_id": contact.id})

    assert len(_notifs_for(db_session, rep1.id)) == 1
    assert len(_notifs_for(db_session, rep2.id)) == 1


# ── wrong entity type — no cross-firing ──────────────────────────────────────


def test_deal_rule_does_not_fire_on_contact_create(client, db_session):
    """A deal-scoped rule does not fire when a contact is created."""
    rep = _seed_user(db_session, email="auto_rep16@test.com")
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id)

    client.post("/contacts", json={"name": "Wrong entity"})

    assert _notifs_for(db_session, rep.id) == []


# ── actor_id set correctly on notification ────────────────────────────────────


def test_automation_notification_actor_id_set(client, db_session):
    """actor_id on the Notification row matches the admin user who triggered the action."""
    admin_id = _get_admin_id(client)
    rep = _seed_user(db_session, email="auto_rep17@test.com")
    contact = _seed_contact(db_session)
    _seed_rule(db_session, entity_type="deal", trigger_kind="deal_created",
               recipient_id=rep.id)

    client.post("/deals", json={"title": "Actor Check Deal", "contact_id": contact.id})

    notifs = [n for n in _notifs_for(db_session, rep.id) if n.kind == "automation_triggered"]
    assert len(notifs) == 1
    assert notifs[0].actor_id == admin_id
