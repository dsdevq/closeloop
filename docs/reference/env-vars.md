---
title: Environment variables — reference
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [reference, configuration, env]
---

# Environment variables

Every environment variable CloseLoop reads. Authoritative — if code adds one, this table gets updated in the same PR.

| Variable | Default | Read by | Effect |
|---|---|---|---|
| `PORT` | `8000` | Dockerfile CMD, gunicorn | Port the FastAPI app listens on inside the container. |
| `WEB_CONCURRENCY` | `4` | Dockerfile CMD, gunicorn | Number of gunicorn UvicornWorker processes. Override at container run-time (e.g. `docker run -e WEB_CONCURRENCY=2`). |
| `DATABASE_URL` | `sqlite:///./closeloop.db` (local dev) / `sqlite:////data/closeloop.db` (Docker image) | `app/database.py` | SQLAlchemy database URL. The Dockerfile overrides this to `/data/closeloop.db` so data lands on the mounted volume. Override to use a different path or engine. |
| `JWT_SECRET_KEY` | dev placeholder (change in prod!) | `app/core/security.py` | HS256 signing secret for access + refresh JWTs. |
| `APP_PORT` | `8000` (via `${APP_PORT:-8000}` in ci.yml) | `.github/workflows/ci.yml` (deploy job) | Host port the container is bound to on `lifekit-vps`. Set as a repo Actions **variable** (not secret). See [guides/deploy.md](../guides/deploy.md). |
| `E2E_PORT` | `8088` | `playwright.config.ts` | Port Playwright expects the FastAPI test server on. Overridable per test environment. |
| `TEST_USER` | `admin@closeloop.com` | Playwright specs | Default e2e login. |
| `TEST_PASS` | `admin123` | Playwright specs | Default e2e password. |
| `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS` | unset | Playwright install | Set to `1` on ARM64 no-root to skip host-deps check. See [guides/development.md](../guides/development.md). |
| `LD_LIBRARY_PATH` | prepended `~/lib` by `playwright.config.ts` | Chromium runtime | Picks up the manually-extracted `libXfixes.so.3` on ARM64 no-root. |

## Adding a variable

If your PR adds a `os.environ.get(...)` or a `${VAR}` reference in a shell script, YAML, or `env:` block, this table gets a new row in the same PR. The docs-lint script (`scripts/docs_lint.py`) can be extended to grep the code for reads that aren't documented here.
