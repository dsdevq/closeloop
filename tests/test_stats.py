"""API tests for GET /stats."""
from datetime import datetime, timedelta, timezone

from app.core.clock import Clock, get_clock
from app.main import app

_EXPECTED_KEYS = {
    "total_contacts",
    "total_deals",
    "total_activities",
    "deals_by_stage",
    "pipeline_value",
    "weighted_forecast",
    "activities_last_30_days",
    "outbox_queued",
}


class FixedClock:
    def __init__(self, dt: datetime):
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def _now_utc():
    return datetime.now(timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_contact(client, name="Alice", email="alice@example.com"):
    r = client.post("/contacts", json={"name": name, "email": email})
    assert r.status_code == 201
    return r.json()


def _make_deal(client, contact_id, value=1000.0, stage="lead"):
    r = client.post("/deals", json={"title": "Deal", "contact_id": contact_id, "value": value})
    assert r.status_code == 201
    d = r.json()
    if stage != "lead":
        # advance through stages sequentially
        path = ["lead", "qualified", "proposal", "negotiation", "won", "lost"]
        cur = "lead"
        for s in path[1:]:
            if cur == stage:
                break
            client.patch(f"/deals/{d['id']}/stage", json={"stage": s})
            cur = s
    return d


def _make_activity(client, contact_id):
    r = client.post("/activities", json={
        "contact_id": contact_id,
        "type": "call",
        "title": "Follow up",
    })
    assert r.status_code == 201
    return r.json()


def _queue_outbox(client):
    r = client.post("/outbox", json={"to_address": "x@x.com", "subject": "S", "body": "B"})
    assert r.status_code == 201
    return r.json()


# ── Tests ────────────────────────────────────────────────────────────────────

def test_stats_returns_all_expected_keys(client):
    r = client.get("/stats")
    assert r.status_code == 200
    assert _EXPECTED_KEYS.issubset(r.json().keys())


def test_stats_total_contacts(client):
    _make_contact(client, "Alice", "a@x.com")
    _make_contact(client, "Bob", "b@x.com")
    r = client.get("/stats")
    assert r.json()["total_contacts"] == 2


def test_stats_total_deals(client):
    c = _make_contact(client)
    _make_deal(client, c["id"])
    _make_deal(client, c["id"])
    r = client.get("/stats")
    assert r.json()["total_deals"] == 2


def test_deals_by_stage_reflects_seeded_deals(client):
    c = _make_contact(client)
    _make_deal(client, c["id"])  # lead
    _make_deal(client, c["id"])  # lead
    d = _make_deal(client, c["id"])
    client.patch(f"/deals/{d['id']}/stage", json={"stage": "qualified"})

    r = client.get("/stats")
    by_stage = r.json()["deals_by_stage"]
    assert by_stage.get("lead") == 2
    assert by_stage.get("qualified") == 1


def test_pipeline_value_excludes_terminal(client):
    c = _make_contact(client)
    _make_deal(client, c["id"], value=500)  # open (lead)
    d2 = _make_deal(client, c["id"], value=1000)
    # close d2 as won
    for s in ["qualified", "proposal", "negotiation", "won"]:
        client.patch(f"/deals/{d2['id']}/stage", json={"stage": s})

    r = client.get("/stats")
    # only the open lead deal (500) should count; won deal excluded
    assert r.json()["pipeline_value"] == 500.0


def test_weighted_forecast_excludes_won_lost(client):
    c = _make_contact(client)
    # lead deal with value=1000, probability=0.10 → contributes 100
    _make_deal(client, c["id"], value=1000)
    d2 = _make_deal(client, c["id"], value=9999)
    # close as won — should be excluded
    for s in ["qualified", "proposal", "negotiation", "won"]:
        client.patch(f"/deals/{d2['id']}/stage", json={"stage": s})

    r = client.get("/stats")
    wf = r.json()["weighted_forecast"]
    # won deal excluded; only lead deal contributes 1000 * 0.10 = 100
    assert abs(wf - 100.0) < 0.01


def test_activities_last_30_days_uses_injected_clock(client):
    c = _make_contact(client)
    _make_activity(client, c["id"])

    # Fix clock to 40 days in the future — the activity's created_at is now > 30 days ago
    future = _now_utc() + timedelta(days=40)

    class FutureClock:
        def now(self):
            return future

    app.dependency_overrides[get_clock] = lambda: FutureClock()
    try:
        r = client.get("/stats")
        assert r.json()["activities_last_30_days"] == 0
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_outbox_queued_count(client):
    _queue_outbox(client)
    _queue_outbox(client)
    r = client.get("/stats")
    assert r.json()["outbox_queued"] == 2


def test_stats_empty_db(client):
    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_contacts"] == 0
    assert data["total_deals"] == 0
    assert data["total_activities"] == 0
    assert data["pipeline_value"] == 0
    assert data["weighted_forecast"] == 0
    assert data["activities_last_30_days"] == 0
    assert data["outbox_queued"] == 0
