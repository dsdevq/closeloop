# Changelog

All notable changes to CloseLoop are documented here.

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
