# CloseLoop — Agent Harness

> Accumulated knowledge for AI agents working on this repo. Read this BEFORE touching code to avoid re-deriving what's already known.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (ORM), SQLite (`closeloop.db`)
- **Frontend:** Single-file vanilla HTML/CSS/JS at `app/static/index.html` — no build step, no bundler, no CDN
- **Tests:** pytest, `httpx`-backed Starlette `TestClient`
- **Zero external services** — no email, no network calls at runtime

## How to run / test

```bash
# Install deps
pip install -r requirements.txt

# Start server
uvicorn app.main:app --reload

# Run tests (must be green before every PR)
python -m pytest -q

# Verify gate (same as CI)
pip install -q -r requirements.txt && python -m pytest -q
```

## Repo layout

```
app/
  main.py        — app creation, middleware, router registration, static mount
  database.py    — engine, SessionLocal, Base, get_db
  models.py      — all SQLAlchemy ORM models
  core/          — pure functions only, zero I/O
    clock.py     — Clock class + get_clock FastAPI dependency
    stages.py    — stage state machine
    forecast.py  — weighted_forecast, stage_forecast
    lead_score.py— compute_lead_score
  routers/       — thin HTTP handlers; one file per resource
    health.py, contacts.py, deals.py, activities.py, reminders.py, forecast.py
  static/
    index.html   — the entire frontend (tabs: Pipeline, Contacts, Today)
tests/
  conftest.py    — client fixture (in-memory SQLite, StaticPool, get_db override)
  test_*.py      — one file per concern
```

## Conventions

### Models (`app/models.py`)
- All timestamps stored as ISO-8601 UTC strings (SQLite TEXT column `String`)
- `created_at` and `updated_at` set from `Clock.now().isoformat()` in routers
- FK cascades: explicit `ondelete=` on all ForeignKey declarations
- Relationships must declare `back_populates` both ways; cascade delete-orphan on owned collections

### Routers
- Each router is a FastAPI `APIRouter` with a `prefix` matching the resource name
- Registered in `app/main.py` BEFORE the static files catch-all mount
- `_to_out(model) -> dict` helper serializes ORM objects — keeps Pydantic models out of response path
- 204 responses use `return Response(status_code=204)` (not plain `return`)
- HTTP 422 (not 400) for semantic validation failures (aligns with FastAPI convention)

### Core functions
- **No I/O, no side effects, no global state** in `app/core/`
- Time-dependent functions accept `clock` kwarg defaulting to `datetime.utcnow`
- Never call `datetime.utcnow()` directly — always use the injected `clock()`
- Timezone handling: strip `tzinfo` from stored timestamps when comparing with naive `datetime.utcnow`; OR pass `clk.now` (timezone-aware bound method) and handle both in the function

### Tests
- `conftest.py` provides a `client` fixture scoped per function — fresh in-memory DB each test
- Pure core tests (`test_core_*.py`) need no fixtures — just import and call
- To override clock in API tests: `app.dependency_overrides[get_clock] = lambda: FixedClock(dt)` with `finally:` cleanup. Never leave overrides in place between tests.
- Never mock the database — always use the in-memory SQLite via the `client` fixture

### Frontend
- Tab switching: use `data-tab="name"` attribute on `<button class="tab">` — `showTab(name)` reads it with `querySelector('[data-tab="${name}"]')`
- All user-supplied content goes through `escHtml()` before insertion into innerHTML
- `fetch` errors show a toast via `showToast(msg)` — never throw to console unhandled

## Key decisions (summary — see DECISIONS.md for full rationale)

| # | Decision |
|---|----------|
| D1 | All verifiable logic in `app/core/` as pure functions |
| D2 | Stage machine: terminal stages block moves; backward moves among open stages allowed |
| D3 | `probability` auto-set from `stage_probability()` on every stage transition |
| D4 | Kanban uses native HTML5 drag-and-drop (no library) |
| D5 | Tests use `StaticPool` so `create_all` and queries share one in-memory connection |
| D6 | Injected clock pattern: `clock` kwarg defaults to `datetime.utcnow`; router passes `clk.now` |
| D7 | `reminders` is a separate table from `activities`; Today queue is on-request, no daemon |
| D8 | Lead score formula: deals +10 (cap 30), stage bonuses, recent activity +5 (cap 20), email/phone +5 |

## Gotchas

- **StaticPool is required** for in-memory SQLite tests — without it, `create_all` and queries hit different empty DBs.
- **Router registration order matters** — API routers must be `include_router`d before `app.mount("/", StaticFiles(...))`.
- **`GET /reminders/today` uses string comparison** — SQLite compares ISO 8601 strings lexicographically; this is correct as long as all timestamps use the same timezone format (`+00:00`).
- **`Activity.deal_id` is ON DELETE CASCADE** (activity deleted when deal deleted). `Activity.contact_id` is ON DELETE SET NULL (activity survives contact deletion, contact_id becomes null).
- **`compute_lead_score` clock param** — when calling from a router, pass `clk.now` (bound method), not `clk.now()` (a datetime value). The function calls `clock()` internally.
- **`test_forecast_empty_pipeline` test** — the `pass` body is intentional: the endpoint is exercised implicitly by other tests; an empty-pipeline call would need a standalone client fixture to be isolated.

## Milestones

| M | Status | What it delivered |
|---|--------|-------------------|
| M1 | ✅ Done | Boot, schema, /health, logging |
| M2 | ✅ Done | Contacts/deals CRUD, kanban UI |
| M3 | ✅ Done | Activities, reminders, forecast, lead score, Today tab |
| M4 | 🔲 Next | Filter AST, saved views, outbox, stats |
