---
id: "0009"
title: Filter AST — recursive dict grammar, JSON-serialised
status: accepted
date: 2026-02-20
owner: "@dsdevq"
tags: [filter, saved-views, ast]
supersedes: null
superseded-by: null
---

# ADR-0009 — Filter AST grammar design

## Context

Saved views need a searchable, persistable filter expression that covers CRM query needs (equality, range, substring) without a full query language or DSL. Storage is SQLite; serialisation must round-trip cleanly through JSON. Evaluation must be pure so it's independently testable.

## Decision

The filter expression is a recursive dict with an `op` key.

- **Leaf nodes** — `op ∈ {eq, neq, gt, gte, lt, lte, contains, starts_with, in}` — carry `field` and `value` keys.
- **Composite nodes** — `and`, `or` — carry a `children` list.
- **`not`** carries a `child` key.

The AST is serialised as JSON in `saved_views.filter_expr`. Pure `parse_filter` + `evaluate_filter` functions live in `app/core/filter_ast.py` (see [ADR-0001](0001-pure-core-module.md)).

## Consequences

- Saved views store raw JSON; `POST /saved-views/{id}/apply` deserialises and evaluates in Python against rows fetched from SQLite.
- Suitable for small datasets (tens–hundreds of records). A future SQL-push-down optimisation could be added; the AST → SQL mapping is straightforward.
- **Missing field → neq is True.** A record without the field is treated as "missing" (falsy for `eq`/`gt`/etc.), but `neq` returns True because the field value is indeed "not equal" to any specified value.

## Alternatives considered

- **String DSL parsed via regex or a real parser** — power we don't need; regex is fragile, real parsers are heavy.
- **Django-style Q objects** — Python-only; can't be serialised without a custom encoder.
