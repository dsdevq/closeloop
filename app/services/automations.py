"""Automation rule evaluation — Trigger → Condition → Action engine.

`_parse_conditions` is fail-closed: a malformed conditions_json raises
`ConditionsParseError` so that `execute_automation_rules` skips the rule
entirely rather than treating it as "no conditions → fires unconditionally".

`_parse_schedule_config` follows the same fail-closed contract for scheduled
rules: a missing, blank, or invalid schedule_config_json raises
`ScheduleConfigParseError` so `run_scheduled_automations` skips the rule
rather than firing at an undefined time.

The two cases are deliberately distinct:
  - conditions_json is NULL / "" / "[]"  →  empty list  →  fires unconditionally
    (intentional: a rule configured with no conditions should always match)
  - conditions_json is non-empty but unparseable  →  ConditionsParseError  →
    rule is skipped (corrupted data must never silently expand the trigger scope)

Multi-worker race condition prevention:
  run_scheduled_automations() uses a compare-and-swap (CAS) UPDATE to claim
  each due rule before firing it.  The UPDATE sets last_triggered_at WHERE
  id = rule.id AND last_triggered_at IS <the exact value read> — handling NULL
  (never-fired) and non-NULL (previously fired) separately.  If rowcount == 0,
  another worker already claimed the rule this cycle and execution is skipped.
  SQLite serialises concurrent writers through its write lock, so exactly one
  worker's UPDATE wins.  The claim is committed immediately after the CAS
  succeeds, before condition evaluation — so a conditions=false outcome does
  not silently roll back the claim and re-expose the rule as due on the next
  poll cycle.  See also: DOMAIN.md §ScheduledTrigger.

ADR-0001: this module has I/O (DB read/write) so it lives in app/services/,
not app/core/.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
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


class ScheduleConfigParseError(ValueError):
    """Raised when schedule_config_json is missing, blank, or structurally invalid.

    Callers of `_parse_schedule_config` MUST catch this and skip the rule.
    A scheduled rule with no valid config must never fire — fail-closed.
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


def _parse_schedule_config(config_json: str | None) -> dict:
    """Parse and validate a scheduled rule's schedule_config_json.

    Raises ScheduleConfigParseError when:
    - config_json is NULL or blank (scheduled rules MUST have a config)
    - JSON is invalid or not an object
    - Neither 'interval_minutes' nor 'run_once_at' key is present
    - interval_minutes is not a positive integer
    - run_once_at is not a parseable ISO-8601 datetime string

    Returns a validated dict — one of:
    - {"interval_minutes": int}   recurring rule, fires every N minutes
    - {"run_once_at": datetime}   one-shot rule (run_once_at already parsed to datetime)
    """
    stripped = config_json.strip() if config_json else ""
    if not stripped:
        raise ScheduleConfigParseError(
            "schedule_config_json is required for scheduled rules but is missing or empty"
        )
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ScheduleConfigParseError(
            f"schedule_config_json is not valid JSON: {exc!r}"
        ) from exc
    if not isinstance(parsed, dict):
        raise ScheduleConfigParseError(
            f"schedule_config_json must be a JSON object, got {type(parsed).__name__}"
        )
    if "interval_minutes" in parsed:
        minutes = parsed["interval_minutes"]
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes <= 0:
            raise ScheduleConfigParseError(
                f"interval_minutes must be a positive integer, got {minutes!r}"
            )
        return {"interval_minutes": minutes}
    if "run_once_at" in parsed:
        raw = parsed["run_once_at"]
        try:
            dt = datetime.fromisoformat(str(raw))
        except (ValueError, TypeError) as exc:
            raise ScheduleConfigParseError(
                f"run_once_at is not a valid ISO-8601 datetime: {raw!r}"
            ) from exc
        return {"run_once_at": dt}
    raise ScheduleConfigParseError(
        "schedule_config_json must contain 'interval_minutes' or 'run_once_at'"
    )


