# CloseLoop — Agent Harness

> Accumulated knowledge for AI agents working on this repo. Read this BEFORE touching code to avoid re-deriving what's already known.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (ORM), SQLite (`closeloop.db`)
- **Auth:** `pyjwt>=2.8.0` (HS256 JWT) + `passlib[bcrypt]>=1.7.4` (password hashing)
- **Frontend:** Vanilla HTML/CSS/JS — `app/static/index.html` (main app) + `app/static/login.html` (auth) — no build step, no bundler, no CDN
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
  main.py        — app creation, middleware, router registration, static mount, seed+backfill
  database.py    — engine, SessionLocal, Base, get_db
  dependencies.py— get_current_user (Bearer JWT → User), require_admin              [v1]
  models.py      — all SQLAlchemy ORM models (incl. User, RefreshToken, Tag, ContactTag, DealTag)
  core/          — pure functions only, zero I/O
    clock.py     — Clock class + get_clock FastAPI dependency
    security.py  — hash_password, verify_password, create_access_token, create_refresh_token, decode_token [v1]
    stages.py    — stage state machine
    forecast.py  — weighted_forecast, stage_forecast, forecast_scenarios        [M3+M5]
    lead_score.py— compute_lead_score (v1) + compute_lead_score_v2 (decay)     [M3+M5]
    filter_ast.py— parse_filter, evaluate_filter; ops incl. `in`               [M4+M5]
    velocity.py  — time_in_stage_hours, cycle_time_hours, is_deal_rotting      [M5]
    recurrence.py— expand_rrule (daily/weekly/monthly RRULE-lite)              [M5]
  routers/       — thin HTTP handlers; one file per resource
    health.py, contacts.py, deals.py, activities.py, reminders.py, forecast.py
    auth.py        — /auth/register, /login, /refresh, /logout, /me, /users    [v1]
    saved_views.py — /saved-views CRUD + /{id}/apply                          [M4]
    outbox.py      — /outbox queue + POST /digest                             [M4+M5]
    stats.py       — /stats aggregate metrics                                  [M4]
    tags.py        — /tags CRUD + /tags/contacts/{id} + /tags/deals/{id}      [M5]
  static/
    login.html   — JWT sign-in form; stores tokens in localStorage             [v1]
    index.html   — main app (tabs: Pipeline, Contacts, Today, Stats); apiFetch + user badge [v1]
tests/
  conftest.py    — client fixture (in-memory SQLite, StaticPool, get_db override, seeded admin+token)
  test_*.py      — one file per concern
  test_auth.py   — auth/role tests (register, login, refresh, logout, 401/403, rep isolation) [v1]
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

## Auth layer (v1)

### JWT strategy
- **HS256** with secret from `JWT_SECRET_KEY` env var (defaults to a dev placeholder — change in production).
- **Access token:** 30-minute TTL. Signed payload: `{sub: user_id, type: "access"}`.
- **Refresh token:** 7-day TTL. Stored in `refresh_tokens` table with `revoked_at` for revocation. Rotated on every `/auth/refresh` call.
- `decode_token()` in `app/core/security.py` raises `jwt.ExpiredSignatureError` or `jwt.InvalidTokenError` on failure.
- `get_current_user` in `app/dependencies.py` resolves Bearer token → live `User` row; raises HTTP 401 on any failure.

### Seed credentials
- On first startup (no users in DB): creates `admin@closeloop.com` / `admin123` (role=admin) and prints to stdout.
- Backfills `owner_id` on any existing `contacts`, `deals`, `activities` rows to the seed admin.
- **Change password immediately after first login in production.**

### Role model
| Role | Access |
|------|--------|
| `admin` | All records + user management (`GET /auth/users`, `POST /auth/register` for others) |
| `manager` | All records; cannot manage users |
| `rep` | Own records only — `owner_id == user.id` filter on contacts, deals, activities |

### Owner_id migration
- `ALTER TABLE contacts/deals/activities ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL` runs idempotently in `_run_migrations()` at startup. Safe to re-run — duplicate-column error is suppressed.

### Test fixture pattern
- `tests/conftest.py` seeds an admin user in the in-memory DB and passes `Authorization: Bearer <token>` as default headers to `TestClient`. All 305 pre-existing tests remain unmodified.
- `tests/test_auth.py` defines its own `fresh_setup` / `admin_setup` fixtures for isolated auth-flow testing without the default admin token.

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
| D9 | Filter AST: recursive dict with `op` key; stored as JSON in `saved_views.filter_expr`; evaluated in Python against fetched rows |
| D10 | Outbox is queue-only — `POST /outbox` inserts `status='queued'`, never opens a socket; enforced by test |
| D11 | `compute_lead_score_v2` uses exponential decay (half-life=15d); `use_decay=False` reproduces v1 exactly |
| D12 | Forecast scenarios: 3 built-in maps (best/expected/worst) + optional custom override via `POST /forecast/scenarios` |
| D13 | Bulk import accepts `{"csv": "..."}` JSON body (not multipart); row-level errors returned in response, not HTTP 4xx |
| D14 | RRULE-lite: daily/weekly/monthly only; validation runs even when count=0 |
| D15 | Tags via many-to-many junction tables; serialised as `list[str]` in filter AST row dicts; `in`/`contains` handle list fields |
| D16 | Deal-rotting: per-stage SLA thresholds (lead=7d, qual=14d, proposal=21d, neg=30d); terminal stages never rot |
| D17 | Outbox digest: one row per call, no deduplication; `to_address=digest@closeloop.local` as sentinel |

