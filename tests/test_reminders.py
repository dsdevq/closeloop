from datetime import datetime, timezone

import pytest

from app.core.clock import get_clock
from app.main import app


class _FixedClock:
    def __init__(self, dt: datetime):
        self._dt = dt

    def now(self) -> datetime:
        return self._dt


def _clock_override(dt: datetime):
    """Return a get_clock dependency override that returns a fixed datetime."""
    clk = _FixedClock(dt)

    def _dep():
        return clk

    return _dep


# A fixed "now" well after both reminder times used in tests
_NOW = datetime(2024, 2, 1, 12, 0, 0, tzinfo=timezone.utc)
_REMIND_PAST = "2024-01-15T09:00:00+00:00"   # before _NOW
_REMIND_FUTURE = "2025-01-01T00:00:00+00:00"  # after _NOW


@pytest.fixture
def contact(client):
    res = client.post("/contacts", json={"name": "Reminder User"})
    assert res.status_code == 201
    return res.json()


@pytest.fixture
def activity(client, contact):
    res = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "Follow up call",
    })
    assert res.status_code == 201
    return res.json()


def test_create_reminder_returns_201(client, activity):
    res = client.post("/reminders", json={
        "activity_id": activity["id"],
        "remind_at": _REMIND_PAST,
    })
    assert res.status_code == 201
    data = res.json()
    assert data["activity_id"] == activity["id"]
    assert data["remind_at"] == _REMIND_PAST
    assert data["dismissed_at"] is None
    assert "id" in data
    assert "created_at" in data


def test_create_reminder_404_for_missing_activity(client):
    res = client.post("/reminders", json={"activity_id": 9999, "remind_at": _REMIND_PAST})
    assert res.status_code == 404


def test_today_queue_returns_undismissed_due_reminders(client, activity):
    client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_PAST})

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        res = client.get("/reminders/today")
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 1
        assert items[0]["activity_title"] == "Follow up call"
        assert items[0]["activity_type"] == "call"
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_today_queue_excludes_future_reminders(client, activity):
    client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_FUTURE})

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        res = client.get("/reminders/today")
        assert res.status_code == 200
        assert res.json() == []
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_past_due_reminder_appears_until_dismissed(client, activity):
    # remind_at is very old — should still appear in today queue
    r = client.post("/reminders", json={
        "activity_id": activity["id"],
        "remind_at": "2024-01-01T00:00:00+00:00",
    })
    rid = r.json()["id"]

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        res = client.get("/reminders/today")
        assert any(item["id"] == rid for item in res.json())
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_dismiss_sets_dismissed_at(client, activity):
    r = client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_PAST})
    rid = r.json()["id"]

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        res = client.patch(f"/reminders/{rid}/dismiss")
        assert res.status_code == 200
        assert res.json()["dismissed_at"] is not None
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_dismiss_removes_reminder_from_today_queue(client, activity):
    r = client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_PAST})
    rid = r.json()["id"]

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        client.patch(f"/reminders/{rid}/dismiss")
        res = client.get("/reminders/today")
        assert not any(item["id"] == rid for item in res.json())
    finally:
        app.dependency_overrides.pop(get_clock, None)


def test_dismiss_404_for_missing(client):
    res = client.patch("/reminders/9999/dismiss")
    assert res.status_code == 404


def test_delete_reminder_returns_204(client, activity):
    r = client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_PAST})
    rid = r.json()["id"]

    res = client.delete(f"/reminders/{rid}")
    assert res.status_code == 204


def test_today_queue_embeds_contact_and_deal_info(client, contact):
    deal_res = client.post("/deals", json={"title": "Big Deal", "contact_id": contact["id"], "value": 5000.0})
    deal = deal_res.json()
    act_res = client.post("/activities", json={
        "deal_id": deal["id"],
        "contact_id": contact["id"],
        "type": "meeting",
        "title": "Intro meeting",
    })
    activity = act_res.json()
    client.post("/reminders", json={"activity_id": activity["id"], "remind_at": _REMIND_PAST})

    app.dependency_overrides[get_clock] = _clock_override(_NOW)
    try:
        res = client.get("/reminders/today")
        assert res.status_code == 200
        item = next(i for i in res.json() if i["activity_title"] == "Intro meeting")
        assert item["deal_title"] == "Big Deal"
        assert item["contact_name"] == "Reminder User"
    finally:
        app.dependency_overrides.pop(get_clock, None)
