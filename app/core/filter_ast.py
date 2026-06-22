from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass
class CompareNode:
    field: str
    op: str  # eq | neq | gt | gte | lt | lte | contains | starts_with
    value: Any


@dataclass
class AndNode:
    children: list[FilterNode]


@dataclass
class OrNode:
    children: list[FilterNode]


@dataclass
class NotNode:
    child: FilterNode


FilterNode = Union[CompareNode, AndNode, OrNode, NotNode]

_COMPARE_OPS = {"eq", "neq", "gt", "gte", "lt", "lte", "contains", "starts_with"}


def parse_filter(expr: dict) -> FilterNode:
    """Parse a dict-based filter expression into an AST node."""
    op = expr.get("op", "").lower()
    if op == "and":
        children = [parse_filter(c) for c in expr["children"]]
        return AndNode(children=children)
    if op == "or":
        children = [parse_filter(c) for c in expr["children"]]
        return OrNode(children=children)
    if op == "not":
        return NotNode(child=parse_filter(expr["child"]))
    if op in _COMPARE_OPS:
        return CompareNode(field=expr["field"], op=op, value=expr["value"])
    raise ValueError(f"unknown filter op: {op!r}")


def evaluate_filter(node: FilterNode, record: dict) -> bool:
    """Evaluate the AST against a record dict. Missing fields are falsy."""
    if isinstance(node, AndNode):
        return all(evaluate_filter(c, record) for c in node.children)
    if isinstance(node, OrNode):
        return any(evaluate_filter(c, record) for c in node.children)
    if isinstance(node, NotNode):
        return not evaluate_filter(node.child, record)
    if isinstance(node, CompareNode):
        field_val = record.get(node.field)
        if field_val is None:
            # missing field is falsy — only neq can be true
            return node.op == "neq"
        return _compare(field_val, node.op, node.value)
    raise TypeError(f"unknown node type: {type(node)}")


def _compare(field_val: Any, op: str, value: Any) -> bool:
    if op == "eq":
        return field_val == value
    if op == "neq":
        return field_val != value
    if op == "contains":
        return str(value) in str(field_val)
    if op == "starts_with":
        return str(field_val).startswith(str(value))
    # numeric comparisons — attempt type coercion so stored strings compare correctly
    try:
        fv = float(field_val)
        v = float(value)
    except (TypeError, ValueError):
        fv = field_val
        v = value
    if op == "gt":
        return fv > v
    if op == "gte":
        return fv >= v
    if op == "lt":
        return fv < v
    if op == "lte":
        return fv <= v
    raise ValueError(f"unknown compare op: {op!r}")
