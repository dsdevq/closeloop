"""CRUD API for AutomationRule management.

Access: admin or manager only (same pattern as pipeline.py).
Rules are evaluated by the after-save trigger sites in routers/deals.py,
contacts.py, and activities.py, and by the scheduled poller in main.py.
This router is only for managing rule definitions — it does NOT trigger rules.

Validation contract (fail-closed, matching services/automations.py):
  - trigger_type must be "after_save" or "scheduled"
  - trigger_event must be in _KNOWN_TRIGGER_EVENTS (after_save only; empty for scheduled)
  - action_type must be in _KNOWN_ACTION_TYPES
  - conditions_json, if non-null and non-empty, must be a JSON array of
    {field, op, value} objects where op is in _KNOWN_CONDITION_OPS
  - schedule_config_json is validated via _parse_schedule_config for scheduled rules
  - action_config_json must be a JSON object (validated via _parse_notify_config for notify)

HTTP 422 for all semantic validation failures (per ADR-0002).
"""
from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.clock import Clock, get_clock
from app.database import get_db
from app.dependencies import get_current_user
from app.models import AutomationRule, User
from app.services.automations import (
    ActionConfigParseError,
    ConditionsParseError,
    ScheduleConfigParseError,
    _parse_conditions,
    _parse_notify_config,
    _parse_schedule_config,
)

router = APIRouter(prefix="/automation-rules")

_KNOWN_TRIGGER_EVENTS = frozenset({
    "deal_created",
    "deal_stage_changed",
    "deal_assigned",
    "deal_updated",
    "contact_created",
    "contact_updated",
    "activity_created",
    "activity_completed",
})
_KNOWN_ACTION_TYPES = frozenset({"notify"})
_KNOWN_CONDITION_OPS = frozenset({"eq", "neq", "in"})


def _require_admin_or_manager(user: User) -> None:
    if user.role not in ("admin", "manager"):
        raise HTTPException(status_code=403, detail="Admin or manager access required")


def _to_out(rule: AutomationRule) -> dict:
    return {
        "id": rule.id,
        "name": rule.name,
        "trigger_type": rule.trigger_type,
        "trigger_event": rule.trigger_event,
        "conditions_json": rule.conditions_json,
        "action_type": rule.action_type,
        "action_config_json": rule.action_config_json,
        "schedule_config_json": rule.schedule_config_json,
        "last_triggered_at": rule.last_triggered_at,
        "is_active": bool(rule.is_active),
        "created_at": rule.created_at,
    }


def _validate_conditions(conditions_json: str | None) -> None:
    """Raise HTTP 422 when conditions_json is syntactically or structurally invalid."""
    if not conditions_json:
        return
    try:
        conditions = _parse_conditions(conditions_json)
    except ConditionsParseError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid conditions_json: {exc}") from exc
    for cond in conditions:
        op = cond.get("op", "")
        if op not in _KNOWN_CONDITION_OPS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown condition op {op!r}; supported: {sorted(_KNOWN_CONDITION_OPS)}",
            )
        if "field" not in cond:
            raise HTTPException(status_code=422, detail="Each condition must have a 'field' key")
        if "value" not in cond:
            raise HTTPException(status_code=422, detail="Each condition must have a 'value' key")


def _validate_action_config(action_type: str, action_config_json: str | None) -> None:
    """Raise HTTP 422 when action_config_json is malformed for the given action_type."""
    if action_type == "notify":
        try:
            _parse_notify_config(action_config_json)
        except ActionConfigParseError as exc:
            raise HTTPException(
                status_code=422, detail=f"Invalid action_config_json: {exc}"
            ) from exc


def _validate_schedule_config(trigger_type: str, schedule_config_json: str | None) -> None:
    """Raise HTTP 422 when schedule_config_json is missing or invalid for scheduled rules."""
    if trigger_type == "scheduled":
        try:
            _parse_schedule_config(schedule_config_json)
        except ScheduleConfigParseError as exc:
            raise HTTPException(
                status_code=422, detail=f"Invalid schedule_config_json: {exc}"
            ) from exc


