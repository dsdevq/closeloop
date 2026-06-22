"""API tests for /outbox — queue-only, no real sends."""
from datetime import datetime, timezone


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


# ── POST /outbox/digest ───────────────────────────────────────────────────────

def _seed_reminder(client, remind_at: str) -> dict:
    """Create an activity + reminder for testing the digest."""
    cr = client.post("/contacts", json={"name": "Digest User", "email": "digest@x.com"})
    cid = cr.json()["id"]
    ar = client.post("/activities", json={
        "contact_id": cid, "type": "call", "title": "Follow up",
    })
    aid = ar.json()["id"]
    rr = client.post("/reminders", json={"activity_id": aid, "remind_at": remind_at})
    assert rr.status_code == 201
    return rr.json()


def test_digest_returns_201_with_queued_outbox_row(client):
    r = client.post("/outbox/digest")
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "queued"
    assert data["to_address"] == "digest@closeloop.local"
    assert "Digest" in data["subject"]


def test_digest_appears_in_outbox_list(client):
    client.post("/outbox/digest")
    msgs = client.get("/outbox").json()
    assert any("Digest" in m["subject"] for m in msgs)


def test_digest_with_overdue_reminders_mentions_them(client):
    # Seed a reminder in the past
    _seed_reminder(client, "2000-01-01T00:00:00")
    r = client.post("/outbox/digest")
    assert r.status_code == 201
    body = r.json()["body"]
    assert "Follow up" in body
    assert "1 reminder" in body


def test_digest_empty_reminders_body_says_none(client):
    r = client.post("/outbox/digest")
    assert r.status_code == 201
    body = r.json()["body"]
    assert "No overdue" in body


def test_digest_does_not_include_dismissed_reminders(client):
    _seed_reminder(client, "2000-01-01T00:00:00")
    # Dismiss the reminder
    reminders = client.get("/reminders/today").json()
    assert len(reminders) == 1
    client.patch(f"/reminders/{reminders[0]['id']}/dismiss")

    r = client.post("/outbox/digest")
    body = r.json()["body"]
    assert "No overdue" in body


def test_digest_makes_no_network_call(client, monkeypatch):
    """Digest creation must not open any socket."""
    import socket

    def _no_connect(*args, **kwargs):
        raise AssertionError("digest must not make real network calls")

    monkeypatch.setattr(socket, "create_connection", _no_connect)
    r = client.post("/outbox/digest")
    assert r.status_code == 201
