---
id: "0018"
title: deal.stage (legacy string) kept for backward compat; stage_id authoritative
status: accepted
date: 2026-05-05
owner: "@dsdevq"
tags: [v2, pipeline-stages, migration]
supersedes: null
superseded-by: null
---

# ADR-0018 — `deal.stage` (legacy string) stays for backward compat; `deal.stage_id` is authoritative

## Context

v2 introduced customizable pipeline stages ([ADR-0021](0021-manager-role-manages-stages.md), [ADR-0022](0022-tests-no-auto-seed-stages.md)). Existing code paths and tests referenced `deal.stage` (a free-text string). Ripping the string field out would break every consumer at once; keeping both in sync gives a gradual migration path.

## Decision

`deal.stage` (legacy string) stays in place for backward compatibility. `deal.stage_id` is the authoritative field for the v2 kanban and the source of truth for PATCH operations. Both are kept in sync on PATCH:

- `PATCH /deals/{id}` sets `stage_id`.
- The router syncs the legacy `deal.stage` string to `PipelineStage.name` at the same moment.
- Reads that only need the string can still use `deal.stage`.

## Consequences

- Two-way sync is a maintenance surface — every mutation must update both.
- Legacy callers keep working unchanged during the v2 rollout.
- A future ADR can retire `deal.stage` once no code reads it.

## Alternatives considered

- **Drop `deal.stage` immediately** — breaks all consumers on the migration.
- **Only add `stage_id`, don't sync** — divergent state; kanban and legacy reads disagree.