def is_due(
    schedule_config: dict,
    last_triggered_at: datetime | None,
    reference_time: datetime,
) -> bool:
    """Return True if a scheduled automation rule is due to fire at reference_time.

    Pure function — no I/O, no side effects.  All datetime comparison is done
    after stripping timezone info (all times are treated as UTC, per ADR-0006).

    interval_minutes rules:
    - Due immediately on first poll (last_triggered_at is None)
    - Due when reference_time >= last_triggered_at + interval

    run_once_at rules:
    - Due when last_triggered_at is None AND reference_time >= run_once_at
    - NOT due (expired) when last_triggered_at is not None (already fired)
    """
    # Strip tzinfo for comparison — all stored times are UTC (ADR-0006)
    ref = reference_time.replace(tzinfo=None) if reference_time.tzinfo else reference_time

    if "interval_minutes" in schedule_config:
        if last_triggered_at is None:
            return True
        last = last_triggered_at.replace(tzinfo=None) if last_triggered_at.tzinfo else last_triggered_at
        return ref >= last + timedelta(minutes=schedule_config["interval_minutes"])

    if "run_once_at" in schedule_config:
        if last_triggered_at is not None:
            return False  # already fired — expired
        target = schedule_config["run_once_at"]
        t = target.replace(tzinfo=None) if target.tzinfo else target
        return ref >= t

    return False  # unknown kind → not due (safe default)


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
    """Evaluate and execute all active after_save AutomationRules for *trigger_event*.

    Only rules with trigger_type == "after_save" are evaluated here.  Scheduled
    rules are handled exclusively by run_scheduled_automations().

    For each matching rule:
      1. Parse conditions_json via `_parse_conditions`.
         On ConditionsParseError the rule is logged and skipped (fail-closed).
      2. Evaluate parsed conditions against *context*.
         If they do not match, the rule is skipped.
      3. Dispatch `_execute_action` for rules that pass conditions.

    Returns the count of rules that actually fired (useful for callers and tests).
    """
    rules: list[AutomationRule] = (
        db.query(AutomationRule)
        .filter_by(trigger_event=trigger_event, trigger_type="after_save", is_active=1)
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


def run_scheduled_automations(db: Session, *, clk: Clock) -> int:
    """Poll all active scheduled AutomationRules and fire those that are due.

    Unlike execute_automation_rules (called within a router's transaction),
    this function is the transaction owner: it commits after claiming and firing
    due rules.  It is called exclusively by the background poller in app/main.py,
    never inline in a request handler — no second evaluation pipeline is introduced.

    Race condition prevention (multi-worker CAS):
      Before calling _execute_action, an atomic UPDATE is issued that sets
      last_triggered_at = now WHERE id = rule.id AND last_triggered_at IS
      <the exact value read> (NULL-safe: IS NULL vs = :old_val).  If rowcount
      is 0, another Gunicorn worker already claimed this rule this cycle and
      we skip without firing.  SQLite serialises concurrent writers so exactly
      one worker's UPDATE will win per cycle.

    Commit-guard invariant:
      The CAS claim (last_triggered_at UPDATE) is committed immediately after
      rowcount == 1 is confirmed, BEFORE condition evaluation.  This ensures
      the claim persists even when conditions evaluate false — without this
      commit, a conditions=false outcome would roll back the UPDATE and the
      next poll cycle would re-treat the rule as due, silently defeating the
      exactly-once guarantee.

    For each scheduled rule:
      1. Parse schedule_config_json (fail-closed on ScheduleConfigParseError).
      2. Parse last_triggered_at from stored ISO-8601 string.
      3. Call is_due() to decide whether to fire.
      4. CAS UPDATE to claim the rule — skip if rowcount == 0.
      5. Commit the claim unconditionally.
      6. Parse conditions_json (fail-closed on ConditionsParseError).
      7. Evaluate conditions against an empty context dict (scheduled rules
         carry no entity snapshot; unconditional rules fire; field-condition
         rules will not match and are silently skipped — future slice).
      8. Call _execute_action().

    Returns the count of rules that fired.
    """
    now = clk.now()
    rules: list[AutomationRule] = (
        db.query(AutomationRule)
        .filter_by(trigger_type="scheduled", is_active=1)
        .all()
    )
    fired = 0
    for rule in rules:
        try:
            config = _parse_schedule_config(rule.schedule_config_json)
        except ScheduleConfigParseError:
            logger.warning(
                "scheduled automation rule %d (%r) skipped: schedule_config_json is malformed",
                rule.id,
                rule.name,
            )
            continue

        last_triggered_at: datetime | None = None
        if rule.last_triggered_at:
            try:
                last_triggered_at = datetime.fromisoformat(rule.last_triggered_at)
            except ValueError:
                logger.warning(
                    "scheduled automation rule %d (%r): unparseable last_triggered_at %r"
                    " — treating as never fired",
                    rule.id,
                    rule.name,
                    rule.last_triggered_at,
                )

        if not is_due(config, last_triggered_at, now):
            continue

        # CAS claim: atomically set last_triggered_at only if the DB row still
        # has the value we read.  A concurrent worker that already committed this
        # update will cause rowcount == 0 here, and we skip without firing.
        new_val = now.isoformat()
        old_val = rule.last_triggered_at  # the string value we read, or None
        if old_val is None:
            result = db.execute(
                text(
                    "UPDATE automation_rules SET last_triggered_at = :new"
                    " WHERE id = :id AND last_triggered_at IS NULL"
                ),
                {"new": new_val, "id": rule.id},
            )
        else:
            result = db.execute(
                text(
                    "UPDATE automation_rules SET last_triggered_at = :new"
                    " WHERE id = :id AND last_triggered_at = :old"
                ),
                {"new": new_val, "id": rule.id, "old": old_val},
            )
        if result.rowcount == 0:
            # Another worker already claimed this rule this cycle — skip.
            continue

        # Persist the claim before evaluating conditions.  last_triggered_at
        # must be committed here so that a conditions=false outcome does not
        # silently roll back this UPDATE and re-expose the rule as due on the
        # next poll cycle.  See the commit-guard invariant in the docstring.
        db.commit()

        try:
            conditions = _parse_conditions(rule.conditions_json)
        except ConditionsParseError:
            logger.warning(
                "scheduled automation rule %d (%r) skipped: conditions_json is malformed",
                rule.id,
                rule.name,
            )
            continue

        if not evaluate_conditions(conditions, {}):
            continue

        _execute_action(db, rule, {}, clk)
        fired += 1

    if fired:
        db.commit()
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
        "automation rule %d action=%r trigger_type=%r fired; context_keys=%r",
        rule.id,
        rule.action_type,
        rule.trigger_type,
        list(context.keys()),
    )
