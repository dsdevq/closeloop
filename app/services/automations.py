"""Workflow automation service — query, evaluate, and execute loop.

execute_automation_rules() is the single entry point for trigger wiring in route
handlers.  It is called inline after the domain mutation and alongside
record_history() / create_notification(), before db.commit() — the same After-Save
position established by PR #43 (notifications) and PR #46–47 (history).

Execution model borrowed from:
- Attio: "at the point of the attribute write, synchronously, before the response
  is sent" (workflow-automation.md §2.4).
- Salesforce Record-Triggered Flow: After-Save execution in the same transaction
  as the mutation (§2.1).
- HubSpot / Zoho: declarative criteria evaluated per rule; action executed only
  when all criteria pass (§2.2 / §2.5).

ADR-0001: this module has I/O (DB reads + writes) so it lives in app/services/,
not app/core/.  The pure condition evaluator is in app/core/automations.py.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.automations import Condition, evaluate_conditions, render_message_template
from app.core.clock import Clock
from app.core.notifications import AutomationTriggeredEvent
from app.models import AutomationRule, User
from app.services.notifications import create_notification


def execute_automation_rules(
    db: Session,
    *,
    trigger_kind: str,
    entity_type: str,
    entity_snapshot: dict[str, Any],
    actor: User,
    clk: Clock,
) -> list[AutomationRule]:
    """Evaluate all active rules for trigger_kind + entity_type.

    For each matching rule, evaluates its conditions against entity_snapshot
    (AND-only conjunctive, Salesforce/Pipedrive/Attio pattern).  If all conditions
    pass, executes the rule's action.  Does NOT commit — caller owns the transaction.

    Returns the list of rules that fired (conditions passed and action executed).
    The return value is used in tests to assert trigger behaviour without having
    to inspect side-effect rows — mirrors the return convention of create_notification()
    and record_history().
    """
    rules: list[AutomationRule] = (
        db.query(AutomationRule)
        .filter(
            AutomationRule.entity_type == entity_type,
            AutomationRule.trigger_kind == trigger_kind,
            AutomationRule.is_active == 1,
        )
        .all()
    )

    fired: list[AutomationRule] = []
    for rule in rules:
        conditions = _parse_conditions(rule.conditions_json)
        if evaluate_conditions(entity_snapshot, conditions):
            execute_automation_action(
                db, rule=rule, actor=actor, clk=clk, entity_snapshot=entity_snapshot
            )
            fired.append(rule)
    return fired


def execute_automation_action(
    db: Session,
    *,
    rule: AutomationRule,
    actor: User,
    clk: Clock,
    entity_snapshot: dict[str, Any],
) -> None:
    """Dispatch a single rule's action.

    Does NOT commit — caller owns the transaction.
    Unknown action kinds are silently skipped for forward-compatibility with
    action types added in later slices (e.g. create_activity in slice 2).
    """
    if rule.action_kind == "notify_user":
        _action_notify_user(db, rule=rule, actor=actor, clk=clk, entity_snapshot=entity_snapshot)


def _action_notify_user(
    db: Session,
    *,
    rule: AutomationRule,
    actor: User,
    clk: Clock,
    entity_snapshot: dict[str, Any],
) -> None:
    """Execute a notify_user action by calling the existing create_notification() service.

    Automation is a new *caller* of create_notification(), not a new notification
    path — consistent with Attio's "notify a team member" action pattern
    (workflow-automation.md §2.4) and Zoho's email-alert action (§2.5).

    Self-notification suppression: recipient_id == actor.id → silently skipped.
    This reuses the same guard as the hardcoded deal/stage triggers
    (HubSpot/Zoho pattern: "don't notify the actor of their own action").
    """
    try:
        params: dict = json.loads(rule.action_params_json)
    except (json.JSONDecodeError, TypeError):
        return

    recipient_id = params.get("recipient_id")
    if not isinstance(recipient_id, int):
        return

    if recipient_id == actor.id:
        return

    template = params.get("message_template") or rule.name
    message = render_message_template(template, entity_snapshot)

    create_notification(
        db,
        recipient_id=recipient_id,
        event=AutomationTriggeredEvent(
            rule_id=rule.id,
            rule_name=rule.name,
            actor_id=actor.id,
            message=message,
        ),
        entity_type=None,
        entity_id=None,
        clk=clk,
    )


def _parse_conditions(conditions_json: str) -> list[Condition]:
    """Deserialise conditions_json to a list of Condition dataclasses.

    Entries missing required keys (field / op / value) are silently dropped.
    A malformed JSON string returns an empty list (fire unconditionally).
    """
    try:
        raw: list[dict] = json.loads(conditions_json)
    except (json.JSONDecodeError, TypeError):
        return []
    result: list[Condition] = []
    for c in raw:
        if isinstance(c, dict) and "field" in c and "op" in c and "value" in c:
            result.append(Condition(field=c["field"], op=c["op"], value=c["value"]))
    return result
