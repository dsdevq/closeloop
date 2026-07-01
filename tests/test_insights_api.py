"""API tests for GET /insights/* endpoints.

Covers all four endpoints plus explicit auth-scope tests for /insights/leaderboard:
- A rep-role request must never see another rep's data.
- Manager / admin requests must see all reps.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.core.security import create_access_token, hash_password
from app.database import Base, get_db
from app.main import app
from app.models import Contact, User


# ── DB / client setup ─────────────────────────────────────────────────────────

def _make_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(eng, "connect")
    def _pragmas(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    return eng


@pytest.fixture
def ic():
    """Insights client fixture.

    Seeds admin, manager, rep1, rep2 in one in-memory DB.
    Yields (admin_client, per_role_headers, user_ids, session_factory).
    admin_client uses admin's Bearer token as the default.
    """
    engine = _make_engine()
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        for role, name, email in [
            ("admin",   "Admin",   "admin@t.com"),
            ("manager", "Manager", "mgr@t.com"),
            ("rep",     "Rep One", "rep1@t.com"),
            ("rep",     "Rep Two", "rep2@t.com"),
        ]:
            db.add(User(
                email=email,
                hashed_password=hash_password("x"),
                role=role,
                full_name=name,
                created_at=now,
                is_active=1,
            ))
        db.commit()
        user_ids = {u.email: u.id for u in db.query(User).all()}

    tokens = {email: create_access_token(uid) for email, uid in user_ids.items()}
    headers = {email: {"Authorization": f"Bearer {t}"} for email, t in tokens.items()}

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, headers=headers["admin@t.com"]) as c:
        yield c, headers, user_ids, Session

    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_contact(client, name, email):
    r = client.post("/contacts", json={"name": name, "email": email})
    assert r.status_code == 201
    return r.json()["id"]


def _close_deal_as_won(client, contact_id, value, auth_header):
    """Create a deal owned by the bearer of auth_header and advance it to won."""
    r = client.post(
        "/deals",
        json={"title": "Won Deal", "contact_id": contact_id, "value": value},
        headers=auth_header,
    )
    assert r.status_code == 201
    deal_id = r.json()["id"]
    for stage in ["qualified", "proposal", "negotiation", "won"]:
        r2 = client.patch(
            f"/deals/{deal_id}/stage",
            json={"stage": stage},
            headers=auth_header,
        )
        assert r2.status_code == 200, f"stage advance to {stage!r} failed: {r2.json()}"
    return deal_id


# ── /insights/trends ──────────────────────────────────────────────────────────

def test_trends_empty_db_returns_empty_dict(ic):
    client, *_ = ic
    r = client.get("/insights/trends")
    assert r.status_code == 200
    assert r.json() == {}


def test_trends_counts_recently_created_deal(ic):
    client, *_ = ic
    cid = _make_contact(client, "Trnd", "trnd@x.com")
    client.post("/deals", json={"title": "T", "contact_id": cid, "value": 100.0})

    r = client.get("/insights/trends?window_days=30")
    assert r.status_code == 200
    data = r.json()
    assert data.get("lead", 0) >= 1


def test_trends_window_30_valid(ic):
    client, *_ = ic
    r = client.get("/insights/trends?window_days=30")
    assert r.status_code == 200


def test_trends_window_90_valid(ic):
    client, *_ = ic
    r = client.get("/insights/trends?window_days=90")
    assert r.status_code == 200


def test_trends_window_365_valid(ic):
    client, *_ = ic
    r = client.get("/insights/trends?window_days=365")
    assert r.status_code == 200


def test_trends_invalid_window_returns_422(ic):
    client, *_ = ic
    for bad in (7, 0, 1, 60, 999):
        r = client.get(f"/insights/trends?window_days={bad}")
        assert r.status_code == 422, f"window_days={bad} should be 422"


def test_trends_requires_auth(ic):
    client, *_ = ic
    r = client.get("/insights/trends", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401


# ── /insights/funnel ──────────────────────────────────────────────────────────

def test_funnel_empty_db_has_four_stages(ic):
    client, *_ = ic
    r = client.get("/insights/funnel")
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) == {"lead", "qualified", "proposal", "negotiation"}


def test_funnel_stage_shape(ic):
    client, *_ = ic
    r = client.get("/insights/funnel")
    assert r.status_code == 200
    for stage_data in r.json().values():
        assert "conversion_rate" in stage_data
        assert "avg_time_in_stage_days" in stage_data


def test_funnel_rates_in_valid_range(ic):
    client, *_ = ic
    cid = _make_contact(client, "Fn", "fn@x.com")
    client.post("/deals", json={"title": "F", "contact_id": cid, "value": 500.0})

    r = client.get("/insights/funnel")
    assert r.status_code == 200
    for stage_data in r.json().values():
        rate = stage_data["conversion_rate"]
        assert 0.0 <= rate <= 1.0


def test_funnel_requires_auth(ic):
    client, *_ = ic
    r = client.get("/insights/funnel", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401


# ── /insights/leaderboard ─────────────────────────────────────────────────────

def test_leaderboard_empty_db_returns_empty_list(ic):
    client, *_ = ic
    r = client.get("/insights/leaderboard")
    assert r.status_code == 200
    assert r.json() == []


def test_leaderboard_row_shape(ic):
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "LB", "lb@x.com")
    rep1_h = headers["rep1@t.com"]
    _close_deal_as_won(client, cid, 1000.0, rep1_h)

    r = client.get("/insights/leaderboard")  # admin sees all
    assert r.status_code == 200
    assert len(r.json()) >= 1
    row = r.json()[0]
    assert "owner_id" in row
    assert "owner_name" in row
    assert "revenue" in row
    assert "deals_closed" in row
    assert "avg_cycle_days" in row


def test_leaderboard_owner_name_joined_from_user(ic):
    """owner_name must equal the User.full_name for the rep who owns the deal."""
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "NameJoin", "namejoin@x.com")
    rep1_h = headers["rep1@t.com"]
    _close_deal_as_won(client, cid, 500.0, rep1_h)

    r = client.get("/insights/leaderboard")
    assert r.status_code == 200
    rows = r.json()
    rep1_row = next(row for row in rows if row["owner_id"] == user_ids["rep1@t.com"])
    assert rep1_row["owner_name"] == "Rep One"


def test_leaderboard_admin_sees_all_reps(ic):
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "Ldbd", "ldbd@x.com")
    rep1_h = headers["rep1@t.com"]
    rep2_h = headers["rep2@t.com"]
    _close_deal_as_won(client, cid, 1000.0, rep1_h)
    _close_deal_as_won(client, cid, 2000.0, rep2_h)

    r = client.get("/insights/leaderboard")  # admin token (default)
    assert r.status_code == 200
    owner_ids = {row["owner_id"] for row in r.json()}
    assert user_ids["rep1@t.com"] in owner_ids
    assert user_ids["rep2@t.com"] in owner_ids


def test_leaderboard_manager_sees_all_reps(ic):
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "Ldbd2", "ldbd2@x.com")
    rep1_h = headers["rep1@t.com"]
    rep2_h = headers["rep2@t.com"]
    _close_deal_as_won(client, cid, 1500.0, rep1_h)
    _close_deal_as_won(client, cid, 2500.0, rep2_h)

    r = client.get("/insights/leaderboard", headers=headers["mgr@t.com"])
    assert r.status_code == 200
    owner_ids = {row["owner_id"] for row in r.json()}
    assert user_ids["rep1@t.com"] in owner_ids
    assert user_ids["rep2@t.com"] in owner_ids


def test_leaderboard_rep_sees_only_own_row(ic):
    """A rep-role request must be scoped to their own data server-side."""
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "Ldbd3", "ldbd3@x.com")
    rep1_h = headers["rep1@t.com"]
    rep2_h = headers["rep2@t.com"]
    _close_deal_as_won(client, cid, 5000.0, rep1_h)
    _close_deal_as_won(client, cid, 9000.0, rep2_h)

    r = client.get("/insights/leaderboard", headers=rep1_h)
    assert r.status_code == 200
    data = r.json()
    # rep1 must only see their own single row
    assert len(data) == 1
    assert data[0]["owner_id"] == user_ids["rep1@t.com"]
    assert data[0]["revenue"] == pytest.approx(5000.0)


def test_leaderboard_rep_cannot_see_other_rep_data(ic):
    """rep2's high-value deal must be invisible to rep1 regardless of what rep1 requests."""
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "Ldbd4", "ldbd4@x.com")
    rep1_h = headers["rep1@t.com"]
    rep2_h = headers["rep2@t.com"]
    _close_deal_as_won(client, cid, 100.0, rep1_h)
    _close_deal_as_won(client, cid, 99999.0, rep2_h)  # rep2's big deal

    r = client.get("/insights/leaderboard", headers=rep1_h)
    assert r.status_code == 200
    data = r.json()
    owner_ids = {row["owner_id"] for row in data}
    # rep2's ID must never appear in rep1's leaderboard view
    assert user_ids["rep2@t.com"] not in owner_ids
    # rep1's revenue is only their own deal, not inflated by rep2's deal
    assert data[0]["revenue"] == pytest.approx(100.0)


