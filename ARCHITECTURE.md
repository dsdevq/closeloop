# CloseLoop — Architecture

## Overview

Self-contained CRM: Python + FastAPI + SQLite backend, vanilla HTML/CSS/JS frontend. Zero external services, zero outbound network calls, no build step.

## Layer Map

```
app/
  main.py           — FastAPI app, JSON logging middleware, router registration, static mount
  database.py       — SQLAlchemy engine, session factory, FK pragma, get_db dependency
  models.py         — ORM table definitions (all entities)
  core/
    clock.py        — Injectable clock (testable time)
    stages.py       — Pure stage state machine (no I/O)
    forecast.py     — Pure weighted_forecast / stage_forecast (no I/O)  [M3]
    lead_score.py   — Pure compute_lead_score 0–100 (no I/O)            [M3]
    filter_ast.py   — Pure filter AST: parse_filter + evaluate_filter   [M4]
  routers/
    health.py       — GET /health
    contacts.py     — CRUD /contacts (+ GET /contacts/{id}/lead-score)  [M3]
    deals.py        — CRUD /deals (includes stage transition endpoint)
    activities.py   — CRUD /activities + POST /{id}/complete            [M3]
    reminders.py    — /reminders: create, today queue, dismiss, delete  [M3]
    forecast.py     — GET /forecast                                     [M3]
    saved_views.py  — CRUD /saved-views + POST /{id}/apply              [M4]
    outbox.py       — CRUD /outbox (queue-only, no real send)           [M4]
    stats.py        — GET /stats (aggregate dashboard metrics)          [M4]
  static/
    index.html      — Single-file kanban + contacts + Today + Stats     [M4]
tests/
  conftest.py               — per-test in-memory SQLite engine (StaticPool), get_db override
  test_health.py
  test_no_outbound_network.py
  test_core_stages.py           — pure unit tests, no fixtures
  test_core_forecast.py         — pure unit tests (forecast arithmetic)      [M3]
  test_core_lead_score.py       — pure unit tests (lead score logic)         [M3]
  test_core_filter_ast.py       — pure unit tests (filter AST semantics)     [M4]
  test_contacts.py
  test_deals.py
  test_activities.py            — API tests                                  [M3]
  test_reminders.py             — API tests (incl. clock override)           [M3]
  test_forecast.py              — API tests                                  [M3]
  test_saved_views.py           — API tests (create/list/apply/delete)       [M4]
  test_outbox.py                — API tests (queue, no real network)         [M4]
  test_stats.py                 — API tests (metrics, clock override)        [M4]
```

## Data Model

SQLite file `closeloop.db`. Foreign keys enforced via `PRAGMA foreign_keys = ON` at connect time.

| Table | Key columns | Notes |
|-------|-------------|-------|
| contacts | id, name, email (UNIQUE), phone, company, lead_score | |
| deals | id, title, contact_id→contacts, stage, value, probability | ON DELETE CASCADE |
| stage_transitions | id, deal_id→deals, from_stage, to_stage, occurred_at | append-only audit log |
| activities | id, deal_id→deals (CASCADE), contact_id→contacts (SET NULL), type, title, body, due_at, completed_at, updated_at | M3 |
| reminders | id, activity_id→activities (CASCADE), remind_at, dismissed_at | M3 — Today queue |
| saved_views | id, name (UNIQUE), entity_type, filter_expr, sort_field, sort_dir | M4 |
| outbox | id, to_address, subject, body, status, deal_id→deals (SET NULL), contact_id→contacts (SET NULL) | stub boundary M4 |
| event_log | id, ts, actor, verb, entity, entity_id, meta_json | usage/audit |

Timestamps: ISO-8601 UTC strings (SQLite TEXT).

## Request Lifecycle

```
HTTP request
  → JSON logging middleware (request_id, latency)
  → FastAPI router (API routes registered before static catch-all)
  → route handler (get_db → SQLAlchemy session; get_clock → injectable clock)
  → SQLite (in-memory in tests, file in prod)
```

## Static Mount

`app.mount("/", StaticFiles(directory="app/static", html=True))` is registered **after** all API routers. FastAPI evaluates routes in registration order, so API paths win over the catch-all static mount.

## Test Design

- `conftest.py` creates a fresh `sqlite:///:memory:` engine per test function using `StaticPool` (required so `create_all` and session queries share the same in-memory database), overrides `get_db`.
- Pure-logic tests (`test_core_*.py`) need no fixtures.
- API tests use the `client` fixture; all state is isolated per test.
- Clock-dependent API tests override `get_clock` directly on `app.dependency_overrides` inside the test (with `finally:` cleanup for isolation). See `test_reminders.py`.
