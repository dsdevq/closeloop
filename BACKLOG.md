# CloseLoop — Backlog

## Milestone status

| Milestone | Status |
|-----------|--------|
| M1 — Skeleton & data layer | ✅ Done |
| M2 — Contacts & deals CRUD + pipeline board | ✅ Done |
| M3 — Activities, reminders & forecast | ✅ Done |
| M4 — Search/saved views, outbox & stats | 🔲 Next |

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

## M3 — Activities, reminders & forecast ✅

- [x] `app/core/forecast.py` — `weighted_forecast`, `stage_forecast` (pure, no I/O)
- [x] `app/core/lead_score.py` — `compute_lead_score` 0–100 (pure, injected clock)
- [x] `app/models.py` — `Activity` updated (title, updated_at, FK CASCADE/SET NULL); `Reminder` table added
- [x] `POST /activities`, `GET /activities` (?deal_id=, ?contact_id=), `GET /activities/{id}`, `PATCH /activities/{id}`, `POST /activities/{id}/complete`, `DELETE /activities/{id}`
- [x] `POST /reminders`, `GET /reminders/today` (undismissed, remind_at ≤ now, embedded info), `PATCH /reminders/{id}/dismiss`, `DELETE /reminders/{id}`
- [x] `GET /forecast` — `{total, by_stage}` weighted pipeline over open deals
- [x] `GET /contacts/{id}/lead-score` — recomputes and persists lead_score, returns `{contact_id, lead_score}`
- [x] Frontend: "Today" tab renders Today queue with type badges + Dismiss button
- [x] Frontend: Forecast panel below kanban columns showing weighted total
- [x] `tests/test_core_forecast.py` — arithmetic, empty, terminal exclusion, stage grouping
- [x] `tests/test_core_lead_score.py` — zero score, stage bonuses, caps, injected clock window
- [x] `tests/test_activities.py` — create 201, deal_id filter, complete sets completed_at, delete 204
- [x] `tests/test_reminders.py` — create 201, today queue, dismiss, past-due appears, embedded info
- [x] `tests/test_forecast.py` — correct total, won/lost excluded, by_stage breakdown

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
