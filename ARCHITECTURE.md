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
  routers/
    health.py       — GET /health
    contacts.py     — CRUD /contacts
    deals.py        — CRUD /deals (includes stage transition endpoint)
  static/
    index.html      — Single-file kanban board + contacts table (HTML5 drag-drop, vanilla JS)
tests/
  conftest.py       — per-test in-memory SQLite engine (StaticPool), get_db override
  test_health.py
  test_no_outbound_network.py
  test_core_stages.py   — pure unit tests, no fixtures
  test_contacts.py
  test_deals.py
```

## Data Model

SQLite file `closeloop.db`. Foreign keys enforced via `PRAGMA foreign_keys = ON` at connect time.

| Table | Key columns | Notes |
|-------|-------------|-------|
| contacts | id, name, email (UNIQUE), phone, company, lead_score | M2+ |
| deals | id, title, contact_id→contacts, stage, value, probability | ON DELETE CASCADE |
| stage_transitions | id, deal_id→deals, from_stage, to_stage, occurred_at | append-only audit log |
| activities | id, deal_id, contact_id, type, subject, due_at, completed_at | M3 |
| saved_views | id, name, entity, filter_json | M4 |
| outbox | id, to_addr, subject, body, kind, status | stub boundary |
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
- Pure-logic tests (`test_core_stages.py`) need no fixtures.
- API tests use the `client` fixture; all state is isolated per test.
