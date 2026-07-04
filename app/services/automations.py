"""Automation rule creation service — thin DB-write layer (not pure core).

`create_automation_rule` is the single DB-write entry point for creating
automation rules.  Parsing and validation of trigger_type / schedule_config
live in app/core/automations.py (pure, testable without a DB).

Trigger wiring (router handlers that fire after-save rules, scheduler scan
that fires scheduled rules) is deferred to the next PR per the slice plan in
.devclaw/research/workflow-automation.md §6.

ADR-0001: this module has I/O (DB write) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.automations import (
    TRIGGER_AFTER_SAVE,
    TRIGGER_SCHEDULED,
    VALID_TRIGGER_TYPES,
    ScheduleConfig,
    schedule_config_to_json,
)
from app.core.clock import Clock
from app.models import AutomationRule


def create_automation_rule(
    db: Session,
    *,
    name: str,
    entity_type: str,
    trigger_type: str,
    conditions: list[dict[str, Any]],
    action_config: dict[str, Any],
    schedule_config: ScheduleConfig | None = None,
    clk: Clock,
) -> AutomationRule:
    """Insert an AutomationRule row and return it.

    Validates:
    - trigger_type is one of VALID_TRIGGER_TYPES
    - scheduled rules supply a schedule_config
    - after_save rules do not supply a schedule_config

    The caller owns the DB transaction — this function calls db.add() but does
    NOT commit.  This mirrors the pattern in app/services/history.py and
    app/services/notifications.py.
    """
    if trigger_type not in VALID_TRIGGER_TYPES:
        raise ValueError(f"unknown trigger_type: {trigger_type!r}")
    if trigger_type == TRIGGER_SCHEDULED and schedule_config is None:
        raise ValueError("scheduled rules require a schedule_config")
    if trigger_type == TRIGGER_AFTER_SAVE and schedule_config is not None:
        raise ValueError("after_save rules must not have a schedule_config")

    now = clk.now().isoformat()
    rule = AutomationRule(
        name=name,
        entity_type=entity_type,
        trigger_type=trigger_type,
        is_active=1,
        conditions_json=json.dumps(conditions),
        action_config_json=json.dumps(action_config),
        schedule_config_json=(
            schedule_config_to_json(schedule_config) if schedule_config else None
        ),
        last_fired_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(rule)
    return rule