class AutomationRuleCreate(BaseModel):
    name: str
    trigger_type: str = "after_save"
    trigger_event: str = ""
    conditions_json: Optional[str] = None
    action_type: str
    action_config_json: str = "{}"
    schedule_config_json: Optional[str] = None
    is_active: bool = True


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = None
    trigger_event: Optional[str] = None
    conditions_json: Optional[str] = None
    action_config_json: Optional[str] = None
    schedule_config_json: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("")
def list_automation_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    _require_admin_or_manager(current_user)
    rules = (
        db.query(AutomationRule)
        .order_by(AutomationRule.created_at.desc())
        .all()
    )
    return [_to_out(r) for r in rules]


@router.post("", status_code=201)
def create_automation_rule(
    body: AutomationRuleCreate,
    db: Session = Depends(get_db),
    clk: Clock = Depends(get_clock),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin_or_manager(current_user)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be blank")

    if body.trigger_type not in ("after_save", "scheduled"):
        raise HTTPException(
            status_code=422,
            detail="trigger_type must be 'after_save' or 'scheduled'",
        )

    trigger_event = body.trigger_event.strip()
    if body.trigger_type == "after_save":
        if not trigger_event:
            raise HTTPException(
                status_code=422,
                detail="trigger_event is required for after_save rules",
            )
        if trigger_event not in _KNOWN_TRIGGER_EVENTS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown trigger_event {trigger_event!r}; supported: {sorted(_KNOWN_TRIGGER_EVENTS)}",
            )
    else:
        trigger_event = ""  # scheduled rules don't use trigger_event

    if body.action_type not in _KNOWN_ACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown action_type {body.action_type!r}; supported: {sorted(_KNOWN_ACTION_TYPES)}",
        )

    _validate_conditions(body.conditions_json)
    _validate_action_config(body.action_type, body.action_config_json)
    _validate_schedule_config(body.trigger_type, body.schedule_config_json)

    rule = AutomationRule(
        name=name,
        trigger_type=body.trigger_type,
        trigger_event=trigger_event,
        conditions_json=body.conditions_json,
        action_type=body.action_type,
        action_config_json=body.action_config_json,
        schedule_config_json=body.schedule_config_json,
        is_active=1 if body.is_active else 0,
        created_at=clk.now().isoformat(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return _to_out(rule)


@router.get("/{rule_id}")
def get_automation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin_or_manager(current_user)
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return _to_out(rule)


@router.patch("/{rule_id}")
def update_automation_rule(
    rule_id: int,
    body: AutomationRuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_admin_or_manager(current_user)
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")

    updates = body.model_dump(exclude_unset=True)

    if "name" in updates:
        name = updates["name"].strip()
        if not name:
            raise HTTPException(status_code=422, detail="name must not be blank")
        rule.name = name

    if "trigger_event" in updates:
        trigger_event = updates["trigger_event"].strip()
        if rule.trigger_type == "after_save":
            if not trigger_event:
                raise HTTPException(
                    status_code=422,
                    detail="trigger_event is required for after_save rules",
                )
            if trigger_event not in _KNOWN_TRIGGER_EVENTS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Unknown trigger_event {trigger_event!r}; supported: {sorted(_KNOWN_TRIGGER_EVENTS)}",
                )
        rule.trigger_event = trigger_event

    if "conditions_json" in updates:
        _validate_conditions(updates["conditions_json"])
        rule.conditions_json = updates["conditions_json"]

    if "action_config_json" in updates:
        _validate_action_config(rule.action_type, updates["action_config_json"])
        rule.action_config_json = updates["action_config_json"]

    if "schedule_config_json" in updates:
        _validate_schedule_config(rule.trigger_type, updates["schedule_config_json"])
        rule.schedule_config_json = updates["schedule_config_json"]

    if "is_active" in updates:
        rule.is_active = 1 if updates["is_active"] else 0

    db.commit()
    db.refresh(rule)
    return _to_out(rule)


@router.delete("/{rule_id}", status_code=204)
def delete_automation_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    _require_admin_or_manager(current_user)
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    db.delete(rule)
    db.commit()
    return Response(status_code=204)
