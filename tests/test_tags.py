"""API tests for tags & segmentation."""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_tag(client, name="vip"):
    r = client.post("/tags", json={"name": name})
    assert r.status_code == 201
    return r.json()


def _make_contact(client, name="Alice", email="alice@example.com"):
    r = client.post("/contacts", json={"name": name, "email": email})
    assert r.status_code == 201
    return r.json()


def _make_deal(client, contact_id, title="Deal"):
    r = client.post("/deals", json={"title": title, "contact_id": contact_id, "value": 500.0})
    assert r.status_code == 201
    return r.json()


# ── Tag CRUD ──────────────────────────────────────────────────────────────────

def test_create_tag_returns_201(client):
    r = client.post("/tags", json={"name": "hot"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "hot"
    assert "id" in data
    assert "created_at" in data


def test_create_duplicate_tag_returns_409(client):
    _make_tag(client, "dup")
    r = client.post("/tags", json={"name": "dup"})
    assert r.status_code == 409


def test_list_tags_empty(client):
    r = client.get("/tags")
    assert r.status_code == 200
    assert r.json() == []


def test_list_tags_returns_all(client):
    _make_tag(client, "tag1")
    _make_tag(client, "tag2")
    r = client.get("/tags")
    names = [t["name"] for t in r.json()]
    assert "tag1" in names
    assert "tag2" in names


def test_get_tag_returns_correct_data(client):
    tag = _make_tag(client, "enterprise")
    r = client.get(f"/tags/{tag['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "enterprise"


def test_get_tag_404_for_missing(client):
    r = client.get("/tags/9999")
    assert r.status_code == 404


def test_delete_tag_returns_204(client):
    tag = _make_tag(client)
    r = client.delete(f"/tags/{tag['id']}")
    assert r.status_code == 204
    assert client.get(f"/tags/{tag['id']}").status_code == 404


def test_delete_tag_404_for_missing(client):
    r = client.delete("/tags/9999")
    assert r.status_code == 404


# ── Contact tags ──────────────────────────────────────────────────────────────

def test_add_tag_to_contact(client):
    tag = _make_tag(client, "priority")
    contact = _make_contact(client)
    r = client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag["id"]})
    assert r.status_code == 201
    assert r.json()["name"] == "priority"


def test_list_contact_tags(client):
    tag1 = _make_tag(client, "hot")
    tag2 = _make_tag(client, "enterprise")
    contact = _make_contact(client)
    client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag1["id"]})
    client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag2["id"]})

    r = client.get(f"/tags/contacts/{contact['id']}")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "hot" in names
    assert "enterprise" in names


def test_list_contact_tags_empty(client):
    contact = _make_contact(client)
    r = client.get(f"/tags/contacts/{contact['id']}")
    assert r.status_code == 200
    assert r.json() == []


def test_add_duplicate_tag_to_contact_returns_409(client):
    tag = _make_tag(client)
    contact = _make_contact(client)
    client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag["id"]})
    r = client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag["id"]})
    assert r.status_code == 409


def test_add_tag_to_missing_contact_returns_404(client):
    tag = _make_tag(client)
    r = client.post("/tags/contacts/9999", json={"tag_id": tag["id"]})
    assert r.status_code == 404


def test_add_missing_tag_to_contact_returns_404(client):
    contact = _make_contact(client)
    r = client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": 9999})
    assert r.status_code == 404


def test_remove_tag_from_contact(client):
    tag = _make_tag(client)
    contact = _make_contact(client)
    client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag["id"]})

    r = client.delete(f"/tags/contacts/{contact['id']}/{tag['id']}")
    assert r.status_code == 204

    tags = client.get(f"/tags/contacts/{contact['id']}").json()
    assert tags == []


def test_remove_unassigned_tag_from_contact_returns_404(client):
    tag = _make_tag(client)
    contact = _make_contact(client)
    r = client.delete(f"/tags/contacts/{contact['id']}/{tag['id']}")
    assert r.status_code == 404


