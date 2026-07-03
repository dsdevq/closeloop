# CloseLoop — Agent Harness

You are a senior engineer picking up CloseLoop. This file is your entry point; the full knowledge tree lives under [docs/](docs/INDEX.md).

## What CloseLoop is (60 seconds)

A self-contained CRM: **Python + FastAPI + SQLite** backend, **React + Vite + Tailwind** frontend served from the same origin. Zero external services, zero outbound network calls (enforced by test — see [ADR-0010](docs/architecture/decisions/0010-outbox-queue-only.md)). Single binary + a static bundle. Full product contract in [docs/product/prd.md](docs/product/prd.md).

## How to navigate this repo

1. **[docs/INDEX.md](docs/INDEX.md)** — top-level map of the docs tree.
2. **[docs/product/prd.md](docs/product/prd.md)** — the product contract. THE answer to "what should CloseLoop do".
3. **[docs/architecture/overview.md](docs/architecture/overview.md)** — layer map, data model, request lifecycle.
4. **[docs/architecture/decisions/INDEX.md](docs/architecture/decisions/INDEX.md)** — 24 ADRs, one per non-trivial design call. Consult when your instinct disagrees with what's in the code.
5. Task guides live under [docs/guides/](docs/guides/INDEX.md).
6. Contributor guide (frontmatter, ADR/RFC process, tree shape): [docs/README.md](docs/README.md).
7. Behavioral skill for maintaining the tree: [.agent/skills/knowledge-tree.md](.agent/skills/knowledge-tree.md) — devclaw runners auto-load this on every task; read it if you're contributing by hand.

## Load-bearing rules — MUST FOLLOW

- **MUST run `bash scripts/verify.sh` before every PR.** Runs pytest + Playwright + frontend typecheck. Non-negotiable gate.
- **MUST use the injected clock** (`clock` kwarg / `clk.now`) in all time-dependent code — never call `datetime.utcnow()` directly. Tests depend on this. See [ADR-0006](docs/architecture/decisions/0006-injected-clock.md).
- **MUST NOT mock the database in tests.** Use the in-memory SQLite via the `client` fixture. See [ADR-0005](docs/architecture/decisions/0005-static-pool-test-engine.md).
- **MUST NOT change `playwright.config.ts` `stdout: 'ignore', stderr: 'ignore'`.** ARM64 pipe buffer fills, uvicorn blocks on log writes, tests get ERR_CONNECTION_REFUSED. See [docs/guides/development.md](docs/guides/development.md#arm64-pipe-gotcha---do-not-undo).
- **MUST use `apiFetch`** (from `frontend/src/lib/api.ts`), never bare `fetch()`. Auth-aware; handles 401 → login redirect consistently.
- **MUST NOT introduce runtime outbound network calls.** Product invariant; enforced by `test_no_outbound_network.py`. See [ADR-0010](docs/architecture/decisions/0010-outbox-queue-only.md).
- **MUST NOT use `dangerouslySetInnerHTML`** for user-supplied data.
- **MUST register API routers BEFORE `app.mount("/", StaticFiles(...))`** in `app/main.py` — route registration order determines which handler wins.
- **MUST use `Response(status_code=204)`** for 204 responses, not plain `return`.
- **MUST return HTTP 422** (not 400) for semantic validation failures — see [ADR-0002](docs/architecture/decisions/0002-stage-state-machine.md).

## What lives WHERE

- `app/` — FastAPI backend. `app/core/` = pure functions, no I/O, no globals ([ADR-0001](docs/architecture/decisions/0001-pure-core-module.md)).
- `frontend/` — React + Vite source. Build outputs to `app/static/`.
- `tests/` — pytest suite (pure unit + API integration).
- `e2e/` — Playwright suite. One `.spec.ts` per feature area.
- `scripts/verify.sh` — the PR gate (pytest + Playwright + typecheck).
- `.agent/skills/` — per-repo skill bundles loaded by devclaw runners. `knowledge-tree.md` teaches the discipline for maintaining `docs/`.
- `docs/` — the knowledge tree. Start at [docs/INDEX.md](docs/INDEX.md).
- Top-level: [README.md](README.md), this file, [CHANGELOG.md](CHANGELOG.md).

## Milestones (as of 2026-07-01)

M1–M5 + v1 (auth) + v2 (accounts + pipeline stages) all **✅ Done**. See [docs/product/roadmap.md](docs/product/roadmap.md).

**Done:** Insights dashboard — all four sections (Trends, Funnel, Leaderboard, SourceCohorts) wired in `features/insights/`. Insights tab added to AppHeader and routed in App.tsx alongside Pipeline/Contacts/Accounts/Activities/Today/Stats. Visible to all roles (auth scoping handled server-side). Smoke e2e test in `e2e/insights.spec.ts`.

**Done:** Notifications engine slice 1 — typed event model (`app/core/notifications.py`: `DealAssignedEvent`, `StageChangedEvent`, `TaskOverdueEvent`, `MentionEvent` discriminated union) + `notifications` table (`app/models.py`) + pull API (`app/routers/notifications.py`: `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`). Full test coverage in `tests/test_core_notifications.py` + `tests/test_notifications.py`. See [ADR-0025](docs/architecture/decisions/0025-notifications-pull-model.md). Trigger wiring (slice 2), overdue-task generation (slice 3), and email digest (slice 4) are deferred.

## When you learn something durable

Add it to the right `docs/` page — do NOT back-fill this file. `AGENTS.md` stays lean; the tree grows.

- Design decision with rationale → new ADR under [docs/architecture/decisions/](docs/architecture/decisions/INDEX.md), following [that dir's README](docs/architecture/decisions/README.md).
- Bigger design in flight → RFC under [docs/proposals/](docs/proposals/INDEX.md).
- Operational procedure → runbook under [docs/operations/runbooks/](docs/operations/runbooks/INDEX.md).
- Post-incident review → [docs/operations/incidents/](docs/operations/incidents/INDEX.md).
- New env var, endpoint, or config knob → the matching [docs/reference/](docs/reference/INDEX.md) page.

Every doc page carries frontmatter (`title`, `status`, `owner`, `last_reviewed`, `tags`). The behavioral discipline for maintaining the tree lives in [.agent/skills/knowledge-tree.md](.agent/skills/knowledge-tree.md) — devclaw runners load it on every task; read it if you're contributing by hand.
