"""Tests for app/services/automations.py.

Covers:
  - _parse_conditions: valid, empty/null/blank inputs, malformed JSON, non-array JSON
  - evaluate_conditions: empty list (unconditional), matching, non-matching, unknown op
  - execute_automation_rules: malformed conditions_json skips the rule (fail-closed);
    valid-empty conditions fires unconditionally; matching/non-matching conditions
    control firing as expected.

The malformed-conditions test (test_malformed_conditions_json_skips_rule) is the
critical regression guard: it MUST fail against any implementation that returns []
on parse error (the buggy behavior) and pass with the fail-closed implementation.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import AutomationRule
from app.services.automations import (
    ConditionsParseError,
    _parse_conditions,
    evaluate_conditions,
    execute_automation_rules,
)


# ── _parse_conditions: pure-function unit tests ───────────────────────────────


def test_parse_conditions_none_returns_empty():
    assert _parse_conditions(None) == []


def test_parse_conditions_empty_string_returns_empty():
    assert _parse_conditions("") == []


def test_parse_conditions_whitespace_only_returns_empty():
    assert _parse_conditions("   ") == []


def test_parse_conditions_null_string_returns_empty():
    assert _parse_conditions("null") == []


def test_parse_conditions_empty_array_string_returns_empty():
    assert _parse_conditions("[]") == []


def test_parse_conditions_valid_returns_list():
    result = _parse_conditions('[{"field": "stage", "op": "eq", "value": "qualified"}]')
    assert result == [{"field": "stage", "op": "eq", "value": "qualified"}]


def test_parse_conditions_multiple_conditions():
    raw = '[{"field": "stage", "op": "eq", "value": "won"}, {"field": "value", "op": "eq", "value": 5000}]'
    result = _parse_conditions(raw)
    assert len(result) == 2
    assert result[0]["field"] == "stage"
    assert result[1]["field"] == "value"


def test_parse_conditions_malformed_raises_parse_error():
    with pytest.raises(ConditionsParseError):
        _parse_conditions("not valid json")


def test_parse_conditions_partial_json_raises():
    with pytest.raises(ConditionsParseError):
        _parse_conditions('[{"field": "stage"')


def test_parse_conditions_object_not_array_raises():
    """A JSON object (not array) must raise ConditionsParseError, not silently return."""
    with pytest.raises(ConditionsParseError):
        _parse_conditions('{"field": "stage", "op": "eq", "value": "won"}')


def test_parse_conditions_string_scalar_raises():
    with pytest.raises(ConditionsParseError):
        _parse_conditions('"just a string"')


def test_parse_conditions_error_is_not_empty_list():
    """The bug: malformed conditions must NOT silently collapse to [].
    If _parse_conditions returned [] on error, evaluate_conditions([]) would
    return True, causing the rule to fire unconditionally — wrong behavior.
    """
    with pytest.raises(ConditionsParseError):
        _parse_conditions("not valid json")


# ── evaluate_conditions: pure-function unit tests ────────────────────────────


def test_evaluate_empty_conditions_always_true():
    assert evaluate_conditions([], {}) is True
    assert evaluate_conditions([], {"stage": "won", "value": 9999}) is True


def test_evaluate_eq_match():
    conds = [{"field": "stage", "op": "eq", "value": "qualified"}]
    assert evaluate_conditions(conds, {"stage": "qualified"}) is True


def test_evaluate_eq_no_match():
    conds = [{"field": "stage", "op": "eq", "value": "qualified"}]
    assert evaluate_conditions(conds, {"stage": "lead"}) is False


def test_evaluate_neq_match():
    conds = [{"field": "stage", "op": "neq", "value": "lost"}]
    assert evaluate_conditions(conds, {"stage": "qualified"}) is True


def test_evaluate_neq_no_match():
    conds = [{"field": "stage", "op": "neq", "value": "lost"}]
    assert evaluate_conditions(conds, {"stage": "lost"}) is False


def test_evaluate_in_match():
    conds = [{"field": "stage", "op": "in", "value": ["qualified", "proposal"]}]
    assert evaluate_conditions(conds, {"stage": "proposal"}) is True


def test_evaluate_in_no_match():
    conds = [{"field": "stage", "op": "in", "value": ["qualified", "proposal"]}]
    assert evaluate_conditions(conds, {"stage": "lead"}) is False


def test_evaluate_unknown_op_returns_false():
    conds = [{"field": "stage", "op": "regex", "value": "qual.*"}]
    assert evaluate_conditions(conds, {"stage": "qualified"}) is False


def test_evaluate_missing_field_returns_false():
    conds = [{"field": "nonexistent", "op": "eq", "value": "anything"}]
    assert evaluate_conditions(conds, {"stage": "qualified"}) is False


def test_evaluate_multiple_conditions_all_must_match():
    conds = [
        {"field": "stage", "op": "eq", "value": "won"},
        {"field": "value", "op": "eq", "value": 5000},
    ]
    assert evaluate_conditions(conds, {"stage": "won", "value": 5000}) is True
    assert evaluate_conditions(conds, {"stage": "won", "value": 999}) is False
    assert evaluate_conditions(conds, {"stage": "lead", "value": 5000}) is False


# ── execute_automation_rules: integration tests (uses in-memory DB) ───────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_rule(
    db: Session,
    *,
    trigger_event: str = "deal.stage_changed",
    conditions_json: str | None = None,
    action_type: str = "notify",
    is_active: int = 1,
    name: str = "Test Rule",
) -> AutomationRule:
    rule = AutomationRule(
        name=name,
        trigger_event=trigger_event,
        conditions_json=conditions_json,
        action_type=action_type,
        action_config_json="{}",
        is_active=is_active,
        created_at=_now(),
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def _make_clock():
    from app.core.clock import Clock
    return Clock()


def test_malformed_conditions_json_skips_rule(client, db_session):
    """Rule with malformed conditions_json must not fire — fail-closed.

    This is the critical regression test for the bug: an earlier implementation
    returned [] on parse error, which evaluate_conditions treated as "no conditions
    → always match", causing the rule to fire unconditionally on corrupted data.

    With the fix, _parse_conditions raises ConditionsParseError and
    execute_automation_rules skips the rule → fired count == 0.
    """
    _seed_rule(db_session, conditions_json="not valid json")

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={"stage": "qualified"},
        clk=_make_clock(),
    )
    assert fired == 0, (
        "A rule with malformed conditions_json must be skipped, not fired. "
        "If this fails, _parse_conditions is returning [] on parse error "
        "instead of raising ConditionsParseError."
    )


def test_null_conditions_fires_unconditionally(client, db_session):
    """Rule with conditions_json=NULL (no conditions) fires on any matching trigger."""
    _seed_rule(db_session, conditions_json=None)

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={"stage": "any"},
        clk=_make_clock(),
    )
    assert fired == 1


def test_empty_array_conditions_fires_unconditionally(client, db_session):
    """Rule with conditions_json='[]' fires on any matching trigger (explicit empty)."""
    _seed_rule(db_session, conditions_json="[]")

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={},
        clk=_make_clock(),
    )
    assert fired == 1


def test_matching_conditions_fires(client, db_session):
    """Rule fires when conditions match the context."""
    _seed_rule(
        db_session,
        conditions_json='[{"field": "stage", "op": "eq", "value": "qualified"}]',
    )

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={"stage": "qualified"},
        clk=_make_clock(),
    )
    assert fired == 1


def test_non_matching_conditions_skips(client, db_session):
    """Rule does not fire when conditions do not match the context."""
    _seed_rule(
        db_session,
        conditions_json='[{"field": "stage", "op": "eq", "value": "qualified"}]',
    )

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={"stage": "lead"},
        clk=_make_clock(),
    )
    assert fired == 0


def test_inactive_rule_never_fires(client, db_session):
    """Inactive rules (is_active=0) are ignored regardless of conditions."""
    _seed_rule(db_session, conditions_json=None, is_active=0)

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={},
        clk=_make_clock(),
    )
    assert fired == 0


def test_wrong_trigger_event_skips(client, db_session):
    """Rules do not fire for events other than their own trigger_event."""
    _seed_rule(db_session, trigger_event="deal.created", conditions_json=None)

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={},
        clk=_make_clock(),
    )
    assert fired == 0


def test_multiple_rules_partial_malformed(client, db_session):
    """When two rules match but one has malformed conditions, only the valid rule fires."""
    _seed_rule(db_session, name="Bad Rule", conditions_json="{{invalid}}")
    _seed_rule(db_session, name="Good Rule", conditions_json=None)

    fired = execute_automation_rules(
        db_session,
        trigger_event="deal.stage_changed",
        context={},
        clk=_make_clock(),
    )
    assert fired == 1
