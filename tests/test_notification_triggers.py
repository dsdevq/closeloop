"""Tests for slice 2: After-Save trigger wiring in app/routers/deals.py.

Each test exercises a real API call and asserts that the correct Notification
rows are (or are not) created in the DB.  The db_session fixture provides
direct DB access for seeding and inspection, sharing the same in-memory
SQLite as the client fixture (ADR-0005).

Reference CRM patterns exercised here:
  - Salesforce workflow-rule / Pipedrive deal_stage_changed trigger
    → PATCH /deals/{id}/stage fires StageChangedEvent to the deal owner
      when the actor is a different user.
  - HubSpot automation / Salesforce After-Save stage_id trigger
    → PATCH /deals/{id} with stage_id fires StageChangedEvent identically.
  - Salesforce / Pipedrive deal-assigned trigger
    → PATCH /deals/{id} with owner_id fires DealAssignedEvent to the new owner
      when the actor is a different user.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.notifications import DealAssignedEvent, StageChangedEvent, event_from_payload
from app.core.security import hash_password
from app.models import Contact, Deal, Notification, PipelineStage, StageTransition, User


# ── Seed helpers ──────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_user(db: Session, *, email: str, role: str = "rep") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("password"),
        role=role,
        full_name="Test Rep",
        created_at=_now(),
        is_active=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_contact(db: Session) -> Contact:
    c = Contact(name="Trigger Test Contact", created_at=_now(), updated_at=_now())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_pipeline_stage(db: Session, *, name: str, position: int = 0) -> PipelineStage:
    stage = PipelineStage(name=name, position=position, probability=50, created_at=_now())
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return stage


def _seed_deal(db: Session, *, owner_id: int, contact_id: int, stage: str = "lead") -> Deal:
    now = _now()
    deal = Deal(
        title="Trigger Test Deal",
        contact_id=contact_id,
        stage=stage,
        value=1000.0,
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


def _get_admin_id(client) -> int:
    r = client.get("/auth/me")
    assert r.status_code == 200
    return r.json()["id"]


def _notifications_for(db: Session, recipient_id: int) -> list[Notification]:
    return db.query(Notification).filter_by(recipient_id=recipient_id).all()


# ── PATCH /deals/{id}/stage — StageChangedEvent trigger ──────────────────────


def test_stage_transition_notifies_deal_owner(client, db_session):
    """Moving a deal owned by rep fires StageChangedEvent to that rep."""
    rep = _seed_user(db_session, email="rep1@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
    assert r.status_code == 200

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "stage_changed"
    assert n.entity_type == "deal"
    assert n.entity_id == deal.id
    assert n.read_at is None

    event = event_from_payload(n.payload_json)
    assert isinstance(event, StageChangedEvent)
    assert event.from_stage == "lead"
    assert event.to_stage == "qualified"
    assert event.deal_title == deal.title


def test_stage_transition_no_self_notification(client, db_session):
    """No notification when the actor is also the deal owner (self-action)."""
    admin_id = _get_admin_id(client)
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
    assert r.status_code == 200

    notifs = _notifications_for(db_session, recipient_id=admin_id)
    assert notifs == []


def test_stage_transition_actor_id_set_on_notification(client, db_session):
    """actor_id on the Notification row matches the user who made the change."""
    admin_id = _get_admin_id(client)
    rep = _seed_user(db_session, email="rep2@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})

    n = _notifications_for(db_session, recipient_id=rep.id)[0]
    assert n.actor_id == admin_id


def test_stage_transition_same_stage_no_notification(client, db_session):
    """No notification when the stage value does not actually change."""
    rep = _seed_user(db_session, email="rep3@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    # lead → lead is technically allowed by validate_transition; must not fire
    r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "lead"})
    assert r.status_code == 200

    assert _notifications_for(db_session, recipient_id=rep.id) == []


def test_stage_transition_no_owner_no_notification(client, db_session):
    """No notification when the deal has no owner (owner_id is NULL)."""
    contact = _seed_contact(db_session)
    now = _now()
    deal = Deal(
        title="Ownerless Deal",
        contact_id=contact.id,
        stage="lead",
        value=0.0,
        probability=0.1,
        owner_id=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(deal)
    db_session.flush()
    db_session.add(StageTransition(deal_id=deal.id, from_stage=None, to_stage="lead", occurred_at=now))
    db_session.commit()

    r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
    assert r.status_code == 200

    count = db_session.query(Notification).count()
    assert count == 0


def test_multiple_stage_transitions_create_multiple_notifications(client, db_session):
    """Each stage transition produces one notification (not deduplicated)."""
    rep = _seed_user(db_session, email="rep4@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
    client.patch(f"/deals/{deal.id}/stage", json={"stage": "proposal"})

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 2
    stages = [event_from_payload(n.payload_json).to_stage for n in notifs]
    assert set(stages) == {"qualified", "proposal"}


# ── PATCH /deals/{id} with stage_id — After-Save stage trigger ───────────────


def test_update_deal_stage_id_notifies_owner(client, db_session):
    """PATCH /deals/{id} with stage_id fires StageChangedEvent (HubSpot automation pattern)."""
    rep = _seed_user(db_session, email="rep5@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id, stage="lead")
    proposal_stage = _seed_pipeline_stage(db_session, name="Proposal Stage", position=2)

    r = client.patch(f"/deals/{deal.id}", json={"stage_id": proposal_stage.id})
    assert r.status_code == 200

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    assert notifs[0].kind == "stage_changed"

    event = event_from_payload(notifs[0].payload_json)
    assert isinstance(event, StageChangedEvent)
    assert event.from_stage == "lead"
    assert event.to_stage == "Proposal Stage"


def test_update_deal_stage_id_no_self_notification(client, db_session):
    """No notification when admin patches stage_id on their own deal."""
    admin_id = _get_admin_id(client)
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)
    proposal_stage = _seed_pipeline_stage(db_session, name="Proposal Stage 2", position=3)

    client.patch(f"/deals/{deal.id}", json={"stage_id": proposal_stage.id})
    assert _notifications_for(db_session, recipient_id=admin_id) == []


# ── PATCH /deals/{id} with owner_id — DealAssignedEvent trigger ──────────────


def test_reassign_owner_notifies_new_owner(client, db_session):
    """Changing owner_id fires DealAssignedEvent to the new owner (Salesforce / Pipedrive pattern)."""
    rep = _seed_user(db_session, email="rep6@test.com")
    admin_id = _get_admin_id(client)
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}", json={"owner_id": rep.id})
    assert r.status_code == 200

    notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(notifs) == 1
    n = notifs[0]
    assert n.kind == "deal_assigned"
    assert n.entity_type == "deal"
    assert n.entity_id == deal.id

    event = event_from_payload(n.payload_json)
    assert isinstance(event, DealAssignedEvent)
    assert event.deal_title == deal.title
    assert event.previous_owner_id == admin_id


def test_reassign_no_self_notification(client, db_session):
    """No DealAssignedEvent when admin assigns a deal to themselves."""
    admin_id = _get_admin_id(client)
    rep = _seed_user(db_session, email="rep7@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    # Admin reassigns to themselves — no notification
    r = client.patch(f"/deals/{deal.id}", json={"owner_id": admin_id})
    assert r.status_code == 200

    assert _notifications_for(db_session, recipient_id=admin_id) == []


def test_reassign_same_owner_no_notification(client, db_session):
    """No notification when owner_id is patched to the same user."""
    rep = _seed_user(db_session, email="rep8@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}", json={"owner_id": rep.id})
    assert r.status_code == 200

    assert _notifications_for(db_session, recipient_id=rep.id) == []


def test_reassign_invalid_owner_returns_404(client, db_session):
    """PATCH /deals/{id} with non-existent owner_id returns 404."""
    admin_id = _get_admin_id(client)
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}", json={"owner_id": 99999})
    assert r.status_code == 404


def test_simultaneous_stage_and_owner_change_fires_both_notifications(client, db_session):
    """A single PATCH with both stage_id and owner_id fires both StageChanged and DealAssigned."""
    rep = _seed_user(db_session, email="rep9@test.com")
    admin_id = _get_admin_id(client)
    rep2 = _seed_user(db_session, email="rep9b@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    proposal_stage = _seed_pipeline_stage(db_session, name="Proposal Stage 3", position=4)

    r = client.patch(f"/deals/{deal.id}", json={"stage_id": proposal_stage.id, "owner_id": rep2.id})
    assert r.status_code == 200

    # rep (original owner) should get a StageChangedEvent
    rep_notifs = _notifications_for(db_session, recipient_id=rep.id)
    assert len(rep_notifs) == 1
    assert rep_notifs[0].kind == "stage_changed"

    # rep2 (new owner) should get a DealAssignedEvent
    rep2_notifs = _notifications_for(db_session, recipient_id=rep2.id)
    assert len(rep2_notifs) == 1
    assert rep2_notifs[0].kind == "deal_assigned"


def test_patch_non_stage_fields_no_notification(client, db_session):
    """Patching title/value fields (no stage or owner change) creates no notifications."""
    rep = _seed_user(db_session, email="rep10@test.com")
    contact = _seed_contact(db_session)
    deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

    r = client.patch(f"/deals/{deal.id}", json={"title": "Updated Title", "value": 9999.0})
    assert r.status_code == 200

    assert _notifications_for(db_session, recipient_id=rep.id) == []
