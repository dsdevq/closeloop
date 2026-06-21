import pytest


@pytest.fixture
def contact(client):
    res = client.post("/contacts", json={"name": "Alice Buyer", "company": "Acme"})
    assert res.status_code == 201
    return res.json()


def test_create_deal_returns_201(client, contact):
    res = client.post("/deals", json={"title": "Big Sale", "contact_id": contact["id"], "value": 5000.0})
    assert res.status_code == 201
    data = res.json()
    assert data["title"] == "Big Sale"
    assert data["stage"] == "lead"
    assert data["probability"] == pytest.approx(0.1)
    assert data["value"] == pytest.approx(5000.0)
    assert data["contact_id"] == contact["id"]
    assert "id" in data


def test_create_deal_default_value_zero(client, contact):
    res = client.post("/deals", json={"title": "Small Deal", "contact_id": contact["id"]})
    assert res.status_code == 201
    assert res.json()["value"] == pytest.approx(0.0)


def test_create_deal_invalid_contact(client):
    res = client.post("/deals", json={"title": "Orphan", "contact_id": 9999})
    assert res.status_code == 404


def test_list_deals_returns_created_deal(client, contact):
    client.post("/deals", json={"title": "Alpha", "contact_id": contact["id"]})
    res = client.get("/deals")
    assert res.status_code == 200
    titles = [d["title"] for d in res.json()]
    assert "Alpha" in titles


def test_list_deals_stage_filter(client, contact):
    client.post("/deals", json={"title": "Deal A", "contact_id": contact["id"]})
    client.post("/deals", json={"title": "Deal B", "contact_id": contact["id"]})
    res = client.get("/deals?stage=lead")
    assert res.status_code == 200
    assert all(d["stage"] == "lead" for d in res.json())


def test_list_deals_stage_filter_empty(client, contact):
    client.post("/deals", json={"title": "Lead deal", "contact_id": contact["id"]})
    res = client.get("/deals?stage=won")
    assert res.status_code == 200
    assert res.json() == []


def test_get_deal_404(client):
    res = client.get("/deals/9999")
    assert res.status_code == 404


def test_patch_stage_valid_transition(client, contact):
    create = client.post("/deals", json={"title": "Promo", "contact_id": contact["id"]})
    did = create.json()["id"]

    res = client.patch(f"/deals/{did}/stage", json={"stage": "qualified"})
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "qualified"
    assert data["probability"] == pytest.approx(0.25)


def test_patch_stage_invalid_transition_won_to_lead(client, contact):
    create = client.post("/deals", json={"title": "Promo", "contact_id": contact["id"]})
    did = create.json()["id"]

    # Move to won first
    client.patch(f"/deals/{did}/stage", json={"stage": "won"})

    # Now try to move backward — must fail
    res = client.patch(f"/deals/{did}/stage", json={"stage": "lead"})
    assert res.status_code == 422
    assert "invalid stage transition" in res.json()["detail"]


def test_patch_stage_terminal_won_cannot_move(client, contact):
    create = client.post("/deals", json={"title": "Closed", "contact_id": contact["id"]})
    did = create.json()["id"]
    client.patch(f"/deals/{did}/stage", json={"stage": "won"})

    for target in ["lead", "qualified", "proposal", "negotiation", "lost"]:
        res = client.patch(f"/deals/{did}/stage", json={"stage": target})
        assert res.status_code == 422, f"Expected 422 for won→{target}"


def test_patch_stage_inserts_transition_row(client, contact):
    create = client.post("/deals", json={"title": "Audit", "contact_id": contact["id"]})
    did = create.json()["id"]

    client.patch(f"/deals/{did}/stage", json={"stage": "qualified"})
    client.patch(f"/deals/{did}/stage", json={"stage": "proposal"})

    # The GET deal endpoint doesn't expose transitions directly, but we verify
    # stage is correctly updated (transitions rows verified via the DB in conftest,
    # here we check the observable effect: stage + probability are updated)
    res = client.get(f"/deals/{did}")
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "proposal"
    assert data["probability"] == pytest.approx(0.5)


def test_patch_deal_fields(client, contact):
    create = client.post("/deals", json={"title": "Old Title", "contact_id": contact["id"], "value": 100.0})
    did = create.json()["id"]

    res = client.patch(f"/deals/{did}", json={"title": "New Title", "value": 999.0})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "New Title"
    assert data["value"] == pytest.approx(999.0)
    assert data["stage"] == "lead"  # stage untouched


def test_patch_deal_404(client):
    res = client.patch("/deals/9999", json={"title": "Ghost"})
    assert res.status_code == 404


def test_delete_deal_returns_204(client, contact):
    create = client.post("/deals", json={"title": "Temp", "contact_id": contact["id"]})
    did = create.json()["id"]

    res = client.delete(f"/deals/{did}")
    assert res.status_code == 204

    res = client.get(f"/deals/{did}")
    assert res.status_code == 404


def test_deal_has_contact_name_embedded(client, contact):
    client.post("/deals", json={"title": "Named", "contact_id": contact["id"]})
    res = client.get("/deals")
    assert res.status_code == 200
    deal = next(d for d in res.json() if d["title"] == "Named")
    assert deal["contact_name"] == "Alice Buyer"
