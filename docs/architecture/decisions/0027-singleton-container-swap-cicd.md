---
id: "0027"
title: "CI/CD — multi-stage Dockerfile, singleton container swap, test-inside-container gate"
status: accepted
date: 2026-07-08
owner: "@dsdevq"
tags: [ci, docker, deploy, architecture]
supersedes: null
superseded-by: null
---

# ADR-0027 — CI/CD: multi-stage Dockerfile, singleton container swap, test-inside-container gate

## Context

CloseLoop is a single-process FastAPI + SQLite application served from a VPS (`lifekit-vps`) where GitHub-hosted runners are billing-locked account-wide. All CI runs on a self-hosted runner registered on the VPS. The application is self-contained (zero external services — see ADR-0010) and has no multi-container dependencies.

Before this ADR, devclaw (the agent harness) spun throwaway containers per goal, accumulating five orphaned `devclaw-deploy-closeloop-*` containers on the VPS by 2026-07-01. The ownership boundary was wrong. This ADR formalises the design that gives closeloop full control of its own CI/CD.

Three decisions are coupled and recorded together:

1. **Multi-stage Dockerfile** (Node build → Python runtime).
2. **Singleton container swap on merge-to-main** as the deploy primitive.
3. **Test-inside-production-container** as the container gate CI job.

## Decision

### 1. Multi-stage Dockerfile

The `Dockerfile` at the repo root has two stages:

- **`frontend-build`** (`node:20.18.0-alpine3.21`): runs `npm ci` + `npm run build` (which is `tsc -b && vite build`). Output is written to `../app/static/` (relative to `frontend/`).
- **`runtime`** (`python:3.12.9-slim-bookworm`): installs only `requirements-prod.txt` (6 packages; pytest and httpx are excluded), copies `app/` from the workspace and `app/static/` from the `frontend-build` stage, creates non-root `appuser` (UID/GID 1001), and runs gunicorn + UvicornWorker.

Layer ordering places `requirements-prod.txt` install before the `COPY app` layer so source-only edits do not bust the slow dependency cache.

The container binds to `0.0.0.0:${PORT:-8000}` (gunicorn) but the `docker run` command in CI pins it to `127.0.0.1:${PORT}` — Tailscale serves the external surface.

### 2. Singleton container swap on merge-to-main

The `deploy` job in `.github/workflows/ci.yml` runs only on push to `main` after the `test` job passes. The sequence is:

1. Snapshot the running container's image SHA for rollback.
2. Build `closeloop:<commit-sha>` + `closeloop:latest` using `--cache-from closeloop:latest` (before stopping the old container).
3. `docker rm -f closeloop || true` then `docker run -d --name closeloop --restart unless-stopped -p "127.0.0.1:${PORT}:${PORT}" -e PORT -v closeloop-data:/data closeloop:<sha>`.
4. Poll `GET /health` up to 30 × 2 s; exit 0 on first success.
5. If step 4 fails and a prior SHA was captured: restore the prior container; re-pin `:latest`.
6. `docker image prune -f` always runs.

The `concurrency: group: deploy-closeloop, cancel-in-progress: false` setting ensures concurrent deploys queue rather than cancel — a mid-swap cancellation would leave the service down.

The named volume `closeloop-data:/data` is never touched by the swap — the database survives a container replacement.

### 3. Test-inside-production-container gate

`.github/workflows/ci-docker.yml` runs on every PR and push alongside the main `ci.yml` test job. It:

1. Builds the full production image (`closeloop:<sha>` + `closeloop:test-cache` for cache persistence).
2. Volume-mounts `tests/` (excluded from the image by `.dockerignore`) and `requirements.txt` (which adds pytest + httpx) into the built container.
3. Runs `python -m pytest -q --ignore=tests/test_e2e_playwright.py tests/` inside the container as root (acceptable for a throwaway test container; the image still runs as `appuser` in production).

This validates the exact binary that ships — not just the source tree. Playwright/browser tests are excluded because Chromium is not in the Python image; they run in the `ci.yml` test job.

## Consequences

- **Ownership is clear:** devclaw's `_project_owns_its_deploy` check skips auto-deploy when it finds a `Dockerfile` at the workspace root. One merge → one deploy from closeloop's own CI.
- **Rollback is automatic:** any deploy failure restores the prior container from the snapshotted image SHA, provided there was a prior deploy.
- **Test deps never enter the production image:** `requirements-prod.txt` (6 packages) is separate from `requirements.txt` (+ pytest, httpx). Volume-mount at test time keeps the image lean.
- **Non-root UID 1001** avoids collision with the VPS host `lifekit` user (UID 1000).
- **Layer cache is preserved across manual `docker system prune`** via `--cache-from closeloop:latest` (deploy) and `--cache-from closeloop:test-cache` (container gate).
- **ESLint is a CI step, not a container step** — `npm run lint` runs in the `test` job alongside `tsc -b`; running it inside the Python container would require Node, which is not in the runtime image.

## Alternatives considered

- **Kubernetes + Helm rolling deploy** — requires cluster infrastructure not available on a single VPS. Rejected.
- **Docker Compose** — no multi-container dependency; direct `docker run` is simpler and matches the devclaw pattern. Rejected.
- **Blue/green with a load balancer** — overkill for a singleton deployment; brief outage during swap (~milliseconds between rm and run) is acceptable. Rejected.
- **Container registry push (ECR/GCR)** — no external registry available; images are built and stored on the runner VPS. Rejected.
- **Per-PR ephemeral review containers** — no infra for per-PR containers on `lifekit-vps`. Rejected.
- **Build test deps into the production image** — violates the principle of keeping the shipped binary lean; pytest and httpx have no role in production. Volume-mount at test time is the correct pattern. Rejected.
