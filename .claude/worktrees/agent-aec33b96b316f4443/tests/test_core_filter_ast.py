import pytest

from app.core.filter_ast import (
    AndNode,
    CompareNode,
    NotNode,
    OrNode,
    evaluate_filter,
    parse_filter,
)


# ── parse_filter ────────────────────────────────────────────────────────────

def test_parse_compare_eq():
    node = parse_filter({"op": "eq", "field": "stage", "value": "lead"})
    assert isinstance(node, CompareNode)
    assert node.op == "eq"
    assert node.field == "stage"
    assert node.value == "lead"


def test_parse_and():
    node = parse_filter({
        "op": "and",
        "children": [
            {"op": "eq", "field": "a", "value": 1},
            {"op": "eq", "field": "b", "value": 2},
        ],
    })
    assert isinstance(node, AndNode)
    assert len(node.children) == 2


def test_parse_or():
    node = parse_filter({
        "op": "or",
        "children": [{"op": "eq", "field": "x", "value": 1}],
    })
    assert isinstance(node, OrNode)


def test_parse_not():
    node = parse_filter({"op": "not", "child": {"op": "eq", "field": "x", "value": 1}})
    assert isinstance(node, NotNode)
    assert isinstance(node.child, CompareNode)


def test_parse_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown filter op"):
        parse_filter({"op": "between", "field": "x", "value": 1})


# ── COMPARE eq / neq ────────────────────────────────────────────────────────

def test_compare_eq_match():
    node = CompareNode(field="stage", op="eq", value="lead")
    assert evaluate_filter(node, {"stage": "lead"}) is True


def test_compare_eq_no_match():
    node = CompareNode(field="stage", op="eq", value="lead")
    assert evaluate_filter(node, {"stage": "won"}) is False


def test_compare_neq_match():
    node = CompareNode(field="stage", op="neq", value="won")
    assert evaluate_filter(node, {"stage": "lead"}) is True


def test_compare_neq_no_match():
    node = CompareNode(field="stage", op="neq", value="lead")
    assert evaluate_filter(node, {"stage": "lead"}) is False


# ── COMPARE contains / starts_with ─────────────────────────────────────────

def test_compare_contains_match():
    node = CompareNode(field="name", op="contains", value="Ali")
    assert evaluate_filter(node, {"name": "Alice"}) is True


def test_compare_contains_no_match():
    node = CompareNode(field="name", op="contains", value="Bob")
    assert evaluate_filter(node, {"name": "Alice"}) is False


def test_compare_starts_with_match():
    node = CompareNode(field="name", op="starts_with", value="Al")
    assert evaluate_filter(node, {"name": "Alice"}) is True


def test_compare_starts_with_no_match():
    node = CompareNode(field="name", op="starts_with", value="Bo")
    assert evaluate_filter(node, {"name": "Alice"}) is False


# ── COMPARE numeric: gt / gte / lt / lte ───────────────────────────────────

def test_compare_gt_match():
    node = CompareNode(field="value", op="gt", value=100)
    assert evaluate_filter(node, {"value": 200}) is True


def test_compare_gt_equal_is_false():
    node = CompareNode(field="value", op="gt", value=100)
    assert evaluate_filter(node, {"value": 100}) is False


def test_compare_gte_equal_is_true():
    node = CompareNode(field="value", op="gte", value=100)
    assert evaluate_filter(node, {"value": 100}) is True


def test_compare_lt_match():
    node = CompareNode(field="value", op="lt", value=100)
    assert evaluate_filter(node, {"value": 50}) is True


def test_compare_lt_equal_is_false():
    node = CompareNode(field="value", op="lt", value=100)
    assert evaluate_filter(node, {"value": 100}) is False


def test_compare_lte_equal_is_true():
    node = CompareNode(field="value", op="lte", value=100)
    assert evaluate_filter(node, {"value": 100}) is True


# ── AND / OR / NOT ──────────────────────────────────────────────────────────

def test_and_both_must_match():
    node = AndNode(children=[
        CompareNode(field="a", op="eq", value=1),
        CompareNode(field="b", op="eq", value=2),
    ])
    assert evaluate_filter(node, {"a": 1, "b": 2}) is True
    assert evaluate_filter(node, {"a": 1, "b": 99}) is False
    assert evaluate_filter(node, {"a": 99, "b": 2}) is False


def test_or_either_match_succeeds():
    node = OrNode(children=[
        CompareNode(field="stage", op="eq", value="lead"),
        CompareNode(field="stage", op="eq", value="won"),
    ])
    assert evaluate_filter(node, {"stage": "lead"}) is True
    assert evaluate_filter(node, {"stage": "won"}) is True
    assert evaluate_filter(node, {"stage": "lost"}) is False


def test_not_inverts():
    node = NotNode(child=CompareNode(field="stage", op="eq", value="won"))
    assert evaluate_filter(node, {"stage": "lead"}) is True
    assert evaluate_filter(node, {"stage": "won"}) is False


# ── Nesting ─────────────────────────────────────────────────────────────────

def test_nested_and_or():
    # AND( OR(stage=lead, stage=qualified), value > 500 )
    node = AndNode(children=[
        OrNode(children=[
            CompareNode(field="stage", op="eq", value="lead"),
            CompareNode(field="stage", op="eq", value="qualified"),
        ]),
        CompareNode(field="value", op="gt", value=500),
    ])
    assert evaluate_filter(node, {"stage": "lead", "value": 1000}) is True
    assert evaluate_filter(node, {"stage": "qualified", "value": 1000}) is True
    assert evaluate_filter(node, {"stage": "won", "value": 1000}) is False
    assert evaluate_filter(node, {"stage": "lead", "value": 100}) is False


# ── Missing field is falsy ──────────────────────────────────────────────────

def test_missing_field_eq_is_false():
    node = CompareNode(field="nonexistent", op="eq", value="anything")
    assert evaluate_filter(node, {}) is False


def test_missing_field_neq_is_true():
    # A record where the field is absent is indeed "not equal" to the value
    node = CompareNode(field="nonexistent", op="neq", value="anything")
    assert evaluate_filter(node, {}) is True


def test_missing_field_in_and_does_not_raise():
    node = AndNode(children=[
        CompareNode(field="missing_field", op="eq", value="x"),
    ])
    # Should return False, not raise
    assert evaluate_filter(node, {"other": "y"}) is False
