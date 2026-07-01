---
id: "0003"
title: stage_probability auto-set on transition
status: accepted
date: 2026-01-22
owner: "@dsdevq"
tags: [pipeline, forecast, audit]
supersedes: null
superseded-by: null
---

# ADR-0003 — `stage_probability` auto-set on transition

## Context

The weighted forecast reads `deal.probability`. If probability could drift freely from the deal's stage, the forecast becomes unauditable and inconsistent across deals in the same stage. The PRD ([§5](../../product/prd.md)) allows a per-deal probability override as a post-MVP feature.

## Decision

When a deal moves to a new stage via the stage endpoint, `deal.probability` is always overwritten by `stage_probability(new_stage)`. Manual probability overrides are not supported in M2.

## Consequences

- `PATCH /deals/{id}` cannot change `stage` (that lives on `/stage`). This enforces the audit trail — every stage change goes through `validate_transition` and writes a `stage_transitions` row.
- The weighted forecast is deterministic given the current stage distribution.
- Post-MVP: a per-deal override field can be added without breaking this ADR — it just requires a new field and a fallback to `stage_probability` when unset.

## Alternatives considered

Not documented at decision time.
