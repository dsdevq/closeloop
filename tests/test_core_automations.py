"""Pure unit tests for app/core/automations.py.

Tests the condition evaluator and message template renderer in isolation —
no DB, no HTTP (ADR-0001 / ADR-0005).  Coverage targets:
- evaluate_conditions: all five operators, AND-conjunctive semantics, empty list,
  missing fields, type-mismatch guards.
- render_message_template: happy path, missing key preservation, format error safety.
- SUPPORTED_TRIGGER_KINDS parity with app/core/history._KIND_MAP.
"""
import pytest

from app.core.automations import (
    SUPPORTED_OPS,
    SUPPORTED_TRIGGER_KINDS,
    Condition,
    evaluate_conditions,
    render_message_template,
)
from app.core.history import _KIND_MAP as HISTORY_KIND_MAP


# ---------------------------------------------------------------------------
# evaluate_conditions — empty list
# ---------------------------------------------------------------------------


def test_empty_conditions_always_fires():
    """No conditions → True for any snapshot (Pipedrive no-filter pattern)."""
    assert evaluate_conditions({"stage": "won"}, []) is True
    assert evaluate_conditions({}, []) is True


# ---------------------------------------------------------------------------
# evaluate_conditions — eq / neq
# ---------------------------------------------------------------------------


def test_eq_match():
    conds = [Condition(field="stage", op="eq", value="won")]
    assert evaluate_conditions({"stage": "won"}, conds) is True


def test_eq_no_match():
    conds = [Condition(field="stage", op="eq", value="won")]
    assert evaluate_conditions({"stage": "lead"}, conds) is False


def test_neq_match():
    conds = [Condition(field="stage", op="neq", value="lost")]
    assert evaluate_conditions({"stage": "won"}, conds) is True


def test_neq_no_match():
    conds = [Condition(field="stage", op="neq", value="won")]
    assert evaluate_conditions({"stage": "won"}, conds) is False


def test_eq_missing_field_vs_none():
    """Missing field resolves to None; None == None is True (eq)."""
    conds = [Condition(field="nonexistent", op="eq", value=None)]
    assert evaluate_conditions({"stage": "won"}, conds) is True


def test_eq_missing_field_not_equal_string():
    """Missing field (None) != "won", so eq should be False."""
    conds = [Condition(field="nonexistent", op="eq", value="won")]
    assert evaluate_conditions({"stage": "won"}, conds) is False


# ---------------------------------------------------------------------------
# evaluate_conditions — gt / lt
# ---------------------------------------------------------------------------


def test_gt_match():
    conds = [Condition(field="value", op="gt", value=5000)]
    assert evaluate_conditions({"value": 10000}, conds) is True


def test_gt_no_match():
    conds = [Condition(field="value", op="gt", value=5000)]
    assert evaluate_conditions({"value": 1000}, conds) is False


def test_gt_equal_is_false():
    conds = [Condition(field="value", op="gt", value=5000)]
    assert evaluate_conditions({"value": 5000}, conds) is False


def test_lt_match():
    conds = [Condition(field="lead_score", op="lt", value=0.5)]
    assert evaluate_conditions({"lead_score": 0.1}, conds) is True


def test_lt_no_match():
    conds = [Condition(field="lead_score", op="lt", value=0.5)]
    assert evaluate_conditions({"lead_score": 0.9}, conds) is False


def test_gt_missing_field_is_false():
    """Missing field → None; None > X raises TypeError → False (safe default)."""
    conds = [Condition(field="value", op="gt", value=0)]
    assert evaluate_conditions({}, conds) is False


def test_lt_missing_field_is_false():
    conds = [Condition(field="value", op="lt", value=9999)]
    assert evaluate_conditions({}, conds) is False


def test_gt_type_mismatch_is_false():
    """Comparing incompatible types (str > int) → False, not an exception."""
    conds = [Condition(field="stage", op="gt", value=100)]
    assert evaluate_conditions({"stage": "won"}, conds) is False


