import pytest


@pytest.fixture
def contact(client):
    res = client.post("/contacts", json={"name": "Activity User", "email": "au@example.com"})
    assert res.status_code == 201
    return res.json()


@pytest.fixture
def deal(client, contact):
    res = client.post("/deals", json={"title": "Activity Deal", "contact_id": contact["id"], "value": 1000.0})
    assert res.status_code == 201
    return res.json()


def test_create_activity_returns_201(client, contact, deal):
    res = client.post("/activities", json={
        "deal_id": deal["id"],
        "contact_id": contact["id"],
        "type": "call",
        "title": "Initial call",
        "body": "Discussed pricing.",
    })
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Initial call"
    assert data["type"] == "call"
    assert data["body"] == "Discussed pricing."
    assert data["deal_id"] == deal["id"]
    assert data["contact_id"] == contact["id"]
    assert data["completed_at"] is None
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_create_activity_without_deal_or_contact(client):
    res = client.post("/activities", json={"type": "note", "title": "Standalone note"})
    assert res.status_code == 201
    data = res.json()
    assert data["deal_id"] is None
    assert data["contact_id"] is None


def test_create_activity_invalid_type_returns_422(client):
    res = client.post("/activities", json={"type": "sms", "title": "Bad type"})
    assert res.status_code == 422


def test_list_activities_returns_all(client, contact):
    client.post("/activities", json={"contact_id": contact["id"], "type": "call", "title": "A"})
    client.post("/activities", json={"contact_id": contact["id"], "type": "email", "title": "B"})
    res = client.get("/activities")
    assert res.status_code == 200
    titles = [a["title"] for a in res.json()]
    assert "A" in titles
    assert "B" in titles


def test_list_with_deal_id_filter(client, contact, deal):
    client.post("/activities", json={"deal_id": deal["id"], "type": "call", "title": "Deal activity"})
    client.post("/activities", json={"contact_id": contact["id"], "type": "email", "title": "Contact-only activity"})

    res = client.get(f"/activities?deal_id={deal['id']}")
    assert res.status_code == 200
    items = res.json()
    titles = [a["title"] for a in items]
    assert "Deal activity" in titles
    assert "Contact-only activity" not in titles


def test_list_with_contact_id_filter(client, contact):
    client.post("/activities", json={"contact_id": contact["id"], "type": "note", "title": "For contact"})
    client.post("/activities", json={"type": "note", "title": "Orphan"})

    res = client.get(f"/activities?contact_id={contact['id']}")
    assert res.status_code == 200
    titles = [a["title"] for a in res.json()]
    assert "For contact" in titles
    assert "Orphan" not in titles


def test_get_activity_returns_correct_data(client, contact):
    create = client.post("/activities", json={"contact_id": contact["id"], "type": "meeting", "title": "Kickoff"})
    aid = create.json()["id"]

    res = client.get(f"/activities/{aid}")
    assert res.status_code == 200
    assert res.json()["title"] == "Kickoff"


def test_get_activity_404_for_missing(client):
    res = client.get("/activities/9999")
    assert res.status_code == 404


def test_patch_activity_updates_fields(client, contact):
    create = client.post("/activities", json={"contact_id": contact["id"], "type": "call", "title": "Old"})
    aid = create.json()["id"]

    res = client.patch(f"/activities/{aid}", json={"title": "New", "body": "Notes here"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New"
    assert data["body"] == "Notes here"
    assert data["type"] == "call"  # unchanged


def test_complete_activity_sets_completed_at(client, contact):
    create = client.post("/activities", json={"contact_id": contact["id"], "type": "note", "title": "Todo"})
    aid = create.json()["id"]
    assert create.json()["completed_at"] is None

    res = client.post(f"/activities/{aid}/complete")
    assert res.status_code == 200
    data = res.json()
    assert data["completed_at"] is not None


def test_complete_activity_404_for_missing(client):
    res = client.post("/activities/9999/complete")
    assert res.status_code == 404


def test_delete_activity_returns_204(client, contact):
    create = client.post("/activities", json={"contact_id": contact["id"], "type": "meeting", "title": "Meet"})
    aid = create.json()["id"]

    res = client.delete(f"/activities/{aid}")
    assert res.status_code == 204

    res = client.get(f"/activities/{aid}")
    assert res.status_code == 404


def test_delete_activity_404_for_missing(client):
    res = client.delete("/activities/9999")
    assert res.status_code == 404


# ── Recurrence tests ──────────────────────────────────────────────────────────

def test_create_activity_with_recurrence_rule(client, contact):
    rule = {"freq": "weekly", "interval": 1}
    res = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "Weekly call",
        "due_at": "2024-06-01T09:00:00",
        "recurrence_rule": rule,
    })
    assert res.status_code == 201
    data = res.json()
    assert data["recurrence_rule"] == rule


