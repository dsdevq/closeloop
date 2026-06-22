# CloseLoop — Backlog

## Milestone status

| Milestone | Status |
|-----------|--------|
| M1 — Skeleton & data layer | ✅ Done |
| M2 — Contacts & deals CRUD + pipeline board | ✅ Done |
| M3 — Activities, reminders & forecast | ✅ Done |
| M4 — Search/saved views, outbox & stats | ✅ Done |

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

## M4 — Search/saved views, outbox & stats ✅

- [x] `app/core/filter_ast.py` — `parse_filter` + `evaluate_filter` (pure, no I/O); nodes: AND/OR/NOT/COMPARE; ops: eq/neq/gt/gte/lt/lte/contains/starts_with
- [x] `saved_views` table: name UNIQUE, entity_type, filter_expr (JSON AST), sort_field, sort_dir, timestamps
- [x] `outbox` table: to_address, subject, body NOT NULL, status, deal_id/contact_id FKs (SET NULL)
- [x] `POST /saved-views`, `GET /saved-views`, `GET /saved-views/{id}`, `POST /saved-views/{id}/apply`, `DELETE /saved-views/{id}`
- [x] `POST /outbox` (queue only, no real send), `GET /outbox` (?status= filter), `GET /outbox/{id}`, `DELETE /outbox/{id}`
- [x] `GET /stats` — total_contacts/deals/activities, deals_by_stage, pipeline_value, weighted_forecast, activities_last_30_days, outbox_queued; injected clock
- [x] Frontend: Stats tab with metric cards + deals-by-stage breakdown; Saved Views panel in Pipeline and Contacts tabs
- [x] `tests/test_core_filter_ast.py` — 20+ cases covering all ops, nesting, missing-field handling
- [x] `tests/test_saved_views.py` — create/list/get/apply/delete with AND filter and filter-against-seeded-records
- [x] `tests/test_outbox.py` — queue, list, status filter, delete, no-network assertion
- [x] `tests/test_stats.py` — all keys, deals_by_stage, weighted_forecast excludes terminal, clock override for 30d window

---

## Post-MVP backlog (from PRD §6) — M5 delivery

| # | Feature | Status |
|---|---------|--------|
| 1 | Stats dashboard (observability) — `/stats` endpoint | ✅ Done (M4) |
| 2 | Forecast scenarios & probability overrides | ✅ Done (M5) |
| 3 | Lead-score model v2 — temporal decay + configurable weights | ✅ Done (M5) |
| 4 | Bulk import/export — CSV in/out for contacts & deals | ✅ Done (M5) |
| 5 | Activity recurrence — RRULE-lite expansion engine | ✅ Done (M5) |
| 6 | Tags & segmentation — many-to-many, queryable via filter AST | ✅ Done (M5) |
| 7 | Outbox digest — daily "overdue + due-today" composed into outbox | ✅ Done (M5) |
| 8 | Deal-rotting alerts — stagnant deals flagged against stage SLAs | ✅ Done (M5) |

**All 8 post-MVP features delivered. Done-when condition: 6-of-8 satisfied (8 of 8 delivered).**

---

## M5 — Post-MVP iteration ✅

- [x] `app/core/forecast.py` — `weighted_forecast_with_overrides`, `forecast_scenarios` (best/expected/worst + custom map)
- [x] `POST /forecast/scenarios` — returns all scenarios; accepts optional `probability_overrides`
- [x] `app/core/lead_score.py` — `compute_lead_score_v2` with exponential temporal decay and configurable weights
- [x] `GET /contacts/export` — CSV download of all contacts
- [x] `POST /contacts/import` — CSV bulk import with row-level validation report
- [x] `GET /deals/export` — CSV download of all deals
- [x] `POST /deals/import` — CSV bulk import with row-level validation report
- [x] `app/core/recurrence.py` — RRULE-lite `expand_rrule` (daily/weekly/monthly, configurable interval)
- [x] `Activity.recurrence_rule` column (JSON, nullable) added to model
- [x] `POST /activities/{id}/expand` — generates N future occurrences from a recurring activity
- [x] `Tag`, `ContactTag`, `DealTag` models (many-to-many junction tables)
- [x] `/tags` CRUD — create/list/get/delete tags
- [x] `/tags/contacts/{id}` — add/list/remove tags on contacts
- [x] `/tags/deals/{id}` — add/list/remove tags on deals
- [x] `filter_ast.py` — `in` operator added (was missing from M4 despite being in PRD §5)
- [x] `filter_ast.py` — `contains` op updated to handle list fields (tag membership)
- [x] `POST /outbox/digest` — compose overdue+due-today reminders into one queued outbox row
- [x] `app/core/velocity.py` — `time_in_stage_hours`, `cycle_time_hours`, `avg_days_per_stage`, `is_deal_rotting`, `stage_sla_days`
- [x] `GET /deals/rotting` — open deals stagnant beyond stage SLA; includes `days_in_stage`, `sla_days`, `is_rotting`
- [x] Tests: `test_core_velocity.py`, `test_core_recurrence.py`, `test_bulk.py`, `test_tags.py`
- [x] Tests: extended `test_core_forecast.py`, `test_core_lead_score.py`, `test_core_filter_ast.py`
- [x] Tests: extended `test_forecast.py`, `test_deals.py`, `test_activities.py`, `test_outbox.py`
- [x] Decisions D11–D17 documented
