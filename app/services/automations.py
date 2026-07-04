"""Automation rule creation + scheduled execution service.

`create_automation_rule` is the single DB-write entry point for creating
automation rules.  Parsing and validation of trigger_type / schedule_config
live in app/core/automations.py (pure, testable without a DB).

`check_scheduled_rules` is the periodic scanner called by the asyncio
background poller wired in app/main.py.  It queries all active scheduled
rules, calls `is_rule_due()` for each, and fires due rules by executing
their action and updating last_fired_at.

No existing scheduler/worker exists in this stack (no APScheduler, Celery, or
cron runner — checked requirements.txt and all app/ code).  A minimal asyncio
background task in app/main.py calls this function every 60 s — the lightweight
poller pattern added per .devclaw/research/workflow-automation.md §6.

The action execution path (_execute_rule_action) is shared: both the scheduled
poller and future after-save wiring will call it to avoid forking a second
evaluation pipeline.

Fail-closed precedent (PR #53): rules with malformed schedule_config_json or
unknown action kinds are silently skipped and never fire.

ADR-0001: this module has I/O (DB read/write) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.core.automations import (
    TRIGGER_AFTER_SAVE,
    TRIGGER_SCHEDULED,
    VALID_TRIGGER_TYPES,
    ScheduleConfig,
    is_rule_due,
    schedule_config_from_json,
    schedule_config_to_json,
)
from app.core.clock import Clock
from app.models import AutomationRule, Notification, User

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Action execution — shared by scheduled poller and future after-save wiring
# ---------------------------------------------------------------------------


def _action_notify_user(
    db: Session, rule: AutomationRule, action: dict, clk: Clock
) -> None:
    """Create an in-app notification for the recipient in action['recipient_id'].

    Fails silently when recipient_id is absent, wrong type, or the recipient
    does not exist / is inactive.  The kind 'automation_fired' sits outside the
    typed NotificationEvent union; the read endpoint renders it with message=""
    until a later slice adds full rendering support.
    """
    recipient_id = action.get("recipient_id")
    if not isinstance(recipient_id, int):
        return
    user = db.query(User).filter(User.id == recipient_id, User.is_active == 1).first()
    if not user:
        return
    db.add(
        Notification(
            recipient_id=recipient_id,
            actor_id=None,
            kind="automation_fired",
            entity_type="automation_rule",
            entity_id=rule.id,
            payload_json=json.dumps(
                {
                    "kind": "automation_fired",
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                }
            ),
            created_at=clk.now().isoformat(),
        )
    )


def _execute_rule_action(db: Session, rule: AutomationRule, clk: Clock) -> None:
    """Dispatch the action described by rule.action_config_json.

    Silently skips unknown action kinds or malformed action_config_json.
    The caller (check_scheduled_rules) still updates last_fired_at after this
    returns to avoid retry loops for persistently broken action configs.
    """
    try:
        action: dict = json.loads(rule.action_config_json)
    except (json.JSONDecodeError, TypeError):
        return

    kind = action.get("kind")
    if kind == "notify_user":
        _action_notify_user(db, rule, action, clk)


# ---------------------------------------------------------------------------
# Scheduled rule scanner — called by the background poller in app/main.py
# ---------------------------------------------------------------------------


def check_scheduled_rules(db: Session, clk: Clock) -> int:
    """Scan active scheduled rules and fire any that are due now.

    Fail-closed: rules with NULL or malformed schedule_config_json are silently
    skipped — consistent with the malformed-conditions precedent from PR #53.

    field_offset rules require an anchor_field_value resolved from the entity
    row; since per-entity scanning is deferred to a later slice, those rules
    raise ValueError inside is_rule_due() (no anchor_field_value supplied) and
    are caught here, causing them to be skipped silently this slice.

    Each rule that fires is committed individually to limit blast radius.
    Errors during individual rule execution are logged and the loop continues,
    so one broken rule does not block subsequent rules.

    Returns the count of rules fired this pass.
    """
    rules = (
        db.query(AutomationRule)
        .filter(
            AutomationRule.trigger_type == TRIGGER_SCHEDULED,
            AutomationRule.is_active == 1,
        )
        .all()
    )

    now = clk.now()
    fired = 0

    for rule in rules:
        # Fail-closed: NULL schedule_config_json is invalid for a scheduled rule
        if not rule.schedule_config_json:
            continue

        try:
            cfg = schedule_config_from_json(rule.schedule_config_json)
        except ValueError:
            continue  # malformed config → skip silently

        last_fired_at: datetime | None = None
        if rule.last_fired_at:
            try:
                last_fired_at = datetime.fromisoformat(rule.last_fired_at)
            except ValueError:
                continue  # malformed timestamp → fail-closed

        try:
            due = is_rule_due(cfg, now, last_fired_at=last_fired_at)
        except ValueError:
            # field_offset without anchor_field_value — entity scan deferred
            continue

        if not due:
            continue

        try:
            _execute_rule_action(db, rule, clk)
            rule.last_fired_at = now.isoformat()
            rule.updated_at = now.isoformat()
            db.commit()
            fired += 1
        except Exception:
            db.rollback()
            logger.exception(
                "error firing scheduled rule id=%d name=%r", rule.id, rule.name
            )

    return fired