def test_delete_tag_cascades_to_contact_assignment(client):
    tag = _make_tag(client, "cascade_tag")
    contact = _make_contact(client)
    client.post(f"/tags/contacts/{contact['id']}", json={"tag_id": tag["id"]})
    client.delete(f"/tags/{tag['id']}")
    # After deleting the tag, the contact should have no tags
    tags = client.get(f"/tags/contacts/{contact['id']}").json()
    assert tags == []


# ── Deal tags ──────────────────────────────────────────────────────────────────

def test_add_tag_to_deal(client):
    tag = _make_tag(client, "strategic")
    contact = _make_contact(client)
    deal = _make_deal(client, contact["id"])

    r = client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag["id"]})
    assert r.status_code == 201
    assert r.json()["name"] == "strategic"


def test_list_deal_tags(client):
    tag1 = _make_tag(client, "hot")
    tag2 = _make_tag(client, "renewal")
    contact = _make_contact(client)
    deal = _make_deal(client, contact["id"])
    client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag1["id"]})
    client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag2["id"]})

    r = client.get(f"/tags/deals/{deal['id']}")
    assert r.status_code == 200
    names = [t["name"] for t in r.json()]
    assert "hot" in names
    assert "renewal" in names


def test_remove_tag_from_deal(client):
    tag = _make_tag(client)
    contact = _make_contact(client)
    deal = _make_deal(client, contact["id"])
    client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag["id"]})

    r = client.delete(f"/tags/deals/{deal['id']}/{tag['id']}")
    assert r.status_code == 204
    assert client.get(f"/tags/deals/{deal['id']}").json() == []


def test_add_duplicate_tag_to_deal_returns_409(client):
    tag = _make_tag(client)
    contact = _make_contact(client)
    deal = _make_deal(client, contact["id"])
    client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag["id"]})
    r = client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag["id"]})
    assert r.status_code == 409


def test_add_tag_to_missing_deal_returns_404(client):
    tag = _make_tag(client)
    r = client.post("/tags/deals/9999", json={"tag_id": tag["id"]})
    assert r.status_code == 404


def test_delete_deal_cascades_to_tag_assignments(client):
    tag = _make_tag(client, "important")
    contact = _make_contact(client)
    deal = _make_deal(client, contact["id"])
    client.post(f"/tags/deals/{deal['id']}", json={"tag_id": tag["id"]})
    # Delete deal — deal_tags row should cascade-delete
    client.delete(f"/deals/{deal['id']}")
    # Tag should still exist
    r = client.get(f"/tags/{tag['id']}")
    assert r.status_code == 200
    assert r.json()["name"] == "important"


# ── Filter AST `in` operator via saved views ──────────────────────────────────

def test_saved_view_with_in_op_filters_by_stage(client):
    contact = _make_contact(client)
    _make_deal(client, contact["id"], title="Lead Deal")
    d2 = _make_deal(client, contact["id"], title="Qualified Deal")
    client.patch(f"/deals/{d2['id']}/stage", json={"stage": "qualified"})
    d3 = _make_deal(client, contact["id"], title="Won Deal")
    for s in ["qualified", "proposal", "negotiation", "won"]:
        client.patch(f"/deals/{d3['id']}/stage", json={"stage": s})

    view_r = client.post("/saved-views", json={
        "name": "open_early_stages",
        "entity_type": "deals",
        "filter_expr": {"op": "in", "field": "stage", "value": ["lead", "qualified"]},
    })
    assert view_r.status_code == 201
    vid = view_r.json()["id"]

    apply_r = client.post(f"/saved-views/{vid}/apply")
    assert apply_r.status_code == 200
    titles = [d["title"] for d in apply_r.json()]
    assert "Lead Deal" in titles
    assert "Qualified Deal" in titles
    assert "Won Deal" not in titles