# ---------------------------------------------------------------------------
# evaluate_conditions — contains
# ---------------------------------------------------------------------------


def test_contains_match():
    conds = [Condition(field="title", op="contains", value="acme")]
    assert evaluate_conditions({"title": "ACME Corp deal"}, conds) is True


def test_contains_case_insensitive():
    conds = [Condition(field="title", op="contains", value="ACME")]
    assert evaluate_conditions({"title": "acme corp"}, conds) is True


def test_contains_no_match():
    conds = [Condition(field="title", op="contains", value="xyz")]
    assert evaluate_conditions({"title": "ACME Corp deal"}, conds) is False


def test_contains_missing_field_is_false():
    conds = [Condition(field="company", op="contains", value="tech")]
    assert evaluate_conditions({}, conds) is False


# ---------------------------------------------------------------------------
# evaluate_conditions — AND semantics (all must pass)
# ---------------------------------------------------------------------------


def test_and_all_pass():
    conds = [
        Condition(field="stage", op="eq", value="won"),
        Condition(field="value", op="gt", value=1000),
    ]
    assert evaluate_conditions({"stage": "won", "value": 5000}, conds) is True


def test_and_first_fails():
    conds = [
        Condition(field="stage", op="eq", value="won"),
        Condition(field="value", op="gt", value=1000),
    ]
    assert evaluate_conditions({"stage": "lead", "value": 5000}, conds) is False


def test_and_second_fails():
    conds = [
        Condition(field="stage", op="eq", value="won"),
        Condition(field="value", op="gt", value=1000),
    ]
    assert evaluate_conditions({"stage": "won", "value": 100}, conds) is False


def test_and_both_fail():
    conds = [
        Condition(field="stage", op="eq", value="won"),
        Condition(field="value", op="gt", value=1000),
    ]
    assert evaluate_conditions({"stage": "lead", "value": 0}, conds) is False


# ---------------------------------------------------------------------------
# evaluate_conditions — unknown operator (forward-compat safe default)
# ---------------------------------------------------------------------------


def test_unknown_op_returns_false():
    conds = [Condition(field="stage", op="regex", value=".*")]
    assert evaluate_conditions({"stage": "won"}, conds) is False


# ---------------------------------------------------------------------------
# render_message_template
# ---------------------------------------------------------------------------


def test_render_message_template_basic():
    result = render_message_template("Deal {title} moved to {stage}", {"title": "Acme", "stage": "won"})
    assert result == "Deal Acme moved to won"


def test_render_message_template_unknown_key_preserved():
    result = render_message_template("Hello {name}, value={value}", {"name": "Alice"})
    assert result == "Hello Alice, value={value}"


def test_render_message_template_empty_snapshot():
    result = render_message_template("No {vars} here", {})
    assert result == "No {vars} here"


def test_render_message_template_no_placeholders():
    result = render_message_template("Static message", {"stage": "won"})
    assert result == "Static message"


def test_render_message_template_integer_value():
    result = render_message_template("Value is {value}", {"value": 9999})
    assert result == "Value is 9999"


# ---------------------------------------------------------------------------
# SUPPORTED_TRIGGER_KINDS parity with history._KIND_MAP
# ---------------------------------------------------------------------------


def test_supported_trigger_kinds_match_history_kind_map():
    """SUPPORTED_TRIGGER_KINDS must stay in sync with the history event kind set.

    This test enforces the research doc's constraint: "AutomationRule.trigger_kind
    is drawn from the same closed set as HistoryEntry.kind" (workflow-automation.md §3).
    """
    assert SUPPORTED_TRIGGER_KINDS == frozenset(HISTORY_KIND_MAP.keys())


# ---------------------------------------------------------------------------
# SUPPORTED_OPS completeness
# ---------------------------------------------------------------------------


def test_supported_ops_contains_required_set():
    assert {"eq", "neq", "gt", "lt", "contains"}.issubset(SUPPORTED_OPS)
