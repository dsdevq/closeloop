---
id: "0015"
title: Tags — many-to-many junction tables, filter via list ops
status: accepted
date: 2026-03-28
owner: "@dsdevq"
tags: [tags, data-model, filter]
supersedes: null
superseded-by: null
---

# ADR-0015 — Tags use many-to-many junction tables; filter via `contains`/`in` on serialized list

## Context

Tags need to be reusable across contacts and deals, renameable in one place, and filterable via the existing filter AST ([ADR-0009](0009-filter-ast-grammar.md)) without a special case. A denormalised text column of comma-separated tags would break both goals.

## Decision

- `Tag` is a first-class table.
- `ContactTag` and `DealTag` are junction tables with composite primary keys.
- When evaluating filter AST against contacts/deals, tags are serialised as a `list[str]` of tag names in the row dict.
- The `contains` op checks list membership for list fields.
- The `in` op (added to the AST for this) checks if a list-valued field contains a scalar value.

## Consequences

- Rename a tag in one place — all references follow.
- Filter AST handles tag queries without a special case: `{"op": "contains", "field": "tags", "value": "vip"}` Just Works.
- `SavedView.apply` fetches all rows in Python; tags are included in `_contact_to_dict`/`_deal_to_dict` when those serialisers are updated.
- The `in` op (PRD [§5](../../product/prd.md) — was missing from M4) is now implemented and pinned by tests.

## Alternatives considered

- **Comma-separated column** — dead-end for rename; no referential integrity.
- **JSON array column** — better than CSV but still no rename support and worse filter ergonomics.
