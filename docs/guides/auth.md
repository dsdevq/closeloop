---
title: Auth guide (v1)
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [auth, jwt, roles]
---

# Auth (v1)

JWT-based auth layer. Landed in v1; test-fixture-transparent so pre-auth tests kept working unchanged.

## JWT strategy

- **HS256** with secret from `JWT_SECRET_KEY` env var (defaults to a dev placeholder — change in production).
- **Access token:** 30-minute TTL. Signed payload: `{sub: user_id, type: "access"}`.
- **Refresh token:** 7-day TTL. Stored in `refresh_tokens` table with `revoked_at` for revocation. **Rotated on every `/auth/refresh` call.**
- `decode_token()` in `app/core/security.py` raises `jwt.ExpiredSignatureError` or `jwt.InvalidTokenError` on failure.
- `get_current_user` in `app/dependencies.py` resolves Bearer token → live `User` row; raises HTTP 401 on any failure.

## Seed credentials

On first startup (no users in DB):
- Creates `admin@closeloop.com` / `admin123` (role=admin) and prints to stdout.
- Backfills `owner_id` on any existing `contacts`, `deals`, `activities` rows to the seed admin.

**Change the password immediately after first login in production.**

## Roles

| Role | Access |
|------|--------|
| `admin` | All records + user management (`GET /auth/users`, `POST /auth/register` for others) |
| `manager` | All records; cannot manage users |
| `rep` | Own records only — `owner_id == user.id` filter on contacts, deals, activities |

## `owner_id` migration

`ALTER TABLE contacts/deals/activities ADD COLUMN owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL` runs idempotently in `_run_migrations()` at startup. Safe to re-run — duplicate-column error is suppressed.

## Test fixtures

- `tests/conftest.py` seeds an admin user in the in-memory DB and passes `Authorization: Bearer <token>` as default headers to `TestClient`. All 305 pre-existing tests remain unmodified.
- `tests/test_auth.py` defines its own `fresh_setup` / `admin_setup` fixtures for isolated auth-flow testing without the default admin token.

## Frontend integration

- All API calls go through `apiFetch` (`frontend/src/lib/api.ts`), which reads the access token from localStorage and handles 401 → clear tokens → redirect to `/login.html`.
- `getToken()` and `storedUser()` are the only sanctioned reads of localStorage auth state.
- The same React bundle handles `/` and `/login.html`; the build script copies `app/static/index.html` to `app/static/login.html` for this reason.
