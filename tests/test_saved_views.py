"""API tests for /saved-views."""
import pytest


_FILTER_EQ_STAGE = {"op": "eq", "field": "stage", "value": "lead"}


def _make_contact(client, name="Alice", email="alice@example.com"):
    r = client.post("/contacts", json={"name": name, "email": email})
    assert r.status_code == 201
    return r.json()


def _make_deal(client, contact_id, stage="lead", value=1000.0):
    r = client.post("/deals", json={"title": "Deal A", "contact_id": contact_id, "value": value})
    assert r.status_code == 201
    return r.json()


# ── Create ──────────────────────────────────────────────────────────────────

def test_create_saved_view_returns_201(client):
    r = client.post("/saved-views", json={
        "name": "All Leads",
        "entity_type": "contacts",
        "filter_expr": _FILTER_EQ_STAGE,
    })
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "All Leads"
    assert data["entity_type"] == "contacts"
    assert data["id"] is not None
    assert data["sort_dir"] == "asc"


def test_create_saved_view_invalid_entity_type(client):
    r = client.post("/saved-views", json={
        "name": "Bad",
        "entity_type": "activities",
        "filter_expr": _FILTER_EQ_STAGE,
    })
    assert r.status_code == 422


def test_create_saved_view_invalid_filter_expr(client):
    r = client.post("/saved-views", json={
        "name": "Bad",
        "entity_type": "deals",
        "filter_expr": {"op": "bogus"},
    })
    assert r.status_code == 422


# ── List ────────────────────────────────────────────────────────────────────

def test_list_saved_views(client):
    client.post("/saved-views", json={"name": "V1", "entity_type": "deals", "filter_expr": _FILTER_EQ_STAGE})
    client.post("/saved-views", json={"name": "V2", "entity_type": "contacts", "filter_expr": _FILTER_EQ_STAGE})
    r = client.get("/saved-views")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_saved_view_by_id(client):
    cr = client.post("/saved-views", json={"name": "V1", "entity_type": "deals", "filter_expr": _FILTER_EQ_STAGE})
    vid = cr.json()["id"]
    r = client.get(f"/saved-views/{vid}")
    assert r.status_code == 200
    assert r.json()["name"] == "V1"


def test_get_saved_view_404(client):
    r = client.get("/saved-views/9999")
    assert r.status_code == 404


# ── Apply ───────────────────────────────────────────────────────────────────

def test_apply_view_filters_contacts(client):
    # Create two contacts; the filter matches by company
    client.post("/contacts", json={"name": "Alice", "email": "a@x.com", "company": "Acme"})
    client.post("/contacts", json={"name": "Bob", "email": "b@x.com", "company": "Beta"})

    cr = client.post("/saved-views", json={
        "name": "Acme only",
        "entity_type": "contacts",
        "filter_expr": {"op": "eq", "field": "company", "value": "Acme"},
    })
    vid = cr.json()["id"]
    r = client.post(f"/saved-views/{vid}/apply")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert results[0]["name"] == "Alice"


def test_apply_view_with_and_filter(client):
    contact = _make_contact(client, "Alice", "a@x.com")
    contact2 = _make_contact(client, "Bob", "b@x.com")
    # Create a lead deal and a won deal
    r1 = client.post("/deals", json={"title": "Lead Deal", "contact_id": contact["id"], "value": 500})
    lead_deal_id = r1.json()["id"]
    r2 = client.post("/deals", json={"title": "Won Deal", "contact_id": contact2["id"], "value": 1000})
    won_deal_id = r2.json()["id"]
    # move r2 to won
    client.patch(f"/deals/{won_deal_id}/stage", json={"stage": "qualified"})
    client.patch(f"/deals/{won_deal_id}/stage", json={"stage": "proposal"})
    client.patch(f"/deals/{won_deal_id}/stage", json={"stage": "negotiation"})
    client.patch(f"/deals/{won_deal_id}/stage", json={"stage": "won"})

    cr = client.post("/saved-views", json={
        "name": "Open big deals",
        "entity_type": "deals",
        "filter_expr": {
            "op": "and",
            "children": [
                {"op": "neq", "field": "stage", "value": "won"},
                {"op": "neq", "field": "stage", "value": "lost"},
            ],
        },
    })
    vid = cr.json()["id"]
    r = client.post(f"/saved-views/{vid}/apply")
    assert r.status_code == 200
    results = r.json()
    stages = [d["stage"] for d in results]
    assert "won" not in stages
    assert "lost" not in stages
    assert any(d["id"] == lead_deal_id for d in results)


def test_apply_view_returns_all_when_filter_matches_all(client):
    _make_contact(client, "Alice", "a@x.com")
    _make_contact(client, "Bob", "b@x.com")

    cr = client.post("/saved-views", json={
        "name": "All contacts",
        "entity_type": "contacts",
        "filter_expr": {"op": "neq", "field": "name", "value": "__NONE__"},
    })
    vid = cr.json()["id"]
    r = client.post(f"/saved-views/{vid}/apply")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_apply_view_404(client):
    r = client.post("/saved-views/9999/apply")
    assert r.status_code == 404


# ── Delete ──────────────────────────────────────────────────────────────────

def test_delete_saved_view_returns_204(client):
    cr = client.post("/saved-views", json={"name": "Temp", "entity_type": "deals", "filter_expr": _FILTER_EQ_STAGE})
    vid = cr.json()["id"]
    r = client.delete(f"/saved-views/{vid}")
    assert r.status_code == 204
    # confirm gone
    assert client.get(f"/saved-views/{vid}").status_code == 404
