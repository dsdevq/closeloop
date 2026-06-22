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
