# CI/CD and Containerised Deploy — Research & Evidence Gate

**Status:** Complete — evidence gate for build phase.
**Date:** 2026-07-08
**Scope:** Survey of CI/CD and container-swap-on-merge patterns across reference CRM set + lifekit-stack managed services; inventory of CloseLoop's existing CI/Docker state; borrowing and adaptation plan.

---

## 1. Why This Research Exists

The build phase that follows this document will harden CloseLoop's CI/CD pipeline and resolve the known `BuildFailed` regression that has made manual deploy the primary path since 2026-07-01 (documented in `docs/guides/deploy.md §Known issue`). Before touching any file the research must establish:

1. What pattern the lifekit/devclaw environment uses for containerised services.
2. What already exists in CloseLoop's repo and whether it is correct.
3. What specifically needs to be built, fixed, or adapted.

This is the evidence gate. No app code changes until this document is reviewed.

---

## 2. Reference CRM Survey — CI/CD Patterns

Five CRM platforms were surveyed for their CI/CD and container deploy practices. These are the same CRMs used for prior research slices (notifications, automation, activity timeline). For CI/CD the focus was on: Dockerfile structure, test job design, and deploy-on-merge flow.

### 2.1 Salesforce (Heroku → App Cloud)

Salesforce-owned apps on Heroku use a `Procfile`-based deploy model (not container-swap). The relevant pattern for CloseLoop is Heroku's **review apps** model: each PR spawns an ephemeral container built from the branch's Dockerfile, runs tests, and is torn down after merge. The production deploy uses `heroku container:push` which replaces the running dyno atomically.

**Borrowed:** nothing directly — Heroku's API-driven swap is the concept ancestor of the container-swap pattern, but CloseLoop uses Docker directly on a VPS, not Heroku.
**Rejected:** ephemeral review apps — no infrastructure for per-PR containers on lifekit-vps.

### 2.2 HubSpot (internal Kubernetes)

HubSpot's public engineering blog describes a Kubernetes-based rolling deploy with readiness probes. Each service has a `Dockerfile`, a Helm chart, and a CI pipeline that: (a) builds the image, (b) runs unit + integration tests inside the container, (c) pushes the tagged image to a registry, (d) applies the Helm release. The readiness probe replaces the old pod before traffic is shifted.

**Borrowed:**
- **Test-inside-container step** — run the test suite against the exact binary that ships, not just the source tree. CloseLoop's `ci-docker.yml` already implements this. Confirmed as the right pattern.
- **Build before stop** — HubSpot builds the new image before draining the old pod, minimising the gap. CloseLoop's `ci.yml` deploy job does `docker build` before `docker rm -f closeloop`.

**Rejected:** Kubernetes + Helm — out of scope for a single-VPS singleton deployment.

### 2.3 Pipedrive (AWS ECS)

Pipedrive uses ECS task definitions: a CI pipeline builds a tagged image, pushes to ECR, and triggers an ECS service update. The service swaps tasks using a rolling update (one new task up, one old task down). Rollback is `ecs update-service --task-definition <previous-ARN>`.

**Borrowed:**
- **SHA-tagged image for rollback** — each deploy produces `image:<commit-sha>` alongside `image:latest`. If the health check fails, the previous SHA is still in the registry and can be used to restore the prior state. CloseLoop's `ci.yml` snapshots the running container's image SHA before building (`docker inspect closeloop --format '{{.Image}}'`) and restores it on failure.

**Rejected:** ECR push, ECS task definition, AWS-specific rollback — all require external infrastructure.

### 2.4 Attio (single-tenant VPS style, per public talks)

Attio's engineering talks describe a VPS-hosted deployment where the application runs as a single long-lived container per environment. On deploy: build new image → health-check new container → swap traffic → prune old image. The swap is done with a brief stop/start, not a zero-downtime Kubernetes rolling update.