def test_leaderboard_avg_cycle_days_populated_after_close(ic):
    """avg_cycle_days must be non-None after a deal is properly closed via the API."""
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "CycleTest", "cycle@x.com")
    rep1_h = headers["rep1@t.com"]
    _close_deal_as_won(client, cid, 1000.0, rep1_h)

    r = client.get("/insights/leaderboard")
    assert r.status_code == 200
    rows = r.json()
    rep1_row = next(row for row in rows if row["owner_id"] == user_ids["rep1@t.com"])
    assert rep1_row["avg_cycle_days"] is not None
    assert rep1_row["avg_cycle_days"] >= 0.0


def test_leaderboard_avg_cycle_days_none_for_open_only_rep(ic):
    """A rep with only open (non-won) deals must not appear in the leaderboard at all."""
    client, headers, user_ids, _ = ic
    cid = _make_contact(client, "OpenOnly", "openonly@x.com")
    rep1_h = headers["rep1@t.com"]
    # Create a deal but leave it in lead stage (never advance to won)
    client.post(
        "/deals",
        json={"title": "Open Deal", "contact_id": cid, "value": 500.0},
        headers=rep1_h,
    )

    r = client.get("/insights/leaderboard", headers=rep1_h)
    assert r.status_code == 200
    assert r.json() == []


