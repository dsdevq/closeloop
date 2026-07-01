---
title: Deploy guide
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [deploy, docker, tailscale]
---

# Deploy

CloseLoop owns its runtime. Devclaw opens PRs; closeloop deploys itself.

## Shape

- **`Dockerfile`** at the repo root — multi-stage: node builds the vite frontend into `app/static/`, python runtime installs `requirements.txt` and runs `uvicorn app.main:app`. `PORT` env-overridable (default 8000).
- **`.github/workflows/ci.yml`** — self-hosted runner registered on `lifekit-vps`. Test job: pytest + frontend typecheck. Deploy job: only on merge-to-main; builds `closeloop:${SHA}` + `closeloop:latest`; swaps the singleton `closeloop` container; verifies `/health` before returning.
- **Runtime URL:** `https://lifekit-vps.tail1cb676.ts.net:8372/` (Tailscale-served, tailnet-only, port fixed via the `APP_PORT` Actions variable).

## Why this shape

Historically devclaw spun ONE throwaway container per goal — five simultaneous `devclaw-deploy-closeloop-*` containers had accumulated on the VPS by 2026-07-01. Wrong ownership boundary. Now closeloop owns its Dockerfile + CI, and devclaw's `_project_owns_its_deploy` check (in `devclaw/goal/tick.py`) detects the Dockerfile at the workspace root and skips its own auto-deploy. One goal-branch merge → one deploy from closeloop's own CI.

## First-time setup (already done — for reference)

1. Register a GitHub Actions runner on `lifekit-vps` for `dsdevq/closeloop`, service name `actions.runner.dsdevq-closeloop.lifekit-vps-closeloop`.
2. Set repo Actions variable `APP_PORT=8372` — deterministic port so the Tailscale URL doesn't move.
3. `sudo tailscale serve --bg --https=8372 http://127.0.0.1:8372` on `lifekit-vps` (one-time, persists across reboots).

## Known issue (2026-07-01)

closeloop's GitHub Actions is stuck on a `BuildFailed` workflow ID (305245282) — every push registers as `startup_failure` even with a trivially-valid workflow file. Root cause unclear; workaround so far is a manual `docker build && docker run` on the VPS. The Dockerfile is what devclaw's escape hatch keys off, so per-goal auto-deploy is already switched off correctly; CI is a nice-to-have that needs a click in the GitHub web UI Actions tab to reset.

## Health probe

- `GET /health` returns `{"status": "ok", "db": "ok", "version": "0.1.0", "timestamp": "..."}`.
- The Dockerfile's HEALTHCHECK uses `curl -fsS http://127.0.0.1:${PORT}/health` — Docker marks the container unhealthy if the app can't answer.

## Manual redeploy (for now)

```bash
ssh lifekit-vps
sudo -u lifekit bash -c '
  cd ~/closeloop && git pull &&
  docker build -t closeloop:latest . &&
  docker rm -f closeloop || true &&
  docker run -d --name closeloop --restart unless-stopped \
    -p 127.0.0.1:8372:8372 -e PORT=8372 -v closeloop-data:/data closeloop:latest
'
```

Once the CI is unstuck, this becomes automatic on every merge-to-main.