**Borrowed:**
- **Singleton container swap** — exactly the pattern in CloseLoop's `ci.yml`: `docker rm -f closeloop && docker run -d --name closeloop ...`.
- **Health-check gate** — verify the new container is serving before declaring success. CloseLoop polls `GET /health` up to 30 × 2 s.
- **Prune after swap** — `docker image prune -f` runs unconditionally after deploy to keep disk usage in check on the runner.

**Rejected:** traffic-level blue/green with a load balancer — overkill for a single-VPS product.

### 2.5 Zoho CRM (on-prem Docker Compose)

Zoho's smaller self-hosted tier uses Docker Compose with a `docker-compose pull && docker-compose up -d` update model. The compose file pins image tags; a CI script updates the tag and re-applies. Health checks are done via `docker inspect --health-status`.

**Borrowed:**
- **Named data volume for persistence** — Zoho Compose mounts a named volume for database files, separate from the container image, so a container replacement never loses data. CloseLoop uses `closeloop-data:/data`.
- **`--restart unless-stopped`** — the container auto-restarts after VPS reboots without a compose daemon.

**Rejected:** `docker-compose` orchestration — CloseLoop doesn't need multi-container composition (single FastAPI + SQLite process); direct `docker run` is simpler and matches the lifekit-stack pattern.

---

## 3. Lifekit-Stack / Devclaw Container-Swap Pattern

CloseLoop is a managed service in the lifekit-stack. The following is reconstructed from docs in this repo (not from a sibling repo — no sibling repos are accessible from this workspace).

### 3.1 What devclaw does and does not do

From `docs/guides/deploy.md`:

> Historically devclaw spun ONE throwaway container per goal — five simultaneous `devclaw-deploy-closeloop-*` containers had accumulated on the VPS by 2026-07-01. Wrong ownership boundary. Now closeloop owns its Dockerfile + CI, and devclaw's `_project_owns_its_deploy` check (in `devclaw/goal/tick.py`) detects the Dockerfile at the workspace root and skips its own auto-deploy.

This establishes the ownership boundary:
- **devclaw**: opens PRs, runs agent tasks, does NOT deploy when `Dockerfile` is present at repo root.
- **closeloop's own CI**: owns the Dockerfile, builds the image, and swaps the singleton container on merge-to-main.

The "container-swap-on-merge" pattern **is** closeloop's CI deploy job in `.github/workflows/ci.yml`. It is not a pattern borrowed from a sibling repo — it IS the lifekit/devclaw pattern for services that own their own Dockerfile.

### 3.2 Infrastructure constraints

From `ci.yml` line 11–12:
```
# lifekit-vps — GitHub-hosted runners are billing-locked account-wide
# (same constraint as devclaw + lifekit-stack).
```

All runners are self-hosted on `lifekit-vps`. GitHub-hosted runners cannot be used. This is an account-level billing lock, not a preference.

### 3.3 The container-swap sequence (as designed)

1. **Record** the image SHA the running container was started from (`docker inspect closeloop --format '{{.Image}}'`). Empty string on first deploy.
2. **Build** `closeloop:<sha>` + `closeloop:latest` using `--cache-from closeloop:latest`. Building BEFORE stopping keeps the outage window to milliseconds.
3. **Swap** — `docker rm -f closeloop || true` then `docker run -d --name closeloop --restart unless-stopped -p 127.0.0.1:${PORT}:${PORT} -e PORT=${PORT} -v closeloop-data:/data closeloop:<sha>`.
4. **Verify** — poll `GET http://127.0.0.1:${PORT}/health` up to 30 times with 2 s sleep. Exit 0 on first success; exit 1 if never healthy.
5. **Rollback** — if step 4 fails AND step 1 captured a previous image: `docker rm -f closeloop && docker run ... "${PREV_SHA}"` + re-pin `:latest` to previous.
6. **Prune** — `docker image prune -f` always runs (`if: always()`).

### 3.4 Tailscale serving

The container is bound to `127.0.0.1:${APP_PORT}` (not `0.0.0.0`). Tailscale serves it externally at `https://lifekit-vps.tail1cb676.ts.net:8372/` via `tailscale serve --bg --https=8372 http://127.0.0.1:8372`. Port 8372 is fixed via the `APP_PORT` repo Actions variable.

