# CloseLoop — Agent Harness

You are a senior engineer picking up CloseLoop. This file is your entry point; the rest of the knowledge tree lives under [docs/](docs/INDEX.md).

## What CloseLoop is (60 seconds)

A self-contained CRM: **Python + FastAPI + SQLite** backend, **React + Vite + Tailwind** frontend served from the same origin. Zero external services, zero outbound network calls (enforced by test), single binary + a static bundle. Full product contract in [PRD.md](PRD.md).

## How to navigate this repo

Read in this order:

1. **[docs/INDEX.md](docs/INDEX.md)** — the map of the docs tree. Follow the links your task needs; you don't need to read everything upfront.
2. **[PRD.md](PRD.md)** — the product contract. THE answer to "what should CloseLoop do".
3. **[ARCHITECTURE.md](ARCHITECTURE.md)** — layer map, data model, request lifecycle.
4. **[DECISIONS.md](DECISIONS.md)** — 22 D-numbered decisions with rationale. Consult when your instinct disagrees with what's in the code — usually the code is right.
5. Subsystem deep-dives in [`docs/`](docs/INDEX.md): development, testing, auth, frontend, e2e, deploy.

## Load-bearing rules — MUST FOLLOW

- **MUST run `bash scripts/verify.sh` before every PR.** Runs pytest + Playwright + frontend typecheck. Non-negotiable gate.
- **MUST use the injected clock** (`clock` kwarg / `clk.now`) in all time-dependent code — never call `datetime.utcnow()` directly. Tests depend on this. See [D6](DECISIONS.md).
- **MUST NOT mock the database in tests.** Use the in-memory SQLite via the `client` fixture. Mocked DBs mask schema drift and migration bugs.
- **MUST NOT change `playwright.config.ts` `stdout: 'ignore', stderr: 'ignore'`.** ARM64 pipe buffer fills, uvicorn blocks on log writes, tests get ERR_CONNECTION_REFUSED. See [docs/development.md](docs/development.md).
- **MUST use `apiFetch`** (from `frontend/src/lib/api.ts`), never bare `fetch()`. Auth-aware; handles 401 → login redirect consistently across features.
- **MUST NOT introduce runtime outbound network calls.** Product invariant; enforced by `test_no_outbound_network.py`.
- **MUST NOT use `dangerouslySetInnerHTML`** for user-supplied data.
- **MUST register API routers BEFORE `app.mount("/", StaticFiles(...))`** in `app/main.py` — FastAPI evaluates routes in registration order.
- **MUST use `Response(status_code=204)`** for 204 responses, not plain `return`.
- **MUST return HTTP 422** (not 400) for semantic validation failures — aligns with FastAPI convention.

## What lives WHERE

- `app/` — FastAPI backend. `app/core/` = pure functions, no I/O, no globals.
- `frontend/` — React + Vite source. Build outputs to `app/static/`.
- `tests/` — pytest suite (pure unit + API integration).
- `e2e/` — Playwright suite. One `.spec.ts` per feature area.
- `scripts/verify.sh` — the PR gate. Handles ARM64 no-root Playwright quirks.
- `.agent/skills/` — per-repo skill bundles loaded by devclaw runners.
- `docs/` — narrative documentation. Read [docs/INDEX.md](docs/INDEX.md) first.
- Top-level: [README.md](README.md), [PRD.md](PRD.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md), [BACKLOG.md](BACKLOG.md), [CHANGELOG.md](CHANGELOG.md) — durable, hand-curated.

## Milestones (as of 2026-07-01)

M1–M5 + v1 (auth) + v2 (accounts + pipeline stages) are all **✅ Done**. See [BACKLOG.md](BACKLOG.md) for what's next and [CHANGELOG.md](CHANGELOG.md) for what shipped.

## When something's not in the docs

If you learn something durable while working — a subtle invariant, a gotcha that would surprise the next reader, a decision with real "why" behind it — add it to the right `docs/` page (and link from the INDEX) rather than back-filling this file. `AGENTS.md` stays lean; the tree grows.
