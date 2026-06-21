# CloseLoop — Backlog

## Milestone status

| Milestone | Status |
|-----------|--------|
| M1 — Skeleton & data layer | ✅ Done |
| M2 — Contacts & deals CRUD + pipeline board | ✅ Done |
| M3 — Activities, reminders & forecast | 🔲 Next |
| M4 — Search/saved views, outbox & stats | 🔲 Pending |

---

## M1 — Skeleton & data layer ✅

- [x] FastAPI app boots
- [x] SQLite schema (all tables) created on startup via `Base.metadata.create_all`
- [x] FK enforcement via `PRAGMA foreign_keys = ON`
- [x] `GET /health` — returns `{status, db, version, timestamp}`
- [x] Structured JSON logging middleware (request_id, method, path, status, latency_ms)
- [x] Injectable clock (`app/core/clock.py`)
- [x] Test: health smoke test
- [x] Test: no outbound network

---

## M2 — Contacts & deals CRUD + pipeline board ✅

- [x] `app/core/stages.py` — pure stage state machine, `validate_transition`, `stage_probability`
- [x] `app/models.py` — `lead_score` on contacts; `value`, `probability` on deals; FK CASCADE on deals/stage_transitions
- [x] `POST /contacts`, `GET /contacts`, `GET /contacts/{id}`, `PATCH /contacts/{id}`, `DELETE /contacts/{id}`
- [x] `POST /deals`, `GET /deals` (with `?stage=` filter + embedded contact name), `GET /deals/{id}`, `PATCH /deals/{id}/stage`, `PATCH /deals/{id}`, `DELETE /deals/{id}`
- [x] Stage transitions audit — row inserted on deal create and every stage move
- [x] `app/static/index.html` — kanban board (6 columns, drag-and-drop, New Deal modal, Contacts tab + New Contact modal)
- [x] `tests/test_core_stages.py` — full transition matrix, probability map, ValueError on bad stage
- [x] `tests/test_contacts.py` — CRUD coverage
- [x] `tests/test_deals.py` — CRUD, stage transitions, terminal stage rejection, embedded contact name

---

## M3 — Activities, reminders & forecast 🔲

- [ ] `POST /activities`, `GET /activities`, `PATCH /activities/{id}`, `DELETE /activities/{id}`
- [ ] Overdue / reminder computation (pure core, injected `now`) — partition into overdue / due-today / upcoming / completed
- [ ] "Today" queue endpoint
- [ ] Weighted pipeline forecast endpoint — `Σ(deal.value × stage_probability)` per open stage, total weighted + unweighted
- [ ] Lead score computation (0–100) — recency, deal amount, stage, engagement count
- [ ] Tests: reminder partition (timezone boundaries), forecast arithmetic (exact values), lead score monotonicity

---

## M4 — Search/saved views, outbox & stats 🔲

- [ ] Filter AST evaluator (AND/OR/NOT, eq/neq/gt/lt/gte/lte/contains/in) — pure core
- [ ] Saved views: `POST /saved_views`, `GET /saved_views`, `GET /saved_views/{id}`, `DELETE /saved_views/{id}`
- [ ] Outbox-backed "send follow-up" action — inserts `queued` row, never sends
- [ ] Stats view: event_log counters + per-endpoint metrics from logging middleware
- [ ] Tests: filter AST semantics, outbox stub, stats endpoint

---

## Post-MVP backlog (from PRD §6)

1. Stats dashboard — event_log + per-endpoint p50/p95 latency
2. Forecast scenarios & probability overrides (best/expected/worst)
3. Lead-score model v2 — temporal decay, configurable weights
4. Bulk import/export — CSV in/out
5. Activity recurrence — RRULE-lite expansion engine
6. Tags & segmentation — many-to-many, queryable via filter AST
7. Outbox digest — daily "overdue + due-today" composed into outbox
8. Deal-rotting alerts — stagnant deals flagged against stage SLAs
