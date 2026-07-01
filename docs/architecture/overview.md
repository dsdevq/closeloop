---
title: Architecture overview
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [architecture, layer-map, data-model]
---

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
    forecast.py     — Pure weighted_forecast / stage_forecast / forecast_scenarios [M3+Post]
    lead_score.py   — compute_lead_score v1 + compute_lead_score_v2 (decay)  [M3+Post]
    filter_ast.py   — Pure filter AST: parse_filter + evaluate_filter; ops incl. `in` [M4+Post]
    velocity.py     — time_in_stage_hours, cycle_time_hours, avg_days_per_stage, is_deal_rotting [Post]
    recurrence.py   — RRULE-lite expand_rrule (daily/weekly/monthly)          [Post]
  routers/
    health.py       — GET /health
    contacts.py     — CRUD /contacts (+ lead-score, CSV export/import)        [M3+Post]
    deals.py        — CRUD /deals (stage transition, CSV export/import, rotting) [Post]
    activities.py   — CRUD /activities + complete + expand (recurrence)       [M3+Post]
    reminders.py    — /reminders: create, today queue, dismiss, delete        [M3]
    forecast.py     — GET /forecast + POST /forecast/scenarios                [M3+Post]
    saved_views.py  — CRUD /saved-views + POST /{id}/apply                   [M4]
    outbox.py       — CRUD /outbox (queue-only) + POST /outbox/digest        [M4+Post]
    stats.py        — GET /stats (aggregate dashboard metrics)               [M4]
    tags.py         — CRUD /tags + /tags/contacts/{id} + /tags/deals/{id}    [Post]
  static/
    index.html      — Single-file kanban + contacts + Today + Stats           [M4]
tests/
  conftest.py               — per-test in-memory SQLite engine (StaticPool), get_db override
  test_health.py
  test_no_outbound_network.py
  test_core_stages.py           — pure unit tests, no fixtures
  test_core_forecast.py         — forecast arithmetic + scenarios/overrides       [M3+Post]
  test_core_lead_score.py       — lead score v1 + v2 decay + configurable weights [M3+Post]
  test_core_filter_ast.py       — filter AST semantics + `in` op                 [M4+Post]
  test_core_velocity.py         — stage timing, cycle time, rotting detection     [Post]
  test_core_recurrence.py       — RRULE-lite expand_rrule                         [Post]
  test_contacts.py
  test_deals.py                 — CRUD, transitions, rotting alerts                [Post]
  test_activities.py            — API tests + recurrence expand                   [M3+Post]
  test_reminders.py             — API tests (incl. clock override)                [M3]
  test_forecast.py              — API tests + scenarios endpoint                  [M3+Post]
  test_saved_views.py           — API tests (create/list/apply/delete)            [M4]
  test_outbox.py                — API tests (queue, digest, no real network)      [M4+Post]
  test_stats.py                 — API tests (metrics, clock override)             [M4]
  test_bulk.py                  — CSV import/export for contacts & deals          [Post]
  test_tags.py                  — tags CRUD, contact/deal associations, filter    [Post]
```

## Data Model

SQLite file `closeloop.db`. Foreign keys enforced via `PRAGMA foreign_keys = ON` at connect time.

| Table | Key columns | Notes |
|-------|-------------|-------|
| contacts | id, name, email (UNIQUE), phone, company, lead_score | |
| deals | id, title, contact_id→contacts, stage, value, probability | ON DELETE CASCADE |
| stage_transitions | id, deal_id→deals, from_stage, to_stage, occurred_at | append-only audit log |
| activities | id, deal_id→deals (CASCADE), contact_id→contacts (SET NULL), type, title, body, due_at, completed_at, recurrence_rule (JSON), updated_at | M3+Post |
| reminders | id, activity_id→activities (CASCADE), remind_at, dismissed_at | M3 — Today queue |
| saved_views | id, name (UNIQUE), entity_type, filter_expr, sort_field, sort_dir | M4 |
| outbox | id, to_address, subject, body, status, deal_id→deals (SET NULL), contact_id→contacts (SET NULL) | stub boundary M4 |
| event_log | id, ts, actor, verb, entity, entity_id, meta_json | usage/audit |
| tags | id, name (UNIQUE), created_at | Post-MVP |
| contact_tags | contact_id→contacts (CASCADE), tag_id→tags (CASCADE) | composite PK, many-to-many |
| deal_tags | deal_id→deals (CASCADE), tag_id→tags (CASCADE) | composite PK, many-to-many |

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
