---
id: "0002"
title: Stage state machine — terminal blocks, backward moves permitted
status: accepted
date: 2026-01-20
owner: "@dsdevq"
tags: [pipeline, state-machine, api]
supersedes: null
superseded-by: null
---

# ADR-0002 — Stage state machine design

## Context

The PRD requires `won` and `lost` to be terminal deal stages with no resurrection. Data-entry errors need a correction path (e.g., "I marked this qualified by mistake, revert to lead") — so backward moves among *open* stages should be allowed. Unknown stage strings from typos need to fail loudly, not silently.

## Decision

`validate_transition(from_stage, to_stage) -> bool` returns `True`/`False` for valid/invalid transitions and raises `ValueError` on unknown stage strings.

- Terminal stages (`won`, `lost`) block all outgoing transitions.
- Any open stage can move to `won`, `lost`, or any other open stage (forward or backward).

## Consequences

- The `PATCH /deals/{id}/stage` endpoint returns **HTTP 422** with `{"detail": "invalid stage transition: X → Y"}` on rejected transitions.
- HTTP 422 rather than 400 aligns with FastAPI's convention for semantic validation failures.
- Callers must distinguish `ValueError` (typo) from `False` (business rule) — the router handles both.

## Alternatives considered

Not documented at decision time.