def test_create_activity_with_invalid_recurrence_rule_returns_422(client, contact):
    res = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "Bad rule",
        "due_at": "2024-06-01T09:00:00",
        "recurrence_rule": {"freq": "hourly", "interval": 1},
    })
    assert res.status_code == 422


def test_expand_activity_returns_created_children(client, contact):
    rule = {"freq": "daily", "interval": 1}
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "Daily standup",
        "due_at": "2024-06-01T09:00:00",
        "recurrence_rule": rule,
    })
    assert create.status_code == 201
    aid = create.json()["id"]

    res = client.post(f"/activities/{aid}/expand", json={"count": 3})
    assert res.status_code == 201
    children = res.json()
    assert len(children) == 3
    # Due dates should advance by 1 day each
    assert children[0]["due_at"] == "2024-06-02T09:00:00"
    assert children[1]["due_at"] == "2024-06-03T09:00:00"
    assert children[2]["due_at"] == "2024-06-04T09:00:00"


def test_expand_activity_children_inherit_type_and_title(client, contact):
    rule = {"freq": "weekly", "interval": 2}
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "meeting",
        "title": "Bi-weekly sync",
        "due_at": "2024-06-01T10:00:00",
        "recurrence_rule": rule,
    })
    aid = create.json()["id"]
    res = client.post(f"/activities/{aid}/expand", json={"count": 1})
    assert res.status_code == 201
    child = res.json()[0]
    assert child["type"] == "meeting"
    assert child["title"] == "Bi-weekly sync"
    assert child["contact_id"] == contact["id"]
    assert child["recurrence_rule"] == rule


def test_expand_activity_without_due_at_returns_422(client, contact):
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "No date",
        "recurrence_rule": {"freq": "daily", "interval": 1},
    })
    aid = create.json()["id"]
    res = client.post(f"/activities/{aid}/expand", json={"count": 1})
    assert res.status_code == 422


def test_expand_activity_without_rule_returns_422(client, contact):
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "No rule",
        "due_at": "2024-06-01T09:00:00",
    })
    aid = create.json()["id"]
    res = client.post(f"/activities/{aid}/expand", json={"count": 1})
    assert res.status_code == 422


def test_expand_activity_count_zero_returns_422(client, contact):
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "call",
        "title": "Zero expand",
        "due_at": "2024-06-01T09:00:00",
        "recurrence_rule": {"freq": "daily", "interval": 1},
    })
    aid = create.json()["id"]
    res = client.post(f"/activities/{aid}/expand", json={"count": 0})
    assert res.status_code == 422


def test_expand_activity_404_for_missing(client):
    res = client.post("/activities/9999/expand", json={"count": 1})
    assert res.status_code == 404


def test_recurrence_rule_returned_in_get(client, contact):
    rule = {"freq": "monthly", "interval": 1}
    create = client.post("/activities", json={
        "contact_id": contact["id"],
        "type": "meeting",
        "title": "Monthly review",
        "due_at": "2024-06-15T09:00:00",
        "recurrence_rule": rule,
    })
    aid = create.json()["id"]
    res = client.get(f"/activities/{aid}")
    assert res.status_code == 200
    assert res.json()["recurrence_rule"] == rule
