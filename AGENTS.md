# CloseLoop — Agent Harness

> Accumulated knowledge for AI agents working on this repo. Read this BEFORE touching code to avoid re-deriving what's already known.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (ORM), SQLite (`closeloop.db`)
- **Auth:** `pyjwt>=2.8.0` (HS256 JWT) + `bcrypt>=4.0.0` (password hashing)
- **Frontend:** React + Vite + TypeScript + Tailwind in `frontend/`; production build emits static assets to `app/static/`
- **Tests:** pytest, `httpx`-backed Starlette `TestClient`
- **Zero external services** — no email, no network calls at runtime

## How to run / test

```bash
# Install deps
pip install -r requirements.txt

# Build frontend
npm --prefix frontend install --include=dev
npm run build

# Start server (local)
uvicorn app.main:app --reload

# Start server (preview/container — bind all interfaces)
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Run Python unit tests only
python -m pytest -q

# Run Playwright e2e tests only (FastAPI auto-starts on port 8088 via webServer config)
npx playwright test --reporter=list

# Full verify gate — BOTH must be green before every PR
bash scripts/verify.sh   # auto-handles ARM64 no-root workaround
# or: make verify  (delegates to the same script)
```

### E2E / Playwright tests

```bash
# Install Playwright (one-time per environment)
npm install                          # installs @playwright/test at root
npx playwright install --with-deps chromium   # downloads Chromium + system deps (needs sudo)

# ARM64 / no-root workaround (libXfixes.so.3 missing, can't sudo):
#   1. Extract lib from .deb without root:
#      curl -fsSL http://deb.debian.org/debian/pool/main/libx/libxfixes/libxfixes3_6.0.0-2+b5_arm64.deb \
#           -o /tmp/lxf.deb && dpkg-deb -x /tmp/lxf.deb /tmp/lxf && mkdir -p ~/lib && cp /tmp/lxf/usr/lib/*/libXfixes.so.3* ~/lib/
#   2. Install Chromium skipping host validation:
#      PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright install chromium
#   playwright.config.ts prepends ~/lib to LD_LIBRARY_PATH automatically.

# Run the suite (server auto-starts on port 8088 via webServer config; set E2E_PORT to override)
npx playwright test --reporter=list

# Credentials: TEST_USER / TEST_PASS env vars (default: admin@closeloop.com / admin123)
# Note: port 8000 may be occupied by a harness stub in some CI environments;
#       the config uses E2E_PORT=8088 to avoid the conflict.
```

**E2E test results (verified 2026-06-29): 52 passed / 0 failed / 5 fixme-skipped** (57 total)

The 5 `test.fixme` items remain as skipped defect markers for UI gaps:
- `contacts.spec.ts`: contact detail/edit UI [UI gap], import UI trigger [UI gap], export UI trigger [UI gap]
- `pipeline.spec.ts`: deal detail/edit UI [UI gap]
- `activities.spec.ts`: Activities navigation tab [UI gap]

> **ARM64 pipe gotcha** — `playwright.config.ts` uses `stdout: 'ignore', stderr: 'ignore'` for the
> webServer. On ARM64 Linux the OS pipe buffer (~64 KB) fills after ~10 tests when set to `'pipe'`,
> blocking uvicorn's logging writes and causing subsequent tests to get ERR_CONNECTION_REFUSED.
> Do NOT change these back to `'pipe'`.

| # | Status | Test | Note |
|---|--------|------|------|
| 1 | `test.fixme` | Contacts CRUD › contact detail/edit UI [UI gap] | In contacts.spec.ts; full CRUD covered by 'contacts - detail' |
| 2 | ✅ Fixed | Deals CRUD › create deal via modal — appears on kanban | `POST /deals` now sets `stage_id` to first pipeline stage |
| 3 | `test.fixme` | Deals CRUD › deal detail/edit UI [UI gap] | In pipeline.spec.ts; full CRUD covered by 'deals - detail' |
| 4 | ✅ Done | Accounts CRUD › edit account | AccountEditModal implemented; Edit button in detail header opens modal (name, notes, address fields; diff-only PATCH); note: `notes` is frontend-only until backend adds the column |
| 5 | `test.fixme` | Activities CRUD › Activities nav tab [UI gap] | ✅ Activities tab added to SPA; activities.spec.ts covers it |
| 6 | `test.fixme` | Import › import UI trigger [UI gap] | ✅ Import CSV button added; contacts.spec.ts covers it |
| 7 | `test.fixme` | Export › export UI trigger [UI gap] | ✅ Export CSV button added; contacts.spec.ts covers it |

