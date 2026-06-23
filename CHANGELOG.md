# Changelog

All notable changes to CloseLoop are documented here.

---

## [v2.0] — 2026-06-23

### Accounts (Companies) Layer + Customizable Pipeline Stages

This release implements the v2 scope defined in [docs/DOMAIN.md](docs/DOMAIN.md) § "v2 — Accounts Layer + Pipeline Stages".

#### Accounts / Companies

- **Account model** — new `accounts` table: id, name, domain, industry, website, phone, address, owner_id FK→users, created_at, updated_at.
- **CRUD endpoints** — `POST/GET/PATCH/DELETE /accounts`. Role rules: `rep` sees own (owner_id), `manager`/`admin` see all.
- **Contact → Account link** — `account_id` FK (nullable, SET NULL) added to contacts so contacts can belong to a company.
- **Account detail** — `GET /accounts/{id}` returns linked contacts inline.
- **Frontend** — new Accounts tab: list table (name, domain, industry, # contacts, owner) + detail panel (meta + linked contacts) + New Account modal. Contacts table shows account name as a click-through link to the account detail.

#### Customizable Pipeline Stages

- **PipelineStage model** — new `pipeline_stages` table: id, name, position (ordering), probability (0–100 int), is_default, created_at.
- **Default stages seeded on startup** (if table empty): Prospecting(0), Qualification(20), Proposal(50), Negotiation(75), Closed-Won(100), Closed-Lost(0).
- **Read endpoint** — `GET /pipeline/stages` (auth required) returns all stages ordered by position.
- **Admin/manager endpoints** — `POST /pipeline/stages`, `PATCH /pipeline/stages/{id}`, `DELETE /pipeline/stages/{id}`. Delete returns **409** with deal count if the stage has active deals.
- **Deal.stage_id** — nullable FK to pipeline_stages added to deals. Existing rows backfilled from legacy `stage` string via name-map at startup.
- **Deal PATCH extended** — `PATCH /deals/{id}` now accepts `stage_id` (and optional `probability` override). On stage_id change, `deal.probability` is inherited from `PipelineStage.probability / 100` unless explicitly overridden; legacy `deal.stage` field is kept in sync with `PipelineStage.name`.
- **Dynamic kanban** — kanban columns now loaded from `GET /pipeline/stages` (no more hardcoded stage list). Drag-and-drop sends `{ stage_id }` to `PATCH /deals/{id}`.

#### Technical notes

- Column migrations: `ALTER TABLE contacts ADD COLUMN account_id` and `ALTER TABLE deals ADD COLUMN stage_id` run idempotently at startup.
- All 324 pre-existing tests continue to pass; 38 new tests in `tests/test_accounts.py` and `tests/test_pipeline.py` (362 total).
- Frontend version label updated to v2.0.

---

## [v1.0] — 2026-06-23

### Authentication & User Roles

This release implements the v1 scope defined in [docs/DOMAIN.md](docs/DOMAIN.md) § "v1 — Auth + User Roles".

#### New features

- **User model** — `users` table with `email`, `hashed_password` (bcrypt), `role` (admin | manager | rep), `full_name`, `created_at`, `is_active`.
- **Auth endpoints** (`/auth`):
  - `POST /auth/register` — open for first user; admin-only thereafter.
  - `POST /auth/login` — returns `{access_token, refresh_token, token_type, user}`.
  - `POST /auth/refresh` — rotates refresh token, returns new access token.
  - `POST /auth/logout` — revokes refresh token (204).
  - `GET  /auth/me` — returns current user info.
  - `GET  /auth/users` — admin-only user list.
- **JWT HS256** — 30-min access tokens, 7-day refresh tokens stored in `refresh_tokens` table with revocation support.
- **Startup seed** — if no users exist, `admin@closeloop.com` / `admin123` is created and credentials are printed to stdout.
- **Record ownership** — `owner_id` FK added to `contacts`, `deals`, `activities`; existing rows backfilled to the seed admin.
- **Role enforcement**:
  - `admin` — full access to all records and user management.
  - `manager` — read/write access to all records, cannot manage users.
  - `rep` — restricted to records where `owner_id == user.id`.
- **Protected endpoints** — all `/contacts`, `/deals`, `/activities`, `/reminders`, `/forecast`, `/saved-views`, `/outbox`, `/stats`, `/tags` routes require a valid Bearer token (401 if missing/invalid).
- **Frontend** — `app/static/login.html` with clean sign-in form; `index.html` updated with JWT-aware `apiFetch`, user badge, role pill, logout button, and v1.0 version label; redirects to `/login.html` on 401.

#### Technical notes

- JWT library: `pyjwt>=2.8.0`.  Password hashing: `passlib[bcrypt]>=1.7.4`.
- Column migration: `ALTER TABLE … ADD COLUMN owner_id` runs at startup with duplicate-column error suppression (idempotent).
- All 305 pre-existing tests continue to pass; the test `client` fixture now seeds an admin user and attaches a valid Bearer token to every request.
- 20 new tests in `tests/test_auth.py` cover register, login, refresh, logout, 401/403 enforcement, rep/manager/admin visibility rules.

---

*Previous milestones (M1–M5) are not listed here — see git history for details.*