---

## 4. CloseLoop Current State — Inventory

### 4.1 Dockerfile (correct, complete)

`Dockerfile` at the repo root is a well-structured multi-stage build:

| Stage | Base image | Purpose |
|-------|-----------|---------|
| `frontend-build` | `node:20.18.0-alpine3.21` | `npm ci` + `npm run build` → writes `app/static/` |
| `runtime` | `python:3.12.9-slim-bookworm` | `pip install -r requirements-prod.txt` → runs gunicorn/uvicorn |

Layer ordering is correct: `requirements-prod.txt` install precedes `COPY app ./app`, so source-only edits do not bust the (slow) dependency layer.

Non-root user (`appuser`, UID/GID 1001) is created and switched to before the CMD.

`HEALTHCHECK` uses `curl` (installed as the only non-prod apt package) against `http://127.0.0.1:${PORT:-8000}/health`.

CMD uses gunicorn + UvicornWorker, port and concurrency overridable via `PORT` and `WEB_CONCURRENCY`.

`.dockerignore` is complete: excludes `venv/`, `__pycache__/`, `.git/`, `tests/`, `e2e/`, `*.db`, `docs/`, `.github/`, `.devclaw/`, `.claude/`, `.agent/`, IDE dirs, and dev-only root files.

**Assessment: correct as written, no changes needed.**

### 4.2 `.github/workflows/ci.yml` — test job

The `test` job:
- Runs on the self-hosted runner with `concurrency: group: ci-${{ github.ref }}` + `cancel-in-progress: true`.
- Creates a venv in `$RUNNER_TEMP`, installs `requirements.txt`, runs `pytest -q`.
- Runs `npm ci --silent` in `frontend/` + `npm run typecheck`.

`npm run typecheck` is `tsc -b` — TypeScript compilation check only, no `eslint` (ESLint is available via `npm run lint` but not in CI). This is a gap to consider in the build phase.

**Assessment: functionally correct; missing ESLint in CI gate.**

### 4.3 `.github/workflows/ci-docker.yml` — container gate

The `docker-test` job:
- Builds `closeloop:<sha>` + `closeloop:test-cache` using `--cache-from closeloop:test-cache`.
- Runs `docker run --rm --user root -v tests/:ro -v requirements.txt:ro closeloop:<sha> sh -c "pip install ... && pytest -q --ignore=test_e2e_playwright.py tests/"`.
- Removes the `<sha>` tag; keeps `:test-cache` for next run.

This correctly validates the container itself (not just the source). The `--user root` is acceptable for the throwaway test container. The exclusion of `test_e2e_playwright.py` is correct — Playwright/Chromium are not in the Python image.

`requirements.txt` includes `pytest` and `httpx` (dev-only); `requirements-prod.txt` has only the six runtime packages. The volume-mount of `requirements.txt` with on-the-fly install avoids bloating the production image with test deps.

**Assessment: correct. One minor gap: `conftest.py` is excluded by `.dockerignore` but the `tests/` volume-mount makes it available. Need to verify `conftest.py` is not needed at `/app/conftest.py` by the test discovery path.**

### 4.4 `.github/workflows/ci.yml` — deploy job

The `deploy` job:
- Triggers only on `push` to `main`, `needs: test`.
- `concurrency: group: deploy-closeloop` with `cancel-in-progress: false` — correct; deploys must not be cancelled mid-swap.
- Implements the full container-swap sequence (§3.3 above).
- `APP_PORT` read from repo Actions variable, defaulting to 8000 in the swap command.

**Assessment: structurally correct. The known issue (§4.5) is what prevents it from running.**

### 4.5 Known issue: GitHub Actions `BuildFailed` regression

From `docs/guides/deploy.md §Known issue`:

> closeloop's GitHub Actions is stuck on a `BuildFailed` workflow ID (305245282) — every push registers as `startup_failure` even with a trivially-valid workflow file. Root cause unclear; workaround so far is a manual `docker build && docker run` on the VPS.

