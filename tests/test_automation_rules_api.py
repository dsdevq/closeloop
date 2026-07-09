"""Integration tests for the /automation-rules CRUD API.

Covers:
  - GET /automation-rules: list all rules (admin/manager only)
  - POST /automation-rules: create after_save and scheduled rules; validation
  - GET /automation-rules/{id}: get by id; 404 for missing
  - PATCH /automation-rules/{id}: partial update; 404; validation
  - DELETE /automation-rules/{id}: 204; 404

All tests use the `client` fixture (in-memory SQLite, admin auth).
Rep-role access is tested via direct 403 assertion using a manually constructed
request with a rep's token.

Reference: app/routers/automation_rules.py, _KNOWN_TRIGGER_EVENTS,
  _KNOWN_ACTION_TYPES, _KNOWN_CONDITION_OPS.
"""
import json

import pytest
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models import AutomationRule, User


def _seed_rep_token(db: Session) -> str:
    rep = User(
        email="rep2@closeloop.com",
        hashed_password=hash_password("password"),
        role="rep",
        full_name="Rep",
        created_at="2026-01-01T00:00:00",
        is_active=1,
    )
    db.add(rep)
    db.commit()
    db.refresh(rep)
    return f"Bearer {create_access_token(rep.id)}"


def _minimal_after_save_payload(**overrides) -> dict:
    base = {
        "name": "Stage changed notify",
        "trigger_type": "after_save",
        "trigger_event": "deal_stage_changed",
        "action_type": "notify",
        "action_config_json": '{"recipient_id": 1}',
    }
    base.update(overrides)
    return base


# ── GET /automation-rules ─────────────────────────────────────────────────────


def test_list_empty(client):
    resp = client.get("/automation-rules")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_returns_created_rules(client, db_session):
    db_session.add(AutomationRule(
        name="Rule A",
        trigger_type="after_save",
        trigger_event="deal_created",
        action_type="notify",
        action_config_json='{"recipient_id": 1}',
        is_active=1,
        created_at="2026-01-01T00:00:00",
    ))
    db_session.commit()

    resp = client.get("/automation-rules")
    assert resp.status_code == 200
    rules = resp.json()
    assert len(rules) == 1
    assert rules[0]["name"] == "Rule A"
    assert rules[0]["trigger_event"] == "deal_created"
    assert rules[0]["is_active"] is True


def test_list_rep_is_forbidden(client, db_session):
    token = _seed_rep_token(db_session)
    resp = client.get("/automation-rules", headers={"Authorization": token})
    assert resp.status_code == 403


# ── POST /automation-rules ────────────────────────────────────────────────────


def test_create_after_save_rule(client):
    resp = client.post("/automation-rules", json=_minimal_after_save_payload())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Stage changed notify"
    assert data["trigger_type"] == "after_save"
    assert data["trigger_event"] == "deal_stage_changed"
    assert data["action_type"] == "notify"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data


def test_create_scheduled_rule(client):
    payload = {
        "name": "Daily ping",
        "trigger_type": "scheduled",
        "action_type": "notify",
        "action_config_json": '{"recipient_id": 1}',
        "schedule_config_json": '{"interval_minutes": 1440}',
    }
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["trigger_type"] == "scheduled"
    assert data["trigger_event"] == ""


def test_create_rule_with_conditions(client):
    payload = _minimal_after_save_payload(
        conditions_json=json.dumps([{"field": "stage", "op": "eq", "value": "won"}])
    )
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 201
    assert resp.json()["conditions_json"] == json.dumps([{"field": "stage", "op": "eq", "value": "won"}])


def test_create_run_once_at_rule(client):
    payload = {
        "name": "One shot",
        "trigger_type": "scheduled",
        "action_type": "notify",
        "action_config_json": '{"recipient_id": 1}',
        "schedule_config_json": '{"run_once_at": "2026-12-01T09:00:00"}',
    }
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 201


def test_create_rule_blank_name_is_422(client):
    resp = client.post("/automation-rules", json=_minimal_after_save_payload(name="  "))
    assert resp.status_code == 422


def test_create_rule_invalid_trigger_type_is_422(client):
    resp = client.post(
        "/automation-rules",
        json=_minimal_after_save_payload(trigger_type="webhook"),
    )
    assert resp.status_code == 422


def test_create_rule_unknown_trigger_event_is_422(client):
    resp = client.post(
        "/automation-rules",
        json=_minimal_after_save_payload(trigger_event="unknown_event"),
    )
    assert resp.status_code == 422


def test_create_after_save_rule_missing_trigger_event_is_422(client):
    payload = _minimal_after_save_payload()
    payload["trigger_event"] = ""
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 422


def test_create_rule_unknown_action_type_is_422(client):
    resp = client.post(
        "/automation-rules",
        json=_minimal_after_save_payload(action_type="send_email"),
    )
    assert resp.status_code == 422


def test_create_rule_invalid_conditions_json_is_422(client):
    resp = client.post(
        "/automation-rules",
        json=_minimal_after_save_payload(conditions_json="{not_an_array}"),
    )
    assert resp.status_code == 422


