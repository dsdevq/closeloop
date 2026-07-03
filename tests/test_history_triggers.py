"""Integration tests for slice-2 history trigger wiring.

Each test exercises a real API call and asserts that the correct HistoryEntry
rows are created in the DB.  The db_session fixture provides direct DB access
for inspection, sharing the same in-memory SQLite as the client fixture (ADR-0005).

Trigger mechanism is Salesforce Field History Tracking's save-triggered capture
(activity-timeline.md §2.1): history rows are written in the same transaction as
the mutation, before db.commit(). Tests verify the rows exist and carry the
correct kind + structured payload.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.history import (
    ActivityCompletedEntry,
    ActivityCreatedEntry,
    ActivityDeletedEntry,
    ActivityUpdatedEntry,
    ContactCreatedEntry,
    ContactDeletedEntry,
    ContactUpdatedEntry,
    DealAssignedEntry,
    DealCreatedEntry,
    DealDeletedEntry,
    DealStageChangedEntry,
    DealUpdatedEntry,
    event_from_meta,
)
from app.core.security import hash_password
from app.models import Contact, Deal, HistoryEntry, PipelineStage, StageTransition, User


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


def _seed_contact(db: Session, *, name: str = "History Test Contact") -> Contact:
    c = Contact(name=name, created_at=_now(), updated_at=_now())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def _seed_pipeline_stage(db: Session, *, name: str, position: int = 99) -> PipelineStage:
    s = PipelineStage(name=name, position=position, probability=50, created_at=_now())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _seed_deal(db: Session, *, owner_id: int, contact_id: int, stage: str = "lead") -> Deal:
    now = _now()
    deal = Deal(
        title="History Test Deal",
        contact_id=contact_id,
        stage=stage,
        value=500.0,
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
    return client.get("/auth/me").json()["id"]


def _history_for(db: Session, *, entity_type: str, entity_id: int) -> list[HistoryEntry]:
    return (
        db.query(HistoryEntry)
        .filter_by(entity_type=entity_type, entity_id=entity_id)
        .order_by(HistoryEntry.occurred_at)
        .all()
    )


# ── Deal triggers ─────────────────────────────────────────────────────────────


class TestDealCreatedTrigger:
    def test_creates_deal_created_entry(self, client, db_session):
        contact = _seed_contact(db_session)
        r = client.post("/deals", json={"title": "New Deal", "contact_id": contact.id, "value": 100.0})
        assert r.status_code == 201
        deal_id = r.json()["id"]

        entries = _history_for(db_session, entity_type="deal", entity_id=deal_id)
        assert len(entries) == 1
        assert entries[0].kind == "deal_created"
        event = event_from_meta(entries[0].meta_json)
        assert isinstance(event, DealCreatedEntry)
        assert event.deal_title == "New Deal"
        assert event.deal_id == deal_id

    def test_actor_id_set_to_current_user(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        r = client.post("/deals", json={"title": "Actor Deal", "contact_id": contact.id})
        deal_id = r.json()["id"]
        entries = _history_for(db_session, entity_type="deal", entity_id=deal_id)
        assert entries[0].actor_id == admin_id


class TestDealStageChangedTrigger:
    def test_patch_stage_creates_stage_changed_entry(self, client, db_session):
        rep = _seed_user(db_session, email="h_rep1@test.com")
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

        r = client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        kinds = [e.kind for e in entries]
        assert "deal_stage_changed" in kinds

        sc_entry = next(e for e in entries if e.kind == "deal_stage_changed")
        event = event_from_meta(sc_entry.meta_json)
        assert isinstance(event, DealStageChangedEntry)
        assert event.from_stage == "lead"
        assert event.to_stage == "qualified"
        assert event.deal_title == deal.title

    def test_same_stage_no_history_entry(self, client, db_session):
        rep = _seed_user(db_session, email="h_rep2@test.com")
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

        # No stage change — lead → lead (validate_transition allows it)
        client.patch(f"/deals/{deal.id}/stage", json={"stage": "lead"})

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        assert not any(e.kind == "deal_stage_changed" for e in entries)

    def test_patch_deal_with_stage_id_creates_stage_changed_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id, stage="lead")
        proposal_stage = _seed_pipeline_stage(db_session, name="H_Proposal", position=50)

        r = client.patch(f"/deals/{deal.id}", json={"stage_id": proposal_stage.id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        sc = [e for e in entries if e.kind == "deal_stage_changed"]
        assert len(sc) == 1
        event = event_from_meta(sc[0].meta_json)
        assert event.to_stage == "H_Proposal"


class TestDealAssignedTrigger:
    def test_owner_change_creates_assigned_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        rep = _seed_user(db_session, email="h_rep3@test.com")
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        r = client.patch(f"/deals/{deal.id}", json={"owner_id": rep.id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        assigned = [e for e in entries if e.kind == "deal_assigned"]
        assert len(assigned) == 1
        event = event_from_meta(assigned[0].meta_json)
        assert isinstance(event, DealAssignedEntry)
        assert event.from_owner_id == admin_id
        assert event.to_owner_id == rep.id

    def test_self_assignment_still_creates_history_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        # Reassign to same owner — notifications skip self, but history always records
        r = client.patch(f"/deals/{deal.id}", json={"owner_id": admin_id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        # No history entry because from_owner_id == to_owner_id (no actual change)
        assigned = [e for e in entries if e.kind == "deal_assigned"]
        assert assigned == []

    def test_new_owner_creates_assigned_entry_regardless_of_self(self, client, db_session):
        admin_id = _get_admin_id(client)
        rep = _seed_user(db_session, email="h_rep4@test.com")
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=rep.id, contact_id=contact.id)

        # Admin assigns to themselves — history records it (unlike notifications which suppress)
        r = client.patch(f"/deals/{deal.id}", json={"owner_id": admin_id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        assigned = [e for e in entries if e.kind == "deal_assigned"]
        assert len(assigned) == 1
        event = event_from_meta(assigned[0].meta_json)
        assert event.to_owner_id == admin_id


class TestDealUpdatedTrigger:
    def test_title_change_creates_updated_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        r = client.patch(f"/deals/{deal.id}", json={"title": "Renamed Deal"})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        updated = [e for e in entries if e.kind == "deal_updated"]
        assert len(updated) == 1
        event = event_from_meta(updated[0].meta_json)
        assert isinstance(event, DealUpdatedEntry)

    def test_stage_only_change_no_updated_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)
        stage = _seed_pipeline_stage(db_session, name="H_Stage2", position=51)

        r = client.patch(f"/deals/{deal.id}", json={"stage_id": stage.id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        assert not any(e.kind == "deal_updated" for e in entries)

    def test_owner_only_change_no_updated_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        rep = _seed_user(db_session, email="h_rep5@test.com")
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        r = client.patch(f"/deals/{deal.id}", json={"owner_id": rep.id})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="deal", entity_id=deal.id)
        assert not any(e.kind == "deal_updated" for e in entries)


class TestDealDeletedTrigger:
    def test_delete_creates_deleted_entry(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)
        deal_id = deal.id
        deal_title = deal.title

        r = client.delete(f"/deals/{deal_id}")
        assert r.status_code == 204

        # History row survives deal deletion (no FK on entity_id)
        entries = _history_for(db_session, entity_type="deal", entity_id=deal_id)
        deleted = [e for e in entries if e.kind == "deal_deleted"]
        assert len(deleted) == 1
        event = event_from_meta(deleted[0].meta_json)
        assert isinstance(event, DealDeletedEntry)
        assert event.deal_title == deal_title
        assert event.deal_id == deal_id

    def test_delete_history_survives_entity_deletion(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)
        deal_id = deal.id

        client.delete(f"/deals/{deal_id}")

        # Verify the deal no longer exists but history does
        assert db_session.query(Deal).filter_by(id=deal_id).first() is None
        assert db_session.query(HistoryEntry).filter_by(entity_id=deal_id).count() >= 1


# ── GET /history endpoint ─────────────────────────────────────────────────────


class TestHistoryEndpoint:
    def test_returns_entries_for_entity(self, client, db_session):
        contact = _seed_contact(db_session)
        r = client.post("/deals", json={"title": "API Test Deal", "contact_id": contact.id})
        deal_id = r.json()["id"]

        r = client.get(f"/history?entity_type=deal&entity_id={deal_id}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) >= 1
        assert data[0]["kind"] == "deal_created"
        assert data[0]["entity_type"] == "deal"
        assert data[0]["entity_id"] == deal_id

    def test_invalid_entity_type_returns_422(self, client, db_session):
        r = client.get("/history?entity_type=bogus&entity_id=1")
        assert r.status_code == 422

    def test_entries_newest_first(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        client.patch(f"/deals/{deal.id}/stage", json={"stage": "qualified"})

        r = client.get(f"/history?entity_type=deal&entity_id={deal.id}")
        data = r.json()
        timestamps = [e["occurred_at"] for e in data]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_limit_param_respected(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        # Generate multiple history entries
        client.patch(f"/deals/{deal.id}", json={"title": "Title A"})
        client.patch(f"/deals/{deal.id}", json={"title": "Title B"})

        r = client.get(f"/history?entity_type=deal&entity_id={deal.id}&limit=1")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_invalid_limit_returns_422(self, client, db_session):
        r = client.get("/history?entity_type=deal&entity_id=1&limit=0")
        assert r.status_code == 422

    def test_no_cross_entity_leakage(self, client, db_session):
        contact = _seed_contact(db_session)
        r1 = client.post("/deals", json={"title": "Deal One", "contact_id": contact.id})
        r2 = client.post("/deals", json={"title": "Deal Two", "contact_id": contact.id})
        deal1_id = r1.json()["id"]
        deal2_id = r2.json()["id"]

        r = client.get(f"/history?entity_type=deal&entity_id={deal1_id}")
        data = r.json()
        assert all(e["entity_id"] == deal1_id for e in data)
        assert not any(e["entity_id"] == deal2_id for e in data)


# ── Contact triggers ──────────────────────────────────────────────────────────


class TestContactTriggers:
    def test_create_contact_creates_history(self, client, db_session):
        admin_id = _get_admin_id(client)
        r = client.post("/contacts", json={"name": "New Contact"})
        assert r.status_code == 201
        contact_id = r.json()["id"]

        entries = _history_for(db_session, entity_type="contact", entity_id=contact_id)
        assert len(entries) == 1
        assert entries[0].kind == "contact_created"
        event = event_from_meta(entries[0].meta_json)
        assert isinstance(event, ContactCreatedEntry)
        assert event.contact_name == "New Contact"
        assert entries[0].actor_id == admin_id

    def test_update_contact_creates_history(self, client, db_session):
        r = client.post("/contacts", json={"name": "Update Me"})
        contact_id = r.json()["id"]

        r = client.patch(f"/contacts/{contact_id}", json={"name": "Updated Name"})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="contact", entity_id=contact_id)
        kinds = [e.kind for e in entries]
        assert "contact_updated" in kinds
        updated = next(e for e in entries if e.kind == "contact_updated")
        event = event_from_meta(updated.meta_json)
        assert isinstance(event, ContactUpdatedEntry)
        assert event.contact_name == "Updated Name"

    def test_delete_contact_creates_history_that_survives(self, client, db_session):
        r = client.post("/contacts", json={"name": "Delete Me"})
        contact_id = r.json()["id"]
        contact_name = r.json()["name"]

        r = client.delete(f"/contacts/{contact_id}")
        assert r.status_code == 204

        entries = _history_for(db_session, entity_type="contact", entity_id=contact_id)
        deleted = [e for e in entries if e.kind == "contact_deleted"]
        assert len(deleted) == 1
        event = event_from_meta(deleted[0].meta_json)
        assert isinstance(event, ContactDeletedEntry)
        assert event.contact_name == contact_name

        # History row persists after entity deletion
        assert db_session.query(Contact).filter_by(id=contact_id).first() is None
        assert db_session.query(HistoryEntry).filter_by(entity_id=contact_id, entity_type="contact").count() >= 1


# ── Activity triggers ─────────────────────────────────────────────────────────


class TestActivityTriggers:
    def test_create_activity_creates_history(self, client, db_session):
        admin_id = _get_admin_id(client)
        r = client.post("/activities", json={
            "type": "call", "title": "Discovery Call",
        })
        assert r.status_code == 201
        activity_id = r.json()["id"]

        entries = _history_for(db_session, entity_type="activity", entity_id=activity_id)
        assert len(entries) == 1
        assert entries[0].kind == "activity_created"
        event = event_from_meta(entries[0].meta_json)
        assert isinstance(event, ActivityCreatedEntry)
        assert event.activity_type == "call"
        assert event.activity_title == "Discovery Call"
        assert entries[0].actor_id == admin_id

    def test_activity_created_carries_deal_and_contact_ids(self, client, db_session):
        admin_id = _get_admin_id(client)
        contact = _seed_contact(db_session)
        deal = _seed_deal(db_session, owner_id=admin_id, contact_id=contact.id)

        r = client.post("/activities", json={
            "type": "note", "title": "Deal Note",
            "deal_id": deal.id, "contact_id": contact.id,
        })
        activity_id = r.json()["id"]

        entries = _history_for(db_session, entity_type="activity", entity_id=activity_id)
        event = event_from_meta(entries[0].meta_json)
        assert isinstance(event, ActivityCreatedEntry)
        assert event.deal_id == deal.id
        assert event.contact_id == contact.id

    def test_update_activity_creates_history(self, client, db_session):
        r = client.post("/activities", json={"type": "email", "title": "First Draft"})
        activity_id = r.json()["id"]

        r = client.patch(f"/activities/{activity_id}", json={"title": "Final Draft"})
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="activity", entity_id=activity_id)
        kinds = [e.kind for e in entries]
        assert "activity_updated" in kinds
        updated = next(e for e in entries if e.kind == "activity_updated")
        event = event_from_meta(updated.meta_json)
        assert isinstance(event, ActivityUpdatedEntry)
        assert event.activity_title == "Final Draft"

    def test_complete_activity_creates_history(self, client, db_session):
        r = client.post("/activities", json={"type": "meeting", "title": "Kickoff"})
        activity_id = r.json()["id"]

        r = client.post(f"/activities/{activity_id}/complete")
        assert r.status_code == 200

        entries = _history_for(db_session, entity_type="activity", entity_id=activity_id)
        completed = [e for e in entries if e.kind == "activity_completed"]
        assert len(completed) == 1
        event = event_from_meta(completed[0].meta_json)
        assert isinstance(event, ActivityCompletedEntry)
        assert event.activity_type == "meeting"

    def test_delete_activity_creates_history_that_survives(self, client, db_session):
        r = client.post("/activities", json={"type": "call", "title": "Short Call"})
        activity_id = r.json()["id"]

        r = client.delete(f"/activities/{activity_id}")
        assert r.status_code == 204

        entries = _history_for(db_session, entity_type="activity", entity_id=activity_id)
        deleted = [e for e in entries if e.kind == "activity_deleted"]
        assert len(deleted) == 1
        event = event_from_meta(deleted[0].meta_json)
        assert isinstance(event, ActivityDeletedEntry)
        assert event.activity_type == "call"