def test_leaderboard_requires_auth(ic):
    client, *_ = ic
    r = client.get("/insights/leaderboard", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401


# ── /insights/cohorts ─────────────────────────────────────────────────────────

def test_cohorts_empty_db_returns_empty_dict(ic):
    client, *_ = ic
    r = client.get("/insights/cohorts")
    assert r.status_code == 200
    assert r.json() == {}


def test_cohorts_no_source_falls_back_to_other(ic):
    """Contacts created via API have source=NULL, which maps to 'other'."""
    client, *_ = ic
    cid = _make_contact(client, "Coh", "coh@x.com")
    client.post("/deals", json={"title": "C", "contact_id": cid, "value": 300.0})

    r = client.get("/insights/cohorts")
    assert r.status_code == 200
    data = r.json()
    # source=NULL is mapped to 'other' by source_cohorts()
    assert "other" in data
    assert data["other"]["deal_count"] >= 1


def test_cohorts_with_explicit_source(ic):
    """Insert a contact with source='referral' directly and verify it surfaces."""
    client, _, user_ids, Session = ic
    now = datetime.now(timezone.utc).isoformat()
    with Session() as db:
        contact = Contact(
            name="Ref Person",
            email="ref@x.com",
            source="referral",
            owner_id=user_ids["admin@t.com"],
            created_at=now,
            updated_at=now,
        )
        db.add(contact)
        db.commit()
        db.refresh(contact)
        cid = contact.id

    client.post("/deals", json={"title": "Ref Deal", "contact_id": cid, "value": 2000.0})

    r = client.get("/insights/cohorts")
    assert r.status_code == 200
    data = r.json()
    assert "referral" in data
    assert data["referral"]["deal_count"] >= 1
    assert data["referral"]["avg_deal_value"] == pytest.approx(2000.0)


def test_cohorts_row_shape(ic):
    client, *_ = ic
    cid = _make_contact(client, "Csh", "csh@x.com")
    client.post("/deals", json={"title": "Sh", "contact_id": cid, "value": 100.0})

    r = client.get("/insights/cohorts")
    assert r.status_code == 200
    for row in r.json().values():
        assert "deal_count" in row
        assert "avg_deal_value" in row
        assert "win_rate" in row


def test_cohorts_requires_auth(ic):
    client, *_ = ic
    r = client.get("/insights/cohorts", headers={"Authorization": "Bearer badtoken"})
    assert r.status_code == 401
