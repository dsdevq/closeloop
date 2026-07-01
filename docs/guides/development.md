---
title: Development guide
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [development, testing, e2e, setup]
---

# Development

How to install, run, and test CloseLoop locally.

## Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.x (ORM), SQLite (`closeloop.db`)
- **Auth:** `pyjwt>=2.8.0` (HS256 JWT) + `bcrypt>=4.0.0` (password hashing)
- **Frontend:** React + Vite + TypeScript + Tailwind in `frontend/`; production build emits static assets to `app/static/`
- **Tests:** pytest, `httpx`-backed Starlette `TestClient`, Playwright (e2e)
- **Runtime posture:** zero external services, zero outbound network calls (enforced by `test_no_outbound_network.py`)

## Quick start

```bash
# Install deps
pip install -r requirements.txt

# Build frontend
npm --prefix frontend install --include=dev
npm run build

# Start server (local dev — hot reload)
uvicorn app.main:app --reload

# Start server (container / preview — bind all interfaces)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Test commands

```bash
# Python unit + integration tests
python -m pytest -q

# Playwright e2e tests (FastAPI auto-starts on port 8088 via webServer config)
npx playwright test --reporter=list

# The verify gate — BOTH must be green before every PR
bash scripts/verify.sh
# or: make verify
```

`scripts/verify.sh` auto-handles the ARM64 no-root workaround below.

## E2E tests — one-time setup

```bash
# Install Playwright (root-level)
npm install                          # installs @playwright/test at root
npx playwright install --with-deps chromium   # downloads Chromium + system deps (needs sudo)
```

**Test credentials:** `TEST_USER` / `TEST_PASS` env vars, default `admin@closeloop.com` / `admin123`.

**Port:** the config uses `E2E_PORT=8088` (port 8000 may be occupied by a harness stub in some CI environments).

## ARM64 / no-root workaround

libXfixes.so.3 is missing on ARM64 Debian and you may not have sudo. Extract without root:

```bash
# 1. Pull the lib out of the .deb (no root required)
curl -fsSL http://deb.debian.org/debian/pool/main/libx/libxfixes/libxfixes3_6.0.0-2+b5_arm64.deb \
     -o /tmp/lxf.deb && dpkg-deb -x /tmp/lxf.deb /tmp/lxf && mkdir -p ~/lib && cp /tmp/lxf/usr/lib/*/libXfixes.so.3* ~/lib/

# 2. Install Chromium skipping host validation
PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=1 npx playwright install chromium
```

`playwright.config.ts` prepends `~/lib` to `LD_LIBRARY_PATH` automatically.

## ARM64 pipe gotcha — DO NOT UNDO

`playwright.config.ts` sets `stdout: 'ignore', stderr: 'ignore'` for the webServer.

On ARM64 Linux the OS pipe buffer (~64 KB) fills after ~10 tests when set to `'pipe'`, blocking uvicorn's logging writes and causing subsequent tests to get `ERR_CONNECTION_REFUSED`. **Do not change these back to `'pipe'`.**

## Current test state

**52 passed / 0 failed / 5 fixme-skipped** (57 total) as of 2026-06-29. See [e2e.md](e2e.md) for the fixme catalog.
