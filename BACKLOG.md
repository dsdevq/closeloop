# CloseLoop — Backlog

> Maintained by devclaw. Status markers: `[ ]` planned · `[~]` in progress · `[x]` done. **Update this as part of every task's definition of done** — mark items, add sub-tasks discovered along the way, and note anything deferred. This is the durable "what's planned vs done" the agent reads at the start of each tick.

## MVP (build in order)

- [ ] **M1 — Skeleton & data layer.** FastAPI boots; SQLite schema + migrations; FK enforcement; `/health` (200 `{status, db, version}`); structured JSON logging middleware; seed script; **a passing `/health` smoke test** (so the verify gate is green from M1).
- [ ] **M2 — Contacts & deals CRUD + pipeline board.** REST endpoints + validation; stage transitions go through the state machine and append to `stage_transitions`; vanilla-JS drag-to-move kanban board.
- [ ] **M3 — Activities, reminders & forecast.** Activity/reminder CRUD; overdue computation; "Today" queue; weighted forecast endpoint + tile; lead score on cards.
- [ ] **M4 — Search/saved views, outbox & stats.** Filter AST evaluator + query UI; save/load named views; outbox-backed "send follow-up" (queues, never sends); in-app stats view from `event_log`.

## Iteration backlog (post-MVP)

- [ ] 1. **Stats dashboard (observability)** — `/stats` usage counters from `event_log` + per-endpoint request count / p50/p95 latency / error rate.
- [ ] 2. **Forecast scenarios & probability overrides** — tunable stage-probability map; best/expected/worst cases (extends the forecast core).
- [ ] 3. **Lead-score model v2** — temporal decay curves + configurable weights, with backtesting fixtures (deepens the core).
- [ ] 4. **Bulk import/export** — CSV in/out for contacts & deals with a row-level validation report.
- [ ] 5. **Activity recurrence** — recurring reminders via a unit-tested RRULE-lite expansion engine.
- [ ] 6. **Tags & segmentation** — many-to-many tags on contacts/deals, queryable via the filter AST.
- [ ] 7. **Outbox digest** — daily "overdue + due-today" digest composed into the outbox (still no real send).
- [ ] 8. **Deal-rotting alerts** — flag deals stagnant beyond a stage-specific SLA, derived from the velocity core.

## Done

_(nothing yet)_