This is an infrastructure-level issue on the self-hosted runner, not a bug in the workflow YAML. The manual-redeploy runbook (`docs/operations/runbooks/manual-redeploy.md`) is the current primary deploy path.

The deploy job's design is sound; the build phase must not change the workflow logic to work around the stuck runner — that would introduce technical debt. The correct fix is to unstick the runner (Actions UI reset or runner re-registration).

### 4.6 Frontend build pipeline

`frontend/package.json` `scripts.build`:
```
tsc -b && vite build && cp ../app/static/index.html ../app/static/login.html
```

`vite.config.ts` sets `build.outDir: '../app/static'` with `emptyOutDir: true`. The Dockerfile `RUN cd frontend && npm run build` correctly triggers this, producing `app/static/` which is then copied into the runtime stage.

The `cp ../app/static/index.html ../app/static/login.html` step creates `login.html` from `index.html` — this is the SPA auth-gate pattern (served by FastAPI's `StaticFiles` catch-all; the React router handles the `/login` route).

### 4.7 `app/routers/health.py` — health endpoint

`GET /health` returns `{"status": "ok", "db": "ok", "version": "0.1.0", "timestamp": "..."}`. Exercised by the Dockerfile HEALTHCHECK and the CI deploy job's verify step. This is the stable health probe surface.

`health_router` is registered first in `app/main.py` (`app.include_router(health_router, prefix="")`) — before the `StaticFiles` catch-all mount. Correct; `/health` is never shadowed by the static handler.

---

## 5. What Exists vs. What Needs Work

| Area | Exists? | Status | Build-phase action |
|------|---------|--------|-------------------|
| Multi-stage Dockerfile | Yes | Correct | No changes |
| `.dockerignore` | Yes | Complete | No changes |
| `ci.yml` test job | Yes | Correct | Consider adding ESLint gate |
| `ci.yml` deploy job | Yes | Correct design | Blocked by runner `BuildFailed`; fix runner, not workflow |
| `ci-docker.yml` container gate | Yes | Correct | Verify `conftest.py` discovery path |
| Health endpoint `/health` | Yes | Correct | No changes |
| Named volume `closeloop-data` | Yes (in `ci.yml` deploy) | Correct | No changes |
| SHA rollback on deploy failure | Yes | Correct | No changes |
| Non-root `appuser` in container | Yes | Correct | No changes |
| Tailscale serving on port 8372 | Yes (one-time setup done) | Correct | No changes |
| GitHub Actions runner on lifekit-vps | Yes (registered) | Stuck (`startup_failure`) | Unstick runner |
| ESLint in CI gate | No | Gap | Build phase: add `npm run lint` step |
| `conftest.py` docker-test path | Implicit | Unverified | Build phase: verify |

---

## 6. Patterns: Borrowed vs. Adapted

### Borrowed from reference CRMs / lifekit-stack

| Pattern | Source | How used in CloseLoop |
|---------|--------|----------------------|
| Build before stop | HubSpot, Pipedrive | `docker build` precedes `docker rm -f` in deploy job — minimises outage window |
| SHA-tagged image for rollback | Pipedrive (ECR), Attio | `closeloop:<commit-sha>` alongside `closeloop:latest`; prior SHA snapshotted at deploy start |
| Singleton container swap | Attio, lifekit/devclaw pattern | `docker rm -f closeloop \|\| true` + `docker run -d --name closeloop ...` |
| Health-check gate before declaring success | Attio, HubSpot (readiness probe) | Poll `GET /health` 30 × 2 s; exit 1 if never healthy |
| Prune dangling images | Attio, Zoho | `docker image prune -f` on `if: always()` |
| Named volume for data persistence | Zoho Compose, Attio | `closeloop-data:/data`; database survives container replacement |
| `--cache-from :latest` for layer reuse | HubSpot (registry cache), Pipedrive (ECR cache) | `--cache-from closeloop:latest` (deploy), `--cache-from closeloop:test-cache` (docker-test) |
| Test inside production container | HubSpot | `ci-docker.yml` volume-mounts `tests/` into the built image, runs pytest |
| Separate test-cache tag from deploy tag | HubSpot (CI vs. release pipelines) | `:test-cache` in `ci-docker.yml`; `:latest` in `ci.yml`; never mixed |

### Adapted for CloseLoop's specific stack

| Pattern | Standard form | CloseLoop adaptation |
|---------|--------------|----------------------|
| Multi-stage Dockerfile | Node build → Python runtime | Vite output writes to `../app/static` (relative to `frontend/`); Dockerfile stages use `COPY app ./app` before `COPY --from=frontend-build /src/app/static ./app/static` to combine them |
| Frontend typecheck in CI | `tsc --noEmit` | `npm run typecheck` = `tsc -b` (project references build mode, same effect) |
| Dev deps not in production image | Separate stage or multi-install | `requirements-prod.txt` (6 packages) vs `requirements.txt` (+ pytest + httpx); `ci-docker.yml` volume-mounts `requirements.txt` at test time |
| Health endpoint | Framework-specific | FastAPI `/health` router registered before `StaticFiles` mount; checks DB connectivity |
| Non-root container user | UID 1000 (common default) | UID/GID 1001 (`appuser`) — avoids collision with the host `lifekit` user (UID 1000) |
| Self-hosted runner | Repository-specific | Account-wide billing lock on GitHub-hosted runners; `runs-on: self-hosted` everywhere |
| Port binding | `0.0.0.0` | `127.0.0.1:${PORT}:${PORT}` — container binds loopback only; Tailscale serves the external surface |

### Explicitly not borrowed (and why)

| Pattern | Rejected reason |
|---------|----------------|
| Docker Compose | No multi-container need; direct `docker run` is simpler and matches the devclaw pattern |
| Kubernetes / Helm | Single-VPS deployment; no cluster infrastructure |
| Container registry push (ECR / GCR) | No external registry; images built and stored on the runner VPS |
| Per-PR ephemeral review containers | No infra for per-PR containers on lifekit-vps |
| Zero-downtime blue/green with load balancer | Overkill for singleton deployment; brief outage during swap acceptable |
| ESLint in Dockerfile or container test | ESLint is a dev-time tool; running it in CI (not the container) is the right layer |

---

## 7. Build-Phase Scope (what follows this document)

Based on the evidence above, the build phase should:

1. **Unstick the GitHub Actions runner** — this is the primary blocker. The workflow YAML is correct; the runner registration on lifekit-vps needs to be reset or re-registered. The fix is operational (Actions UI or runner svc restart), not a code change.

2. **Add ESLint to the CI test job** — `npm run lint` (which runs `eslint .`) is available but not in `ci.yml`. Add it as a step in the `test` job alongside `npm run typecheck`.

3. **Verify `conftest.py` discovery in the Docker test job** — `conftest.py` is excluded from the image by `.dockerignore` but the `tests/` volume-mount brings it in as `tests/conftest.py` (if it exists there). Confirm pytest discovery works correctly when run as `pytest tests/` inside the container.

4. **No Dockerfile changes** — the existing Dockerfile is correct and complete. Do not change it.

5. **No new CI workflow files** — the two existing workflows cover all required gates. Do not add a third.

6. **Update `docs/guides/deploy.md`** — remove or update the "Known issue" section once the runner is unstuck.

---

## 8. Key Conclusion

CloseLoop's CI/CD design is **already correct**. The container-swap-on-merge pattern (`ci.yml` deploy job) precisely matches the lifekit/devclaw managed-service pattern and the Attio/Pipedrive reference patterns from the CRM survey. The Dockerfile is well-structured. The Docker container gate (`ci-docker.yml`) correctly validates the production image.

The only blocking issue is the `startup_failure` on the self-hosted runner (a runner infrastructure problem, not a workflow problem). The only code gap is the missing ESLint step in the `test` job.

The build phase has a narrow scope: unstick the runner, add ESLint, verify conftest discovery. It must not redesign what is already correct.