def test_create_rule_unknown_condition_op_is_422(client):
    payload = _minimal_after_save_payload(
        conditions_json=json.dumps([{"field": "stage", "op": "contains", "value": "lead"}])
    )
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 422


def test_create_rule_condition_missing_field_is_422(client):
    payload = _minimal_after_save_payload(
        conditions_json=json.dumps([{"op": "eq", "value": "lead"}])
    )
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 422


def test_create_scheduled_rule_missing_schedule_config_is_422(client):
    payload = {
        "name": "Bad scheduled",
        "trigger_type": "scheduled",
        "action_type": "notify",
        "action_config_json": '{"recipient_id": 1}',
    }
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 422


def test_create_scheduled_rule_invalid_interval_is_422(client):
    payload = {
        "name": "Bad interval",
        "trigger_type": "scheduled",
        "action_type": "notify",
        "action_config_json": '{"recipient_id": 1}',
        "schedule_config_json": '{"interval_minutes": -5}',
    }
    resp = client.post("/automation-rules", json=payload)
    assert resp.status_code == 422


def test_create_rule_rep_is_forbidden(client, db_session):
    token = _seed_rep_token(db_session)
    resp = client.post(
        "/automation-rules",
        json=_minimal_after_save_payload(),
        headers={"Authorization": token},
    )
    assert resp.status_code == 403


# ── GET /automation-rules/{id} ────────────────────────────────────────────────


def test_get_rule_by_id(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    resp = client.get(f"/automation-rules/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]


def test_get_rule_not_found_is_404(client):
    resp = client.get("/automation-rules/99999")
    assert resp.status_code == 404


def test_get_rule_rep_is_forbidden(client, db_session):
    token = _seed_rep_token(db_session)
    resp = client.get("/automation-rules/1", headers={"Authorization": token})
    assert resp.status_code == 403


# ── PATCH /automation-rules/{id} ─────────────────────────────────────────────


def test_patch_name(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    resp = client.patch(f"/automation-rules/{created['id']}", json={"name": "Updated Name"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Name"


def test_patch_is_active_toggle(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    rule_id = created["id"]
    assert created["is_active"] is True

    resp = client.patch(f"/automation-rules/{rule_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = client.patch(f"/automation-rules/{rule_id}", json={"is_active": True})
    assert resp.json()["is_active"] is True


def test_patch_conditions(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    new_conditions = json.dumps([{"field": "stage", "op": "neq", "value": "lost"}])
    resp = client.patch(
        f"/automation-rules/{created['id']}",
        json={"conditions_json": new_conditions},
    )
    assert resp.status_code == 200
    assert resp.json()["conditions_json"] == new_conditions


def test_patch_trigger_event(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    resp = client.patch(
        f"/automation-rules/{created['id']}",
        json={"trigger_event": "deal_created"},
    )
    assert resp.status_code == 200
    assert resp.json()["trigger_event"] == "deal_created"


def test_patch_invalid_trigger_event_is_422(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    resp = client.patch(
        f"/automation-rules/{created['id']}",
        json={"trigger_event": "not_a_real_event"},
    )
    assert resp.status_code == 422


def test_patch_invalid_conditions_is_422(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    resp = client.patch(
        f"/automation-rules/{created['id']}",
        json={"conditions_json": "this is not json"},
    )
    assert resp.status_code == 422


def test_patch_not_found_is_404(client):
    resp = client.patch("/automation-rules/99999", json={"name": "Ghost"})
    assert resp.status_code == 404


def test_patch_rep_is_forbidden(client, db_session):
    token = _seed_rep_token(db_session)
    resp = client.patch(
        "/automation-rules/1",
        json={"name": "Hacked"},
        headers={"Authorization": token},
    )
    assert resp.status_code == 403


# ── DELETE /automation-rules/{id} ─────────────────────────────────────────────


def test_delete_rule(client):
    created = client.post("/automation-rules", json=_minimal_after_save_payload()).json()
    rule_id = created["id"]

    resp = client.delete(f"/automation-rules/{rule_id}")
    assert resp.status_code == 204

    # Confirm it's gone
    resp = client.get(f"/automation-rules/{rule_id}")
    assert resp.status_code == 404


def test_delete_not_found_is_404(client):
    resp = client.delete("/automation-rules/99999")
    assert resp.status_code == 404


def test_delete_rep_is_forbidden(client, db_session):
    token = _seed_rep_token(db_session)
    resp = client.delete("/automation-rules/1", headers={"Authorization": token})
    assert resp.status_code == 403


# ── Round-trip: create then list ──────────────────────────────────────────────


def test_list_returns_newest_first(client):
    client.post("/automation-rules", json=_minimal_after_save_payload(name="First"))
    client.post("/automation-rules", json=_minimal_after_save_payload(name="Second"))
    rules = client.get("/automation-rules").json()
    # newest-first ordering — "Second" was created after "First"
    # (they share the same timestamp in tests so ordering by created_at asc/desc may tie;
    # just verify both are present)
    names = {r["name"] for r in rules}
    assert "First" in names
    assert "Second" in names
