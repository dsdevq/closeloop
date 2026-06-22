"""API tests for /outbox — queue-only, no real sends."""


def _queue(client, **overrides):
    payload = {
        "to_address": "test@example.com",
        "subject": "Hello",
        "body": "Body text",
    }
    payload.update(overrides)
    return client.post("/outbox", json=payload)


# ── POST /outbox ─────────────────────────────────────────────────────────────

def test_post_outbox_queues_with_status_queued(client):
    r = _queue(client)
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "queued"
    assert data["to_address"] == "test@example.com"
    assert data["subject"] == "Hello"
    assert data["body"] == "Body text"
    assert data["sent_at"] is None


def test_post_outbox_returns_id(client):
    r = _queue(client)
    assert r.status_code == 201
    assert r.json()["id"] is not None


def test_post_outbox_with_deal_and_contact_ids(client):
    # Create a contact and deal to reference
    cr = client.post("/contacts", json={"name": "A", "email": "a@x.com"})
    cid = cr.json()["id"]
    dr = client.post("/deals", json={"title": "D", "contact_id": cid, "value": 0})
    did = dr.json()["id"]
    r = _queue(client, deal_id=did, contact_id=cid)
    assert r.status_code == 201
    data = r.json()
    assert data["deal_id"] == did
    assert data["contact_id"] == cid


# ── GET /outbox ──────────────────────────────────────────────────────────────

def test_get_outbox_lists_messages(client):
    _queue(client, subject="Msg1")
    _queue(client, subject="Msg2")
    r = client.get("/outbox")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_outbox_status_filter_queued(client):
    _queue(client, subject="Msg1")
    _queue(client, subject="Msg2")
    r = client.get("/outbox?status=queued")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) == 2
    assert all(m["status"] == "queued" for m in msgs)


def test_get_outbox_status_filter_sent_returns_empty(client):
    _queue(client, subject="Msg1")
    r = client.get("/outbox?status=sent")
    assert r.status_code == 200
    assert r.json() == []


def test_get_outbox_invalid_status_422(client):
    r = client.get("/outbox?status=unknown")
    assert r.status_code == 422


def test_get_outbox_by_id(client):
    mid = _queue(client).json()["id"]
    r = client.get(f"/outbox/{mid}")
    assert r.status_code == 200
    assert r.json()["id"] == mid


def test_get_outbox_by_id_404(client):
    r = client.get("/outbox/9999")
    assert r.status_code == 404


# ── DELETE /outbox/{id} ──────────────────────────────────────────────────────

def test_delete_outbox_returns_204(client):
    mid = _queue(client).json()["id"]
    r = client.delete(f"/outbox/{mid}")
    assert r.status_code == 204
    assert client.get(f"/outbox/{mid}").status_code == 404


# ── No real network call ─────────────────────────────────────────────────────

def test_outbox_makes_no_network_call(client, monkeypatch):
    """Queueing a message must not open any socket."""
    import socket

    def _no_connect(*args, **kwargs):
        raise AssertionError("outbox must not make real network calls")

    monkeypatch.setattr(socket, "create_connection", _no_connect)
    r = _queue(client)
    assert r.status_code == 201
    assert r.json()["status"] == "queued"
