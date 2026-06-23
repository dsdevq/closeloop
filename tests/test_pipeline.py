"""Tests for pipeline stages CRUD, role enforcement, and deal stage_id updates."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import PipelineStage, User


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    return engine


def _make_session(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_db(Session):
    def _inner():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    return _inner


def _cleanup(engine):
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _seed_user(Session, email, password="pass", role="admin"):
    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        u = User(email=email, hashed_password=hash_password(password), role=role,
                 full_name="", created_at=now, is_active=1)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


def _seed_stages(Session):
    """Insert 3 default stages for tests that need them."""
    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        stages = [
            PipelineStage(name="Prospecting",  position=0, probability=0,   is_default=1, created_at=now),
            PipelineStage(name="Qualification", position=1, probability=20,  is_default=1, created_at=now),
            PipelineStage(name="Closed-Won",    position=2, probability=100, is_default=1, created_at=now),
        ]
        db.add_all(stages)
        db.commit()
        return [s.id for s in stages]


def _make_client(Session, user_id):
    token = create_access_token(user_id)
    app.dependency_overrides[get_db] = _override_db(Session)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


# ── List stages (public-to-authenticated) ──────────────────────────────────────

def test_list_stages_empty(client):
    res = client.get("/pipeline/stages")
    assert res.status_code == 200
    assert res.json() == []


def test_list_stages_returns_seeded(client):
    # Create stages then list them
    client.post("/pipeline/stages", json={"name": "Alpha", "position": 0, "probability": 10})
    client.post("/pipeline/stages", json={"name": "Beta",  "position": 1, "probability": 50})
    res = client.get("/pipeline/stages")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert data[0]["name"] == "Alpha"
    assert data[1]["name"] == "Beta"


def test_list_stages_ordered_by_position(client):
    client.post("/pipeline/stages", json={"name": "Third", "position": 2, "probability": 75})
    client.post("/pipeline/stages", json={"name": "First", "position": 0, "probability": 0})
    client.post("/pipeline/stages", json={"name": "Second","position": 1, "probability": 50})
    res = client.get("/pipeline/stages")
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert names == ["First", "Second", "Third"]


def test_list_stages_requires_auth():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    app.dependency_overrides[get_db] = _override_db(Session)
    try:
        c = TestClient(app)
        res = c.get("/pipeline/stages")
        assert res.status_code == 401
    finally:
        _cleanup(engine)


# ── Create stage (admin/manager only) ─────────────────────────────────────────

def test_create_stage_as_admin_returns_201(client):
    res = client.post("/pipeline/stages", json={"name": "Discovery", "position": 0, "probability": 15})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Discovery"
    assert data["position"] == 0
    assert data["probability"] == 15
    assert data["is_default"] is False
    assert "id" in data
    assert "created_at" in data


def test_create_stage_probability_out_of_range(client):
    res = client.post("/pipeline/stages", json={"name": "Bad", "position": 0, "probability": 150})
    assert res.status_code == 422


def test_create_stage_as_rep_is_forbidden():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    rep_id = _seed_user(Session, "rep@t.com", role="rep")
    c = _make_client(Session, rep_id)
    try:
        res = c.post("/pipeline/stages", json={"name": "Sneaky", "position": 0, "probability": 10})
        assert res.status_code == 403
    finally:
        _cleanup(engine)


def test_create_stage_as_manager_succeeds():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    mgr_id = _seed_user(Session, "mgr@t.com", role="manager")
    c = _make_client(Session, mgr_id)
    try:
        res = c.post("/pipeline/stages", json={"name": "Pipeline Stage", "position": 0, "probability": 25})
        assert res.status_code == 201
    finally:
        _cleanup(engine)


# ── Update stage ──────────────────────────────────────────────────────────────

def test_patch_stage(client):
    create_res = client.post("/pipeline/stages", json={"name": "Old", "position": 0, "probability": 10})
    stage_id = create_res.json()["id"]

    res = client.patch(f"/pipeline/stages/{stage_id}", json={"name": "New", "probability": 30})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "New"
    assert data["probability"] == 30
    assert data["position"] == 0  # unchanged


def test_patch_stage_404(client):
    res = client.patch("/pipeline/stages/99999", json={"name": "Ghost"})
    assert res.status_code == 404


def test_patch_stage_probability_out_of_range(client):
    create_res = client.post("/pipeline/stages", json={"name": "Valid", "position": 0, "probability": 10})
    stage_id = create_res.json()["id"]
    res = client.patch(f"/pipeline/stages/{stage_id}", json={"probability": 200})
    assert res.status_code == 422


def test_patch_stage_as_rep_is_forbidden():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    admin_id = _seed_user(Session, "admin@t.com", role="admin")
    rep_id = _seed_user(Session, "rep@t.com", role="rep")

    admin_client = _make_client(Session, admin_id)
    stage_id = admin_client.post("/pipeline/stages", json={"name": "S", "position": 0, "probability": 0}).json()["id"]

    rep_client = _make_client(Session, rep_id)
    res = rep_client.patch(f"/pipeline/stages/{stage_id}", json={"name": "Hijacked"})
    assert res.status_code == 403

    _cleanup(engine)


# ── Delete stage ──────────────────────────────────────────────────────────────

def test_delete_stage_204(client):
    create_res = client.post("/pipeline/stages", json={"name": "Temp", "position": 0, "probability": 0})
    stage_id = create_res.json()["id"]

    res = client.delete(f"/pipeline/stages/{stage_id}")
    assert res.status_code == 204

    stages = client.get("/pipeline/stages").json()
    assert not any(s["id"] == stage_id for s in stages)


def test_delete_stage_404(client):
    res = client.delete("/pipeline/stages/99999")
    assert res.status_code == 404


def test_delete_stage_with_deals_returns_409(client):
    # Create stage
    stage_res = client.post("/pipeline/stages", json={"name": "Occupied", "position": 0, "probability": 10})
    stage_id = stage_res.json()["id"]

    # Create contact and deal assigned to this stage
    c_res = client.post("/contacts", json={"name": "Alice", "email": "alice@example.com"})
    contact_id = c_res.json()["id"]
    deal_res = client.post("/deals", json={"title": "Big Deal", "contact_id": contact_id})
    deal_id = deal_res.json()["id"]

    # Assign deal to the stage via PATCH
    client.patch(f"/deals/{deal_id}", json={"stage_id": stage_id})

    # Now try to delete the stage
    res = client.delete(f"/pipeline/stages/{stage_id}")
    assert res.status_code == 409
    assert "1" in res.json()["detail"]


def test_delete_stage_as_rep_is_forbidden():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    admin_id = _seed_user(Session, "admin@t.com", role="admin")
    rep_id = _seed_user(Session, "rep@t.com", role="rep")

    admin_client = _make_client(Session, admin_id)
    stage_id = admin_client.post("/pipeline/stages", json={"name": "S", "position": 0, "probability": 0}).json()["id"]

    rep_client = _make_client(Session, rep_id)
    res = rep_client.delete(f"/pipeline/stages/{stage_id}")
    assert res.status_code == 403

    _cleanup(engine)


# ── Deal stage_id PATCH (kanban drag-and-drop) ──────────────────────────────────

def test_patch_deal_stage_id_updates_stage(client):
    stage_res = client.post("/pipeline/stages", json={"name": "Prospect", "position": 0, "probability": 10})
    stage_id = stage_res.json()["id"]

    c_res = client.post("/contacts", json={"name": "Bob", "email": "bob@x.com"})
    contact_id = c_res.json()["id"]
    deal_res = client.post("/deals", json={"title": "Kanban Move", "contact_id": contact_id})
    deal_id = deal_res.json()["id"]

    res = client.patch(f"/deals/{deal_id}", json={"stage_id": stage_id})
    assert res.status_code == 200
    data = res.json()
    assert data["stage_id"] == stage_id
    assert data["stage_name"] == "Prospect"
    # probability inherited from stage (10% -> 0.10)
    assert abs(data["probability"] - 0.10) < 0.001


def test_patch_deal_stage_id_probability_inherits_from_stage(client):
    stage_res = client.post("/pipeline/stages", json={"name": "Proposal", "position": 1, "probability": 50})
    stage_id = stage_res.json()["id"]

    c_res = client.post("/contacts", json={"name": "Carol", "email": "carol@x.com"})
    deal_res = client.post("/deals", json={"title": "Prop Deal", "contact_id": c_res.json()["id"]})
    deal_id = deal_res.json()["id"]

    res = client.patch(f"/deals/{deal_id}", json={"stage_id": stage_id})
    assert res.status_code == 200
    assert abs(res.json()["probability"] - 0.50) < 0.001


def test_patch_deal_stage_id_probability_override(client):
    stage_res = client.post("/pipeline/stages", json={"name": "Neg", "position": 2, "probability": 75})
    stage_id = stage_res.json()["id"]

    c_res = client.post("/contacts", json={"name": "Dan", "email": "dan@x.com"})
    deal_res = client.post("/deals", json={"title": "Override Deal", "contact_id": c_res.json()["id"]})
    deal_id = deal_res.json()["id"]

    # Explicitly override probability while also setting stage_id
    res = client.patch(f"/deals/{deal_id}", json={"stage_id": stage_id, "probability": 0.85})
    assert res.status_code == 200
    assert abs(res.json()["probability"] - 0.85) < 0.001


def test_patch_deal_invalid_stage_id_returns_404(client):
    c_res = client.post("/contacts", json={"name": "Eve", "email": "eve@x.com"})
    deal_res = client.post("/deals", json={"title": "No Stage", "contact_id": c_res.json()["id"]})
    deal_id = deal_res.json()["id"]

    res = client.patch(f"/deals/{deal_id}", json={"stage_id": 99999})
    assert res.status_code == 404


def test_deal_to_out_includes_stage_fields(client):
    stage_res = client.post("/pipeline/stages", json={"name": "Qualified", "position": 0, "probability": 20})
    stage_id = stage_res.json()["id"]

    c_res = client.post("/contacts", json={"name": "Frank", "email": "frank@x.com"})
    deal_res = client.post("/deals", json={"title": "Full Deal", "contact_id": c_res.json()["id"]})
    deal_id = deal_res.json()["id"]
    client.patch(f"/deals/{deal_id}", json={"stage_id": stage_id})

    res = client.get(f"/deals/{deal_id}")
    assert res.status_code == 200
    data = res.json()
    assert "stage_id" in data
    assert "stage_name" in data
    assert data["stage_id"] == stage_id
    assert data["stage_name"] == "Qualified"
