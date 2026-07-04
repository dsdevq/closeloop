"""Workflow automation rule model — pure typed definitions (ADR-0001).

Condition/evaluate_conditions mirrors the declarative field-value filter model
borrowed from Salesforce Process Builder, HubSpot Workflows, and Zoho Workflow
Rules.  render_message_template is the pure counterpart to the I/O-bearing
execute_automation_action in app/services/automations.py.

Trigger kind vocabulary is drawn directly from app.core.history._KIND_MAP
(Pipedrive/Salesforce closed trigger-event-enum pattern): no separate trigger
taxonomy is defined — the automation engine is a consumer of the existing kind
set, not a producer of a new one.

See .devclaw/research/workflow-automation.md §2–4 for full design rationale and
the borrowed/rejected pattern table.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Closed operator set (Attio condition operators, extended for common CRM ops)
# ---------------------------------------------------------------------------

SUPPORTED_OPS: frozenset[str] = frozenset({"eq", "neq", "gt", "lt", "contains"})

# ---------------------------------------------------------------------------
# Trigger kind vocabulary — identical to app.core.history._KIND_MAP keys.
# (Pipedrive trigger-event-enum / Salesforce closed trigger type pattern.)
# Keeping them in sync is enforced by tests/test_core_automations.py.
# ---------------------------------------------------------------------------

SUPPORTED_TRIGGER_KINDS: frozenset[str] = frozenset({
    "deal_created",
    "deal_stage_changed",
    "deal_assigned",
    "deal_updated",
    "deal_deleted",
    "contact_created",
    "contact_updated",
    "contact_deleted",
    "activity_created",
    "activity_updated",
    "activity_completed",
    "activity_deleted",
})

SUPPORTED_ENTITY_TYPES: frozenset[str] = frozenset({"deal", "contact", "activity"})


# ---------------------------------------------------------------------------
# Condition dataclass
# ---------------------------------------------------------------------------


@dataclass
class Condition:
    """A single field-value filter applied in the AND-conjunctive condition list.

    Shape stored in conditions_json: {"field": "stage", "op": "eq", "value": "won"}
    """
    field: str
    op: str      # must be in SUPPORTED_OPS
    value: Any   # compared against entity_snapshot[field] at evaluation time


# ---------------------------------------------------------------------------
# Condition evaluation — pure, no I/O
# ---------------------------------------------------------------------------


def evaluate_conditions(
    entity_snapshot: dict[str, Any],
    conditions: list[Condition],
) -> bool:
    """Return True if ALL conditions pass against entity_snapshot (AND-only).

    Empty conditions list → always returns True: the trigger kind alone is
    sufficient to fire the rule (Pipedrive no-op-when-no-conditions pattern).

    Borrowed from Salesforce declarative criteria, HubSpot enrollment filters,
    and Attio attribute-equality conditions.  OR-logic is explicitly rejected
    (see .devclaw/research/workflow-automation.md §2.1 Rejected).
    """
    for cond in conditions:
        actual = entity_snapshot.get(cond.field)
        if not _eval_one(actual, cond.op, cond.value):
            return False
    return True


def _eval_one(actual: Any, op: str, expected: Any) -> bool:
    """Evaluate a single condition triple (actual op expected)."""
    if op == "eq":
        return actual == expected
    if op == "neq":
        return actual != expected
    if op == "gt":
        if actual is None:
            return False
        try:
            return actual > expected  # type: ignore[operator]
        except TypeError:
            return False
    if op == "lt":
        if actual is None:
            return False
        try:
            return actual < expected  # type: ignore[operator]
        except TypeError:
            return False
    if op == "contains":
        if actual is None:
            return False
        return str(expected).lower() in str(actual).lower()
    return False  # unknown op — safe false default for forward-compatibility


# ---------------------------------------------------------------------------
# Message template rendering — pure, no I/O
# ---------------------------------------------------------------------------


class _SafeDict(dict):
    """dict subclass that preserves unknown {key} placeholders on format_map()."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def render_message_template(template: str, entity_snapshot: dict[str, Any]) -> str:
    """Render a message_template string using entity_snapshot as context variables.

    Unknown placeholders are preserved as-is so a partially-matched template
    degrades gracefully rather than raising KeyError.
    """
    try:
        return template.format_map(_SafeDict(entity_snapshot))
    except (ValueError, KeyError):
        return template
