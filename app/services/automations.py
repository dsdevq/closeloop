"""Automation rule evaluation — Trigger → Condition → Action engine.

`_parse_conditions` is fail-closed: a malformed conditions_json raises
`ConditionsParseError` so that `execute_automation_rules` skips the rule
entirely rather than treating it as "no conditions → fires unconditionally".

The two cases are deliberately distinct:
  - conditions_json is NULL / "" / "[]"  →  empty list  →  fires unconditionally
    (intentional: a rule configured with no conditions should always match)
  - conditions_json is non-empty but unparseable  →  ConditionsParseError  →
    rule is skipped (corrupted data must never silently expand the trigger scope)

ADR-0001: this module has I/O (DB read) so it lives in app/services/, not app/core/.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models import AutomationRule

logger = logging.getLogger(__name__)


class ConditionsParseError(ValueError):
    """Raised when conditions_json is present but cannot be decoded as a condition list.

    Callers of `_parse_conditions` MUST catch this and skip the rule rather than
    falling back to an empty list — otherwise a corrupted conditions string would
    silently become an unconditional trigger (the opposite of a safe default).
    """


def _parse_conditions(conditions_json: str | None) -> list[dict]:
    """Parse the conditions JSON from an AutomationRule row.

    Returns an empty list when conditions_json is NULL, blank, "null", or "[]" —
    all of which represent an intentionally condition-free rule (fires on every
    matching trigger event).

    Raises ConditionsParseError when conditions_json is a non-empty string that
    fails JSON decoding or is not a JSON array.  Callers must catch this exception
    and skip the rule (fail-closed): corrupted conditions must never be silently
    collapsed into an unconditional fire.
    """
    stripped = conditions_json.strip() if conditions_json else ""
    if not stripped or stripped in ("null", "[]"):
        return []
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ConditionsParseError(
            f"conditions_json is not valid JSON: {exc!r}"
        ) from exc
    if not isinstance(parsed, list):
        raise ConditionsParseError(
            f"conditions_json must be a JSON array, got {type(parsed).__name__}"
        )
    return parsed  # type: ignore[return-value]


def evaluate_conditions(conditions: list[dict], context: dict[str, Any]) -> bool:
    """Return True iff every condition matches the context (AND semantics).

    An empty conditions list means no conditions → always True.
    Supported operators: "eq", "neq", "in".
    An unrecognised operator or missing context field evaluates to False
    (safe default — better to miss a fire than to fire spuriously).
    """
    for cond in conditions:
        field = cond.get("field", "")
        op = cond.get("op", "")
        expected = cond.get("value")
        actual = context.get(field)
        if op == "eq":
            if actual != expected:
                return False
        elif op == "neq":
            if actual == expected:
                return False
        elif op == "in":
            if not isinstance(expected, list) or actual not in expected:
                return False
        else:
            return False
    return True


def execute_automation_rules(
    db: Session,
    *,
    trigger_event: str,
    context: dict[str, Any],
    clk: Clock,
) -> int:
    """Evaluate and execute all active AutomationRules for *trigger_event*.

    For each active rule:
      1. Parse conditions_json via `_parse_conditions`.
         On ConditionsParseError the rule is logged and skipped (fail-closed).
      2. Evaluate parsed conditions against *context*.
         If they do not match, the rule is skipped.
      3. Dispatch `_execute_action` for rules that pass conditions.

    Returns the count of rules that actually fired (useful for callers and tests).
    """
    rules: list[AutomationRule] = (
        db.query(AutomationRule)
        .filter_by(trigger_event=trigger_event, is_active=1)
        .all()
    )
    fired = 0
    for rule in rules:
        try:
            conditions = _parse_conditions(rule.conditions_json)
        except ConditionsParseError:
            logger.warning(
                "automation rule %d (%r) skipped: conditions_json is malformed",
                rule.id,
                rule.name,
            )
            continue
        if not evaluate_conditions(conditions, context):
            continue
        _execute_action(db, rule, context, clk)
        fired += 1
    return fired


def _execute_action(
    db: Session,
    rule: AutomationRule,
    context: dict[str, Any],
    clk: Clock,
) -> None:
    """Dispatch to the action handler for rule.action_type.

    Action handlers for individual action_type values are added in later slices.
    """
    logger.debug(
        "automation rule %d action=%r fired for trigger=%r context=%r",
        rule.id,
        rule.action_type,
        rule.trigger_event,
        context,
    )
