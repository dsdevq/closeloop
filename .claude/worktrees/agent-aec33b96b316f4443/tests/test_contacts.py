def test_create_contact_returns_201(client):
    res = client.post("/contacts", json={"name": "Alice", "email": "alice@example.com", "company": "Acme"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Alice"
    assert data["email"] == "alice@example.com"
    assert data["company"] == "Acme"
    assert data["lead_score"] == 0.0
    assert "id" in data
    assert "created_at" in data


def test_list_contacts_empty_initially(client):
    res = client.get("/contacts")
    assert res.status_code == 200
    assert res.json() == []


def test_list_contacts_returns_created_contact(client):
    client.post("/contacts", json={"name": "Bob"})
    res = client.get("/contacts")
    assert res.status_code == 200
    names = [c["name"] for c in res.json()]
    assert "Bob" in names


def test_get_contact_404_for_missing(client):
    res = client.get("/contacts/9999")
    assert res.status_code == 404


def test_patch_contact_updates_fields(client):
    create = client.post("/contacts", json={"name": "Carol", "company": "OldCo"})
    cid = create.json()["id"]

    res = client.patch(f"/contacts/{cid}", json={"company": "NewCo", "phone": "+15550001234"})
    assert res.status_code == 200
    data = res.json()
    assert data["company"] == "NewCo"
    assert data["phone"] == "+15550001234"
    assert data["name"] == "Carol"  # unchanged


def test_patch_contact_404_for_missing(client):
    res = client.patch("/contacts/9999", json={"name": "Ghost"})
    assert res.status_code == 404


def test_delete_contact_returns_204(client):
    create = client.post("/contacts", json={"name": "Dave"})
    cid = create.json()["id"]

    res = client.delete(f"/contacts/{cid}")
    assert res.status_code == 204

    res = client.get(f"/contacts/{cid}")
    assert res.status_code == 404


def test_create_contact_minimal_fields(client):
    res = client.post("/contacts", json={"name": "Eve"})
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Eve"
    assert data["email"] is None
    assert data["phone"] is None
    assert data["company"] is None