## Repo layout

```
app/
  main.py        — app creation, middleware, router registration, static mount, seed+backfill
  database.py    — engine, SessionLocal, Base, get_db
  dependencies.py— get_current_user (Bearer JWT → User), require_admin              [v1]
  models.py      — all SQLAlchemy ORM models (incl. User, RefreshToken, Tag, ContactTag, DealTag,
                   Account, PipelineStage)                                           [v2]
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
    accounts.py    — /accounts CRUD; rep sees own, manager/admin see all       [v2]
    pipeline.py    — /pipeline/stages CRUD; write is admin/manager only        [v2]
  static/
    index.html   — generated React SPA entry served at `/`
    login.html   — generated React SPA entry copy served at `/login.html`
    assets/      — generated Vite JS/CSS bundles
frontend/
  src/types.ts   — all shared TypeScript domain types (User, Contact, Deal, Account, Activity, SavedView, Reminder, PipelineStage, Tag, …)
  src/lib/
    api.ts       — apiFetch (auth-aware fetch; 401 clears tokens → /login.html), getToken, storedUser
    formatters.ts— money, numberText display formatters (no React/DOM dependency)
  src/components/
    AppHeader.tsx— sticky nav header (tab switcher + user info + logout)
    AppModals.tsx— all modal rendering (deal/contact/account/activity/import)
    ui/          — shared presentational primitives (TextField, ModalShell, ModalActions, SectionHeader, SavedViewsBar)
  src/features/
    pipeline/    — kanban board (PipelineView, DealCard, DealDetailView, DealModal, DealEditModal)
    contacts/    — contacts list + detail + CSV import/export (ContactsView, ContactDetailView, ContactModal, ContactEditModal, ImportModal)
    accounts/    — accounts list + detail (AccountsView, AccountDetailView, AccountModal)
    activities/  — activities list + detail (ActivitiesView, ActivityDetailView, ActivityFormModal; ActivityFormModal owns `ACTIVITY_TYPES` const)
    today/       — reminders queue with dismiss (TodayView)
    stats/       — aggregate metrics dashboard (StatsView)
    auth/        — login form (LoginView)
  src/hooks/
    useAuth.ts      — token/user state, handleLogin, logout, login-redirect effect
    useDeals.ts     — deals state + CRUD (createDeal, updateDeal, deleteDeal, moveDeal, loadDeals)
    useContacts.ts  — contacts state + CRUD (createContact, updateContact, deleteContact, loadContacts, exportContacts)
    useAccounts.ts  — accounts state + CRUD (createAccount, deleteAccount, loadAccounts); account-detail effect
    useActivities.ts— activities state + CRUD (createActivity, updateActivity, deleteActivity, loadActivities)
    useAppState.ts  — composition hook: calls the five above, owns remaining app-level state (activeTab, stages, today, savedViews, stats, modal, toast, loading) and orchestrates refreshCore + effects
  src/App.tsx    — React CRM app entry: hook call + render tree only (≤175 lines)
  src/styles.css — Tailwind base/components/utilities
  vite.config.ts — builds into `app/static/`; dev proxy targets FastAPI on :8000
tests/
  conftest.py    — client fixture (in-memory SQLite, StaticPool, get_db override, seeded admin+token)
  test_*.py      — one file per concern
e2e/
  auth.spec.ts        — Basic load, Auth (login/logout/guard), Route coverage, Auth flow (10 tests)
  pipeline.spec.ts    — Pipeline nav, Deals CRUD smoke+FC, drag-and-drop, per-stage Add Deal (12 tests)
  contacts.spec.ts    — Contacts nav, Contacts CRUD smoke+FC, Import/Export, saved-view Apply/Clear (19 tests)
  accounts.spec.ts    — Accounts nav, Accounts CRUD smoke+FC (6 tests)
  activities.spec.ts  — Activities CRUD smoke+FC (7 tests; 1 fixme: Activities nav [UI gap])
  stats.spec.ts       — Stats nav (1 test)
  today.spec.ts       — Today nav, reminder Dismiss (2 tests)
  tsconfig.json       — TypeScript config for e2e tests
  fixtures/
    contacts.csv — sample CSV for manual/automated import testing
playwright.config.ts  — Playwright config (Chromium headless, port 8088, webServer auto-start)
  test_auth.py   — auth/role tests (register, login, refresh, logout, 401/403, rep isolation) [v1]
  test_accounts.py  — account CRUD, contact-account linking, role enforcement  [v2]
  test_pipeline.py  — pipeline stage CRUD, deal stage_id PATCH, 409 on delete  [v2]
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

- Source of truth is `frontend/src`, not generated files under `app/static`.
- Run `npm --prefix frontend run typecheck`, `npm --prefix frontend run lint`, and `npm --prefix frontend run build` before frontend PRs.
- The build script copies `app/static/index.html` to `app/static/login.html` so FastAPI serves the same React auth-aware SPA at both routes.
- Use typed React state and normal JSX escaping. Avoid `dangerouslySetInnerHTML` for user-supplied data.

#### Key files and directories

- **`frontend/src/types.ts`** — all shared TypeScript domain types (`User`, `Contact`, `Deal`, `Account`, `Activity`, `SavedView`, `Reminder`, `PipelineStage`, `Tag`, …). Every feature module imports types from here; no type definitions live in component files.
- **`frontend/src/lib/api.ts`** — `apiFetch` (auth-aware fetch; 401 clears tokens → `/login.html`), `getToken`, `storedUser`. All API calls go through `apiFetch` so auth errors are handled consistently across features.
- **`frontend/src/lib/formatters.ts`** — `money` and `numberText` display formatters. No React or DOM dependency; safe to call in any context.
- **`frontend/src/components/ui/`** — shared presentational primitives; each file exports one named export matching the filename:
  - `TextField` — labelled text input
  - `ModalShell` — modal overlay and card wrapper
  - `ModalActions` — modal footer button row (Cancel / primary action)
  - `SectionHeader` — page section title bar with optional action button
  - `SavedViewsBar` — saved-view chips + apply/clear controls; imports `SavedView` from `../../types`, no internal `apiFetch` call
- **`frontend/src/features/`** — one subdirectory per product area; each file exports one named export matching the filename; imports only from `../../types`, `../../lib/*`, and `../../components/ui/*`:
  - `pipeline/` — kanban board with drag-and-drop stage moves (`PipelineView`, `DealCard`, `DealDetailView`, `DealModal`, `DealEditModal`; `PipelineView` owns `stagePalette`)
  - `contacts/` — contacts list + detail + CSV import/export (`ContactsView`, `ContactDetailView`, `ContactModal`, `ContactEditModal`, `ImportModal`)
  - `accounts/` — accounts list + detail + create/edit modals (`AccountsView`, `AccountDetailView`, `AccountModal`, `AccountEditModal`)
  - `activities/` — activities list + detail (`ActivitiesView`, `ActivityDetailView`, `ActivityFormModal`; `ActivityFormModal` owns `ACTIVITY_TYPES` const)
  - `today/` — reminders queue with dismiss action (`TodayView`)
  - `stats/` — aggregate metrics dashboard (`StatsView`)
  - `auth/` — login form with no hardcoded credential defaults (`LoginView`)
- **`frontend/src/components/AppHeader.tsx`** — sticky nav bar (tab switcher + user info + logout); app-level, not a UI primitive.
- **`frontend/src/components/AppModals.tsx`** — renders all modals; driven by state from `useAppState`.
- **`frontend/src/hooks/useAppState.ts`** — the only custom hook; owns all `useState`, `useCallback`, `useEffect`, and async CRUD actions. `App.tsx` calls this hook then renders the layout tree.

#### E2E spec layout (`e2e/`)

One spec file per feature area; each is self-contained with its own setup/teardown:

- `auth.spec.ts` — basic SPA load, login/logout/guard, route coverage (10 tests)
- `pipeline.spec.ts` — Pipeline nav, Deals CRUD, drag-and-drop, per-stage Add Deal (12 tests)
- `contacts.spec.ts` — Contacts nav, Contacts CRUD, Import/Export, saved-view Apply/Clear (19 tests)
- `accounts.spec.ts` — Accounts nav, Accounts CRUD (6 tests)
- `activities.spec.ts` — Activities CRUD (7 tests; 1 fixme: Activities nav [UI gap])
- `stats.spec.ts` — Stats nav (1 test)
- `today.spec.ts` — Today nav, reminder Dismiss (2 tests)

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
| v2 | ✅ Done | Accounts/Companies layer + Customizable Pipeline Stages (see below) |

## M4 gotchas

- **`saved_views.entity_type`** (not `entity`) and **`filter_expr`** (not `filter_json`) — the M1 placeholder had different column names; M4 redefined both models cleanly.
- **`outbox.to_address`** (not `to_addr`), no `kind` column, body is NOT NULL, adds `deal_id`/`contact_id` FKs (SET NULL).
- **`stats.py` imports `Callable`** — unused after refactor; the clock is accessed via `clk.now` (bound method, callable). Keep the pattern consistent with other routers.
- **Filter AST `missing field → neq is True`** — a record without the field at all is treated as "missing" (falsy for eq/gt/etc.), but `neq` returns True because the field value is indeed "not equal" to any specified value.
- **`POST /saved-views/{id}/apply`** fetches all rows in Python and evaluates the AST in-process. Acceptable for small datasets; not SQL-push-down.

## v2 — Accounts + Pipeline Stages

### New models
- **Account** (`accounts` table) — id, name, domain, industry, website, phone, address, owner_id FK→users, created_at, updated_at. Rep sees own; manager/admin see all.
- **PipelineStage** (`pipeline_stages` table) — id, name, position (ordering), probability (0–100 int), is_default (bool as int), created_at. 6 default stages seeded at startup if table is empty.
- **Contact.account_id** — nullable FK→accounts (SET NULL on delete). Allows a contact to belong to a company.
- **Deal.stage_id** — nullable FK→pipeline_stages (SET NULL on delete). Replaces the legacy free-text `stage` field for kanban placement; `stage` (string) kept for backward compat.
- **Deal.probability** — existing float field (0.0–1.0). Inherited from `PipelineStage.probability / 100` on stage_id change, but overridable per deal.

### New routes
- `GET/POST/PATCH/DELETE /accounts` — account CRUD; rep scope = own.
- `GET /pipeline/stages` — list all stages ordered by position; auth required.
- `POST/PATCH/DELETE /pipeline/stages/{id}` — admin or manager only; DELETE returns 409 if deals reference that stage (with count in detail).
- `PATCH /deals/{id}` — extended to accept `stage_id` and/or `probability`; sets `stage_id`, syncs legacy `stage` field to `PipelineStage.name`, auto-inherits probability unless overridden.

### Migration notes
- `_run_migrations()` in main.py runs idempotent `ALTER TABLE` to add `account_id` to contacts and `stage_id` to deals.
- `_seed_pipeline_stages()` seeds 6 default stages and then backfills `deal.stage_id` from legacy `deal.stage` string via `_STAGE_NAME_MAP`.
- In tests, `conftest.py` does NOT call lifespan (and therefore does NOT seed pipeline stages). Tests that need stages must insert them directly via the API or `PipelineStage` model.

### Frontend (React v2.2)
- React SPA tabs: Pipeline, Contacts, Accounts, **Activities** (new), Today, Stats.
- **Activities tab**: full CRUD list view — click activity title to open ActivityDetailView (back/edit/delete), New Activity modal with type/contact/notes fields.
- **Contacts**: name is now a clickable button → ContactDetailView (back/edit/delete). Edit modal patches name/email/phone/company. **Import CSV** and **Export CSV** buttons added to section header.
  - Import: reads file client-side with FileReader, POSTs JSON `{"csv": "..."}` to `/contacts/import`, shows result modal.
  - Export: fetches `/contacts/export` with auth, converts to blob, triggers browser download via `<a download>` click.
- **Pipeline**: DealCard is clickable → DealDetailView (back/edit/delete). Edit modal patches title/value.
- Accounts tab unchanged (account detail/edit still an outstanding UI gap, smoke test.fixme #4).
- Kanban loads stages dynamically from `GET /pipeline/stages`; drag-and-drop PATCHes `{ stage_id }`.
- The same React bundle handles `/` and `/login.html`; login stores access/refresh tokens and current user in `localStorage`.

### SPA repair log (covered by per-feature spec files in e2e/)
| File | Change | Test |
|------|--------|------|
| `frontend/src/App.tsx` | Added `activities` state + `Calendar` tab | 'activities - list', 'activities - create' |
| `frontend/src/App.tsx` | `ActivitiesView` + `ActivityDetailView` components | 'activities - detail', 'activities - update', 'activities - delete' |
| `frontend/src/App.tsx` | `ActivityFormModal` (create + edit) | 'activities - create', 'activities - update' |
| `frontend/src/App.tsx` | Contact name → clickable button, `ContactDetailView` | 'contacts - detail', 'contacts - update', 'contacts - delete' |
| `frontend/src/App.tsx` | `ContactEditModal` (PATCH /contacts/:id) | 'contacts - update' |
| `frontend/src/App.tsx` | `DealCard` onClick → `DealDetailView` | 'deals - detail', 'deals - update', 'deals - delete' |
| `frontend/src/App.tsx` | `DealEditModal` (PATCH /deals/:id) | 'deals - update' |
| `frontend/src/App.tsx` | `ImportModal` (file → FileReader → POST /contacts/import) | 'import - upload triggers feedback' |
| `frontend/src/App.tsx` | `exportContacts()` (fetch → blob → `<a download>`) | 'export - download initiated' |

### Key decisions (v2)
| # | Decision |
|---|----------|
| D18 | `deal.stage` (legacy string) stays in place for backward compat; `deal.stage_id` is the authoritative field for v2 kanban. Both are kept in sync on PATCH. |
| D19 | Pipeline stage `probability` stored as 0–100 integer; converted to 0.0–1.0 float before writing to `deal.probability` so existing probability-based code is unaffected. |
| D20 | Stage DELETE returns 409 (not 422) when deals exist — 409 Conflict is the correct HTTP semantics for "resource state conflict". |
| D21 | Manager role can create/update/delete pipeline stages (same as admin) — stage configuration is an operations concern, not just superadmin. |
| D22 | In tests, pipeline stages are NOT auto-seeded (no lifespan). Tests that need them must create them via `POST /pipeline/stages` or insert `PipelineStage` rows directly. |

## M5 gotchas

- **`GET /deals/rotting` and `GET /deals/export` must be registered BEFORE `GET /deals/{deal_id}`** — FastAPI matches literal path segments before parameterized ones only when they're registered first in the same router.
- **`GET /contacts/export` and `POST /contacts/import` must be registered BEFORE `GET /contacts/{contact_id}`** — same routing order issue.
- **`expand_rrule` validates before the `count=0` guard** — so calling with count=0 still raises ValueError for invalid rules. This is intentional for router-level validation without needing a separate validate function.
- **`recurrence_rule` stored as JSON Text** in Activity; `_to_out` deserializes it and returns `None` when absent. Client-side JSON encoding/decoding is fully round-tripped.
- **Tags router uses `/tags/contacts/{id}` and `/tags/deals/{id}` prefixes** (not nested under `/contacts/{id}/tags`) to keep the router self-contained under the `/tags` prefix.
- **`POST /outbox/digest` path conflict** — `POST /outbox` and `POST /outbox/digest` are different paths; `GET /outbox/{message_id}` uses `int` type annotation so "digest" would 422 on GET but the POST endpoint has a distinct path that matches before the int param.
- **`compute_lead_score_v2` with `use_decay=False` and default weights is bit-identical to v1** — verified by test `test_v2_use_decay_false_matches_v1`. Use this when comparing scores for regression.
