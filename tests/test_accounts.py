"""Tests for Accounts (Companies) CRUD and role enforcement."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import User


# ── Fixtures ───────────────────────────────────────────────────────────────────

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


def _seed_user(Session, email, password="pass", role="admin"):
    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        u = User(email=email, hashed_password=hash_password(password), role=role,
                 full_name="", created_at=now, is_active=1)
        db.add(u)
        db.commit()
        db.refresh(u)
        return u.id


def _make_client(Session, user_id):
    token = create_access_token(user_id)
    app.dependency_overrides[get_db] = _override_db(Session)
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _cleanup(engine):
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


# ── Simple CRUD (using the default conftest admin client) ───────────────────────

def test_create_account_returns_201(client):
    res = client.post("/accounts", json={"name": "Acme Corp", "domain": "acme.com", "industry": "Tech"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Acme Corp"
    assert data["domain"] == "acme.com"
    assert data["industry"] == "Tech"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data
    assert "owner_id" in data


def test_create_account_minimal(client):
    res = client.post("/accounts", json={"name": "Bare Co"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Bare Co"
    assert data["domain"] is None
    assert data["industry"] is None


def test_list_accounts_returns_created(client):
    client.post("/accounts", json={"name": "Alpha Inc"})
    client.post("/accounts", json={"name": "Beta Ltd"})
    res = client.get("/accounts")
    assert res.status_code == 200
    names = [a["name"] for a in res.json()]
    assert "Alpha Inc" in names
    assert "Beta Ltd" in names


def test_list_accounts_contact_count(client):
    acct_res = client.post("/accounts", json={"name": "CountCo"})
    acct_id = acct_res.json()["id"]

    client.post("/contacts", json={"name": "C1", "email": "c1@x.com", "account_id": acct_id})
    client.post("/contacts", json={"name": "C2", "email": "c2@x.com", "account_id": acct_id})

    res = client.get("/accounts")
    acct = next(a for a in res.json() if a["id"] == acct_id)
    assert acct["contact_count"] == 2


def test_get_account_returns_linked_contacts(client):
    acct_res = client.post("/accounts", json={"name": "LinkedCo"})
    acct_id = acct_res.json()["id"]
    client.post("/contacts", json={"name": "Anna", "email": "anna@x.com", "account_id": acct_id})
    client.post("/contacts", json={"name": "Bob", "email": "bob@x.com", "account_id": acct_id})

    res = client.get(f"/accounts/{acct_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "LinkedCo"
    assert data["contact_count"] == 2
    contact_names = [c["name"] for c in data["contacts"]]
    assert "Anna" in contact_names
    assert "Bob" in contact_names


def test_get_account_404(client):
    res = client.get("/accounts/99999")
    assert res.status_code == 404


def test_patch_account(client):
    acct_res = client.post("/accounts", json={"name": "Old Name", "domain": "old.com"})
    acct_id = acct_res.json()["id"]

    res = client.patch(f"/accounts/{acct_id}", json={"name": "New Name", "industry": "Finance"})
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "New Name"
    assert data["industry"] == "Finance"
    assert data["domain"] == "old.com"  # unchanged


def test_patch_account_404(client):
    res = client.patch("/accounts/99999", json={"name": "Ghost"})
    assert res.status_code == 404


def test_delete_account_returns_204(client):
    acct_res = client.post("/accounts", json={"name": "DeleteMe"})
    acct_id = acct_res.json()["id"]

    res = client.delete(f"/accounts/{acct_id}")
    assert res.status_code == 204

    res = client.get(f"/accounts/{acct_id}")
    assert res.status_code == 404


def test_delete_account_404(client):
    res = client.delete("/accounts/99999")
    assert res.status_code == 404


def test_contact_linked_to_account(client):
    acct_res = client.post("/accounts", json={"name": "ParentCo"})
    acct_id = acct_res.json()["id"]

    c_res = client.post("/contacts", json={"name": "Eve", "email": "eve@x.com", "account_id": acct_id})
    assert c_res.status_code == 201
    assert c_res.json()["account_id"] == acct_id


def test_contact_account_id_in_list(client):
    acct_res = client.post("/accounts", json={"name": "ListCo"})
    acct_id = acct_res.json()["id"]
    client.post("/contacts", json={"name": "Frank", "email": "frank@x.com", "account_id": acct_id})

    res = client.get("/contacts")
    assert res.status_code == 200
    frank = next((c for c in res.json() if c["name"] == "Frank"), None)
    assert frank is not None
    assert frank["account_id"] == acct_id


def test_accounts_requires_auth():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)
    app.dependency_overrides[get_db] = _override_db(Session)
    try:
        c = TestClient(app)
        res = c.get("/accounts")
        assert res.status_code == 401
    finally:
        _cleanup(engine)


# ── Role enforcement: rep cannot see another rep's account ─────────────────────

def test_rep_cannot_see_other_reps_account():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)

    rep1_id = _seed_user(Session, "rep1@t.com", role="rep")
    rep2_id = _seed_user(Session, "rep2@t.com", role="rep")

    # rep1 creates an account
    rep1_client = _make_client(Session, rep1_id)
    res = rep1_client.post("/accounts", json={"name": "Rep1 Account"})
    assert res.status_code == 201

    # rep2 should not see rep1's account
    rep2_client = _make_client(Session, rep2_id)
    res = rep2_client.get("/accounts")
    assert res.status_code == 200
    assert all(a["owner_id"] == rep2_id for a in res.json())

    _cleanup(engine)


def test_manager_sees_all_accounts():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)

    rep_id = _seed_user(Session, "rep@t.com", role="rep")
    mgr_id = _seed_user(Session, "mgr@t.com", role="manager")

    rep_client = _make_client(Session, rep_id)
    rep_client.post("/accounts", json={"name": "Rep Account"})

    mgr_client = _make_client(Session, mgr_id)
    res = mgr_client.get("/accounts")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    _cleanup(engine)


def test_admin_sees_all_accounts():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)

    rep_id = _seed_user(Session, "rep@t.com", role="rep")
    admin_id = _seed_user(Session, "admin@t.com", role="admin")

    rep_client = _make_client(Session, rep_id)
    rep_client.post("/accounts", json={"name": "Rep Account"})

    admin_client = _make_client(Session, admin_id)
    res = admin_client.get("/accounts")
    assert res.status_code == 200
    assert len(res.json()) >= 1

    _cleanup(engine)


def test_rep_cannot_get_other_reps_account_by_id():
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session(engine)

    rep1_id = _seed_user(Session, "rep1@t.com", role="rep")
    rep2_id = _seed_user(Session, "rep2@t.com", role="rep")

    rep1_client = _make_client(Session, rep1_id)
    acct_id = rep1_client.post("/accounts", json={"name": "Rep1 Only"}).json()["id"]

    rep2_client = _make_client(Session, rep2_id)
    res = rep2_client.get(f"/accounts/{acct_id}")
    assert res.status_code == 404

    _cleanup(engine)