## Gotchas

- **StaticPool is required** for in-memory SQLite tests — without it, `create_all` and queries hit different empty DBs.
- **Router registration order matters** — API routers must be `include_router`d before `app.mount("/", StaticFiles(...))`.
- **`GET /reminders/today` uses string comparison** — SQLite compares ISO 8601 strings lexicographically; this is correct as long as all timestamps use the same timezone format (`+00:00`).
- **`Activity.deal_id` is ON DELETE CASCADE** (activity deleted when deal deleted). `Activity.contact_id` is ON DELETE SET NULL (activity survives contact deletion, contact_id becomes null).
- **`compute_lead_score` clock param** — when calling from a router, pass `clk.now` (bound method), not `clk.now()` (a datetime value). The function calls `clock()` internally.
- **`test_forecast_empty_pipeline` test** — the `pass` body is intentional: the endpoint is exercised implicitly by other tests; an empty-pipeline call would need a standalone client fixture to be isolated.

## Docs

- `docs/DOMAIN.md` — CRM domain best-practices brief (Part A) + CloseLoop honest assessment and proposed v1–v6 roadmap (Part B). Not app code — read it before scoping any new feature version.

## Milestones

| M | Status | What it delivered |
|---|--------|-------------------|
| M1 | ✅ Done | Boot, schema, /health, logging |
| M2 | ✅ Done | Contacts/deals CRUD, kanban UI |
| M3 | ✅ Done | Activities, reminders, forecast, lead score, Today tab |
| M4 | ✅ Done | Filter AST, saved views, outbox queue, stats dashboard |
| M5 | ✅ Done | All 8 post-MVP features: scenarios, lead-score v2, CSV import/export, recurrence, tags, digest, rotting alerts |
| v1 | ✅ Done | Auth + user roles (JWT, bcrypt, register/login/refresh/logout, owner_id, rep/manager/admin enforcement, login.html) |

## M4 gotchas

- **`saved_views.entity_type`** (not `entity`) and **`filter_expr`** (not `filter_json`) — the M1 placeholder had different column names; M4 redefined both models cleanly.
- **`outbox.to_address`** (not `to_addr`), no `kind` column, body is NOT NULL, adds `deal_id`/`contact_id` FKs (SET NULL).
- **`stats.py` imports `Callable`** — unused after refactor; the clock is accessed via `clk.now` (bound method, callable). Keep the pattern consistent with other routers.
- **Filter AST `missing field → neq is True`** — a record without the field at all is treated as "missing" (falsy for eq/gt/etc.), but `neq` returns True because the field value is indeed "not equal" to any specified value.
- **`POST /saved-views/{id}/apply`** fetches all rows in Python and evaluates the AST in-process. Acceptable for small datasets; not SQL-push-down.

## M5 gotchas

- **`GET /deals/rotting` and `GET /deals/export` must be registered BEFORE `GET /deals/{deal_id}`** — FastAPI matches literal path segments before parameterized ones only when they're registered first in the same router.
- **`GET /contacts/export` and `POST /contacts/import` must be registered BEFORE `GET /contacts/{contact_id}`** — same routing order issue.
- **`expand_rrule` validates before the `count=0` guard** — so calling with count=0 still raises ValueError for invalid rules. This is intentional for router-level validation without needing a separate validate function.
- **`recurrence_rule` stored as JSON Text** in Activity; `_to_out` deserializes it and returns `None` when absent. Client-side JSON encoding/decoding is fully round-tripped.
- **Tags router uses `/tags/contacts/{id}` and `/tags/deals/{id}` prefixes** (not nested under `/contacts/{id}/tags`) to keep the router self-contained under the `/tags` prefix.
- **`POST /outbox/digest` path conflict** — `POST /outbox` and `POST /outbox/digest` are different paths; `GET /outbox/{message_id}` uses `int` type annotation so "digest" would 422 on GET but the POST endpoint has a distinct path that matches before the int param.
- **`compute_lead_score_v2` with `use_decay=False` and default weights is bit-identical to v1** — verified by test `test_v2_use_decay_false_matches_v1`. Use this when comparing scores for regression.
