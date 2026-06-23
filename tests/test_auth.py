"""Tests for authentication, authorization, and role enforcement."""
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


def _make_session_factory(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_db(Session):
    def _override():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    return _override


def _make_client(Session, headers=None):
    app.dependency_overrides[get_db] = _override_db(Session)
    return TestClient(app, headers=headers or {}, raise_server_exceptions=True)


def _cleanup(engine):
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def _create_user(Session, email, password, role="rep", full_name=""):
    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            full_name=full_name,
            created_at=now,
            is_active=1,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


@pytest.fixture
def fresh_setup():
    """Fresh in-memory DB with no pre-existing users.  Yields (client, Session, engine)."""
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session_factory(engine)
    client = _make_client(Session)
    yield client, Session, engine
    _cleanup(engine)


@pytest.fixture
def admin_setup():
    """Fresh DB pre-seeded with an admin user.  Yields (admin_client, Session, engine, admin_token)."""
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = _make_session_factory(engine)
    admin_id = _create_user(Session, "admin@t.com", "adminpass", role="admin", full_name="Admin")
    token = create_access_token(admin_id)
    client = _make_client(Session, {"Authorization": f"Bearer {token}"})
    yield client, Session, engine, token
    _cleanup(engine)


# ── Register ───────────────────────────────────────────────────────────────────

def test_register_first_user_open(fresh_setup):
    client, Session, engine = fresh_setup
    res = client.post("/auth/register", json={
        "email": "first@example.com",
        "password": "secret123",
        "full_name": "First User",
        "role": "admin",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "first@example.com"
    assert data["role"] == "admin"
    assert "hashed_password" not in data
    assert "password" not in data


def test_register_second_user_requires_admin(fresh_setup):
    client, Session, engine = fresh_setup
    # Create first user (open)
    client.post("/auth/register", json={"email": "admin@t.com", "password": "pass", "role": "admin"})

    # Second registration without token must fail
    res = client.post("/auth/register", json={"email": "rep@t.com", "password": "pass"})
    assert res.status_code == 401


def test_register_second_user_with_admin_token(fresh_setup):
    client, Session, engine = fresh_setup
    # First user (admin)
    client.post("/auth/register", json={"email": "admin@t.com", "password": "pass", "role": "admin"})
    login_res = client.post("/auth/login", json={"email": "admin@t.com", "password": "pass"})
    token = login_res.json()["access_token"]

    # Second registration with admin token
    res = client.post(
        "/auth/register",
        json={"email": "rep@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    assert res.json()["role"] == "rep"


def test_register_duplicate_email_rejected(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "dup@t.com", "password": "pass", "role": "admin"})
    # Second attempt as admin
    token = client.post("/auth/login", json={"email": "dup@t.com", "password": "pass"}).json()["access_token"]
    res = client.post(
        "/auth/register",
        json={"email": "dup@t.com", "password": "pass"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 422


def test_register_invalid_role_rejected(fresh_setup):
    client, Session, engine = fresh_setup
    res = client.post("/auth/register", json={"email": "x@t.com", "password": "pass", "role": "superuser"})
    assert res.status_code == 422


# ── Login ──────────────────────────────────────────────────────────────────────

def test_login_correct_credentials(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "user@t.com", "password": "correct"})
    res = client.post("/auth/login", json={"email": "user@t.com", "password": "correct"})
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "user@t.com"


def test_login_wrong_password(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "user@t.com", "password": "correct"})
    res = client.post("/auth/login", json={"email": "user@t.com", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_email(fresh_setup):
    client, Session, engine = fresh_setup
    res = client.post("/auth/login", json={"email": "nobody@t.com", "password": "pass"})
    assert res.status_code == 401


# ── Token refresh and logout ───────────────────────────────────────────────────

def test_refresh_returns_new_access_token(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "u@t.com", "password": "pass"})
    tokens = client.post("/auth/login", json={"email": "u@t.com", "password": "pass"}).json()

    res = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 200
    new_data = res.json()
    assert "access_token" in new_data
    assert new_data["access_token"] != tokens["access_token"]


def test_refresh_after_logout_fails(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "u@t.com", "password": "pass"})
    tokens = client.post("/auth/login", json={"email": "u@t.com", "password": "pass"}).json()

    # Logout revokes refresh token
    logout_res = client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]})
    assert logout_res.status_code == 204

    # Refresh with revoked token must fail
    res = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 401


# ── Protected endpoint enforcement ────────────────────────────────────────────

def test_contacts_requires_bearer_token(fresh_setup):
    client, Session, engine = fresh_setup
    # No auth header
    res = client.get("/contacts")
    assert res.status_code == 401


def test_contacts_with_valid_token_succeeds(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "u@t.com", "password": "pass"})
    token = client.post("/auth/login", json={"email": "u@t.com", "password": "pass"}).json()["access_token"]
    res = client.get("/contacts", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_contacts_with_garbage_token_is_401(fresh_setup):
    client, Session, engine = fresh_setup
    res = client.get("/contacts", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


# ── /auth/me ──────────────────────────────────────────────────────────────────

def test_me_returns_current_user(fresh_setup):
    client, Session, engine = fresh_setup
    client.post("/auth/register", json={"email": "me@t.com", "password": "pass", "full_name": "Me User"})
    token = client.post("/auth/login", json={"email": "me@t.com", "password": "pass"}).json()["access_token"]
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["email"] == "me@t.com"
    assert res.json()["full_name"] == "Me User"


# ── Role enforcement: rep vs admin ────────────────────────────────────────────

def test_rep_cannot_see_another_reps_contacts(admin_setup):
    """A rep's GET /contacts must not return contacts owned by another rep."""
    admin_client, Session, engine, admin_token = admin_setup

    # Create rep1 and rep2 via admin
    admin_client.post(
        "/auth/register",
        json={"email": "rep1@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    admin_client.post(
        "/auth/register",
        json={"email": "rep2@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    rep1_token = admin_client.post("/auth/login", json={"email": "rep1@t.com", "password": "pass"}).json()["access_token"]
    rep2_token = admin_client.post("/auth/login", json={"email": "rep2@t.com", "password": "pass"}).json()["access_token"]

    # rep1 creates a contact
    admin_client.post(
        "/contacts",
        json={"name": "Rep1 Contact", "email": "c1@t.com"},
        headers={"Authorization": f"Bearer {rep1_token}"},
    )

    # rep2 should NOT see rep1's contact
    res = admin_client.get("/contacts", headers={"Authorization": f"Bearer {rep2_token}"})
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert "Rep1 Contact" not in names


def test_admin_sees_all_contacts(admin_setup):
    """Admin sees all contacts regardless of owner."""
    admin_client, Session, engine, admin_token = admin_setup

    admin_client.post(
        "/auth/register",
        json={"email": "rep@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rep_token = admin_client.post("/auth/login", json={"email": "rep@t.com", "password": "pass"}).json()["access_token"]

    # rep creates a contact
    admin_client.post(
        "/contacts",
        json={"name": "Rep Contact"},
        headers={"Authorization": f"Bearer {rep_token}"},
    )
    # admin creates a contact
    admin_client.post("/contacts", json={"name": "Admin Contact"})

    # admin sees both
    res = admin_client.get("/contacts")
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert "Rep Contact" in names
    assert "Admin Contact" in names


def test_manager_sees_all_contacts(admin_setup):
    """Manager sees all contacts (no ownership filter)."""
    admin_client, Session, engine, admin_token = admin_setup

    admin_client.post(
        "/auth/register",
        json={"email": "mgr@t.com", "password": "pass", "role": "manager"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    admin_client.post(
        "/auth/register",
        json={"email": "rep@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    mgr_token = admin_client.post("/auth/login", json={"email": "mgr@t.com", "password": "pass"}).json()["access_token"]
    rep_token = admin_client.post("/auth/login", json={"email": "rep@t.com", "password": "pass"}).json()["access_token"]

    # rep creates a contact
    admin_client.post(
        "/contacts",
        json={"name": "Rep Owned"},
        headers={"Authorization": f"Bearer {rep_token}"},
    )

    # manager sees it
    res = admin_client.get("/contacts", headers={"Authorization": f"Bearer {mgr_token}"})
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert "Rep Owned" in names


def test_non_admin_cannot_list_users(admin_setup):
    """GET /auth/users is admin-only."""
    admin_client, Session, engine, admin_token = admin_setup

    admin_client.post(
        "/auth/register",
        json={"email": "rep@t.com", "password": "pass", "role": "rep"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    rep_token = admin_client.post("/auth/login", json={"email": "rep@t.com", "password": "pass"}).json()["access_token"]

    res = admin_client.get("/auth/users", headers={"Authorization": f"Bearer {rep_token}"})
    assert res.status_code == 403


def test_admin_can_list_users(admin_setup):
    """Admin can list all users."""
    admin_client, Session, engine, admin_token = admin_setup
    res = admin_client.get("/auth/users")
    assert res.status_code == 200
    assert len(res.json()) >= 1
