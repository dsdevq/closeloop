---
title: Architecture Decision Records — index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [architecture, adr, meta]
---

# ADRs

Every non-trivial design decision made in CloseLoop, one file per decision, numbered sequentially, immutable once accepted. Process in [README.md](README.md); template in [`../../_templates/adr.md`](../../_templates/adr.md).

## Accepted (current)

| # | Title | Tags |
|---|---|---|
| [0001](0001-pure-core-module.md) | Pure core module (`app/core/`) | architecture, testing, core |
| [0002](0002-stage-state-machine.md) | Stage state machine — terminal blocks, backward moves permitted | pipeline, state-machine |
| [0003](0003-stage-probability-auto-set.md) | `stage_probability` auto-set on transition | pipeline, forecast |
| [0005](0005-static-pool-test-engine.md) | `StaticPool` for in-memory SQLite test engine | testing, sqlite |
| [0006](0006-injected-clock.md) | Injected clock for time-dependent logic | testing, core |
| [0007](0007-reminders-separate-table.md) | Reminders as a separate table from activities | data-model, reminders |
| [0009](0009-filter-ast-grammar.md) | Filter AST — recursive dict grammar | filter, saved-views |
| [0010](0010-outbox-queue-only.md) | Outbox is a queue-only stub boundary | outbox, network-boundary |
| [0011](0011-lead-score-v2-decay.md) | Lead-score v2 — exponential decay | lead-score, formula |
| [0012](0012-forecast-scenarios-fixed-maps.md) | Forecast scenarios — fixed built-in probability maps | forecast, scenarios |
| [0013](0013-bulk-import-json-body.md) | Bulk import — JSON body, not multipart | bulk-import, api |
| [0014](0014-rrule-lite.md) | RRULE-lite — daily/weekly/monthly, eager validation | recurrence |
| [0015](0015-tags-junction-tables.md) | Tags — many-to-many junction tables | tags, data-model |
| [0016](0016-deal-rotting-per-stage-sla.md) | Deal-rotting — per-stage SLA thresholds | deals, velocity |
| [0017](0017-outbox-digest-no-dedupe.md) | Outbox digest — single queued row per call | outbox, digest |
| [0018](0018-deal-stage-backward-compat.md) | `deal.stage` (legacy string) kept for backward compat | v2, migration |
| [0019](0019-stage-probability-int-storage.md) | Pipeline stage probability stored as 0–100 int | v2, probability |
| [0020](0020-stage-delete-409-conflict.md) | Stage DELETE returns 409 when deals exist | v2, api |
| [0021](0021-manager-role-manages-stages.md) | Manager role can manage pipeline stages | v2, auth, roles |
| [0022](0022-tests-no-auto-seed-stages.md) | Tests do not auto-seed pipeline stages | v2, testing |
| [0023](0023-insights-python-side-aggregation.md) | Insights aggregation computed in pure Python, not SQL | insights, architecture, core, testing |
| [0024](0024-insights-svg-chart-primitives.md) | Insights charts are hand-rolled SVG primitives, no charting library | insights, frontend, charts, dependencies |
| [0025](0025-notifications-pull-model.md) | Notifications engine — typed event model and pull-based retrieval | notifications, data-model, api, architecture |
| [0026](0026-history-save-triggered-capture.md) | Activity timeline — save-triggered audit history capture | history, audit, data-model, api, architecture |
| [0027](0027-singleton-container-swap-cicd.md) | CI/CD — multi-stage Dockerfile, singleton container swap, test-inside-container gate | ci, docker, deploy, architecture |

## Superseded (historical)

| # | Title | Superseded by |
|---|---|---|
| [0004](0004-html5-drag-and-drop.md) | HTML5 drag-and-drop for kanban (no library) | Frontend framework choice reversed 2026-06 — see [../../guides/frontend.md](../../guides/frontend.md); this ADR's *decision* (avoid a drag library) still holds inside React |
| [0008](0008-lead-score-formula.md) | Lead score formula (v1) | [0011](0011-lead-score-v2-decay.md) |
