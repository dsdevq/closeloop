---
title: Deploy guide
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-08
tags: [deploy, docker, tailscale, ci]
---

# Deploy

CloseLoop owns its runtime. Devclaw opens PRs; closeloop deploys itself.

## Shape

- **`Dockerfile`** at the repo root — multi-stage: node builds the Vite frontend into `app/static/`, Python runtime installs `requirements-prod.txt` and runs gunicorn + UvicornWorker. `PORT` and `WEB_CONCURRENCY` env-overridable (defaults: 8000, 4). See [reference/env-vars.md](../reference/env-vars.md).
- **`.github/workflows/ci.yml`** — self-hosted runner on `lifekit-vps`. Test job: pytest + frontend typecheck + ESLint. Deploy job: only on merge-to-main; runs the container-swap sequence (§ below) after tests pass.
- **`.github/workflows/ci-docker.yml`** — container gate (PRs + pushes): builds the full production image and runs the pytest suite inside the built container. Validates the Dockerfile itself, not just the Python source.
- **Runtime URL:** `https://lifekit-vps.tail1cb676.ts.net:8372/` (Tailscale-served, tailnet-only, port fixed via the `APP_PORT` Actions variable).

## Why this shape

Historically devclaw spun ONE throwaway container per goal — five simultaneous `devclaw-deploy-closeloop-*` containers had accumulated on the VPS by 2026-07-01. Wrong ownership boundary. Now closeloop owns its Dockerfile + CI, and devclaw's `_project_owns_its_deploy` check (in `devclaw/goal/tick.py`) detects the Dockerfile at the workspace root and skips its own auto-deploy. One goal-branch merge → one deploy from closeloop's own CI. See [ADR-0027](../architecture/decisions/0027-singleton-container-swap-cicd.md).

## Deploy contract

**Trigger:** every push to `main` runs the `deploy` job in `ci.yml`, gated on the `test` job passing.

**Container-swap sequence (automated by `ci.yml` deploy job):**

1. **Record** the image SHA the running container was started from. Empty on first deploy.
2. **Build** `closeloop:<commit-sha>` + `closeloop:latest` using `--cache-from closeloop:latest`. Building before stopping the old container keeps the gap to milliseconds.
3. **Swap** — `docker rm -f closeloop || true` then `docker run -d --name closeloop --restart unless-stopped -p 127.0.0.1:${PORT}:${PORT} -e PORT=${PORT} -v closeloop-data:/data closeloop:<sha>`.
4. **Verify** — poll `GET http://127.0.0.1:${PORT}/health` up to 30 × 2 s. Exit 0 on first success; exit 1 if never healthy.
5. **Rollback** — if step 4 fails AND step 1 captured a previous image: restore the prior container from the snapshotted SHA and re-pin `:latest`.
6. **Prune** — `docker image prune -f` always runs (`if: always()`).

**Invariants callers can rely on:**

- The named volume `closeloop-data:/data` is preserved across swaps — the database survives a container replacement.
- `GET /health` is the stable health probe surface: `{"status": "ok", "db": "ok", ...}`.
- If the new container is unhealthy, CI restores the previous image automatically (as long as there was a prior deploy).
- `:latest` tag always reflects the currently running container after a successful deploy.

**Container gate (`ci-docker.yml`):** runs on every PR and push. Builds the production image, then runs the full pytest suite inside it (excluding Playwright). The `tests/` directory and `requirements.txt` (which includes pytest + httpx) are volume-mounted at test time — they are not baked into the production image.

## Health probe

`GET /health` returns `{"status": "ok", "db": "ok", "version": "0.1.0", "timestamp": "..."}`.

- The Dockerfile's `HEALTHCHECK` uses `curl -fsS http://127.0.0.1:${PORT}/health` — Docker marks the container unhealthy if the app can't answer within 5 s (3 retries, 30 s interval, 15 s start period).
- `health_router` is registered first in `app/main.py`, before the `StaticFiles` catch-all mount, so `/health` is never shadowed by the static handler.

## First-time setup (already done — for reference)

1. Register a GitHub Actions runner on `lifekit-vps` for `dsdevq/closeloop`, service name `actions.runner.dsdevq-closeloop.lifekit-vps-closeloop`.
2. Set repo Actions variable `APP_PORT=8372` — deterministic port so the Tailscale URL doesn't move.
3. `sudo tailscale serve --bg --https=8372 http://127.0.0.1:8372` on `lifekit-vps` (one-time, persists across reboots).

## Manual redeploy

Documented in [operations/runbooks/manual-redeploy.md](../operations/runbooks/manual-redeploy.md). Use this when the deploy job fails or when you want to test a build change on the VPS before merging.

> **Runner caveat (2026-07-01, status unverified):** The self-hosted runner on `lifekit-vps` experienced a `startup_failure` regression (workflow ID 305245282) — every push registered as `startup_failure` even with a valid workflow YAML. Root cause: runner infrastructure, not workflow code. If you see jobs failing with `startup_failure`, reset or re-register the runner via the GitHub Actions tab on `dsdevq/closeloop`; this is an infrastructure issue, not a bug in the workflow YAML. Until green runner status is confirmed, treat the manual-redeploy runbook as the primary deploy path.

## Local build/run

```bash
# Build the full multi-stage image
docker build -t closeloop:local .

# Ephemeral run — data lost on exit
docker run --rm -p 8000:8000 closeloop:local

# Persistent singleton — data survives restarts
docker run -d --name closeloop -p 8000:8000 -v closeloop-data:/data closeloop:local
```
