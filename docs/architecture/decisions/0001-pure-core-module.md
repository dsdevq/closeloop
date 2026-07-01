---
id: "0001"
title: Pure core module (app/core/)
status: accepted
date: 2026-01-15
owner: "@dsdevq"
tags: [architecture, testing, core]
supersedes: null
superseded-by: null
---

# ADR-0001 — Pure core module (`app/core/`)

## Context

The PRD requires that verifiable business logic be pinned by a pytest suite with ≥90% coverage ([PRD §5](../../product/prd.md)). Business logic mixed with I/O (DB access, HTTP handlers) has hidden dependencies that make coverage brittle and refactors risky.

## Decision

All verifiable business logic (stage machine, forecast, lead score, filter AST, velocity, recurrence, security primitives) lives in `app/core/` as pure functions with **no I/O and no global state**. Modules under `app/core/`:

- `clock.py` — injectable clock (see ADR-0006)
- `stages.py`, `forecast.py`, `lead_score.py`, `filter_ast.py`, `velocity.py`, `recurrence.py` — pure logic
- `security.py` — password hashing + JWT primitives (pure at the crypto boundary)

## Consequences

- **Routers stay thin**: HTTP → call core function → persist → return JSON. No business logic in `app/routers/*`.
- **Pure-core tests need no fixtures** — `test_core_*.py` files import and call directly.
- **Testability is architectural**, not a side effect of good hygiene. New logic that reaches for `datetime.utcnow()` or `open()` doesn't belong in `app/core/`.

## Alternatives considered

Not documented at decision time.
