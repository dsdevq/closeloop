# CloseLoop — Agent Harness

You are a senior engineer picking up CloseLoop. This file is your entry point; the full knowledge tree lives under [docs/](docs/INDEX.md).

## What CloseLoop is (60 seconds)

A self-contained CRM: **Python + FastAPI + SQLite** backend, **React + Vite + Tailwind** frontend served from the same origin. Zero external services, zero outbound network calls (enforced by test — see [ADR-0010](docs/architecture/decisions/0010-outbox-queue-only.md)). Single binary + a static bundle. Full product contract in [docs/product/prd.md](docs/product/prd.md).

## How to navigate this repo

1. **[docs/INDEX.md](docs/INDEX.md)** — top-level map of the docs tree.
2. **[docs/product/prd.md](docs/product/prd.md)** — the product contract. THE answer to "what should CloseLoop do".
3. **[docs/architecture/overview.md](docs/architecture/overview.md)** — layer map, data model, request lifecycle.
4. **[docs/architecture/decisions/INDEX.md](docs/architecture/decisions/INDEX.md)** — 26 ADRs, one per non-trivial design call. Consult when your instinct disagrees with what's in the code.
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

**Done:** Notifications engine slice 1 — typed event model (`app/core/notifications.py`: `DealAssignedEvent`, `StageChangedEvent`, `TaskOverdueEvent`, `MentionEvent` discriminated union) + `notifications` table (`app/models.py`) + pull API (`app/routers/notifications.py`: `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`). Full test coverage in `tests/test_core_notifications.py` + `tests/test_notifications.py`. See [ADR-0025](docs/architecture/decisions/0025-notifications-pull-model.md).

**Done:** Notifications engine slice 2 — After-Save trigger wiring. `app/services/notifications.py` provides `create_notification(db, *, recipient_id, event, entity_type, entity_id, clk)` — the single DB-write entry point; it calls `db.add()` but does NOT commit (caller owns the transaction). Triggers live inline in `app/routers/deals.py` alongside the domain mutations they observe: `update_deal_stage` fires `StageChangedEvent` to the deal owner (Salesforce workflow-rule / Pipedrive `deal_stage_changed` pattern); `update_deal` fires `StageChangedEvent` when `stage_id` changes and `DealAssignedEvent` when `owner_id` changes (Salesforce After-Save / HubSpot automation pattern). Self-notifications are suppressed (actor == recipient → no notification). `DealUpdate` now includes `owner_id: Optional[int]` so deals can be reassigned. Tests in `tests/test_notification_triggers.py`. Overdue-task generation (slice 4) and email digest (slice 5) are deferred.

**Done:** Notifications engine slice 3 — @mention parsing. `parse_mentions(body: str) -> list[str]` is a pure function in `app/core/notifications.py`: extracts `@token` mentions using `(?<!\w)@([A-Za-z0-9][A-Za-z0-9._+-]*)` (negative lookbehind prevents matching the `@` inside email addresses like `alice@example.com`). Returns lowercased, de-duplicated tokens in first-appearance order. `resolve_mentioned_users(db, tokens)` in `app/services/notifications.py` resolves tokens to active User rows by ILIKE `<token>@%` against `User.email`. Trigger wiring lives in `app/routers/activities.py`: `_emit_mention_notifications(db, *, activity, actor, clk)` is called (a) in `create_activity` after `db.flush()` (before commit, so activity.id is available), and (b) in `update_activity` when `"body"` is in the update payload. Only fires for `activity.type == "note"` — call/email/meeting bodies are skipped to avoid spurious pings from email addresses or Zoom links. Self-mentions suppressed. Borrowed from Zoho @mention (first-class kind) and Salesforce Chatter (@ prefix); Attio `comment_mention` pattern influenced the entity_type/entity_id/snippet payload shape. Tests in `tests/test_core_notifications.py` (TestParseMentions) and `tests/test_mention_triggers.py`. Email digest (slice 4) and overdue-task notifications remain deferred.

**Done:** Activity timeline / audit history slice 1 — typed event model + persistence. `app/core/history.py` defines the closed discriminated union of 12 typed history event dataclasses (`DealCreatedEntry`, `DealStageChangedEntry`, `DealAssignedEntry`, `DealUpdatedEntry`, `DealDeletedEntry`, `ContactCreatedEntry`, `ContactUpdatedEntry`, `ContactDeletedEntry`, `ActivityCreatedEntry`, `ActivityUpdatedEntry`, `ActivityCompletedEntry`, `ActivityDeletedEntry`). `_KIND_MAP` is the single source of truth for the closed kind set. `event_to_meta()` / `event_from_meta()` handle JSON serialisation round-trips. `HistoryEntry` ORM model in `app/models.py` (`history_entries` table): `entity_id` is a plain INTEGER (no FK) so history survives entity deletion; composite index on `(entity_type, entity_id, occurred_at)`. `app/services/history.py` provides `record_history(db, *, entity_type, entity_id, event, clk)` — the single DB-write entry point; calls `db.add()` but does NOT commit (caller owns transaction). `GET /history?entity_type=deal&entity_id=N[&limit=N]` in `app/routers/history.py` — entity-scoped pull, newest first, no creation endpoint. See [ADR-0026](docs/architecture/decisions/0026-history-save-triggered-capture.md).

**Done:** Activity timeline / audit history slice 2 — trigger wiring. `record_history()` is called inline in router handlers after the domain mutation, before `db.commit()`, mirroring the notification trigger pattern established in PR #43. Trigger pattern borrowed from Salesforce Field History Tracking's save-triggered capture (same-transaction write); rejected alternatives: outbox/event-queue, SQLAlchemy ORM event hooks, database-layer CDC, separate audit microservice — see [ADR-0026](docs/architecture/decisions/0026-history-save-triggered-capture.md) §Rejected alternatives. History triggers are unconditional on actor (unlike notifications, which suppress self-actions). Trigger sites:
- `app/routers/deals.py`: `create_deal` → `deal_created`; `update_deal_stage` → `deal_stage_changed` (when stage actually changes); `update_deal` → `deal_stage_changed` (when stage_id causes stage name change), `deal_assigned` (when owner_id changes to a non-null user), `deal_updated` (when non-structural fields like title/value are in the update); `delete_deal` → `deal_deleted` (title snapshotted before `db.delete()`; `delete_deal` now accepts `clk` dependency).
- `app/routers/contacts.py`: `create_contact` → `contact_created` (now flushes before commit to get contact.id); `update_contact` → `contact_updated`; `delete_contact` → `contact_deleted` (name snapshotted before delete; `delete_contact` now accepts `clk` dependency).
- `app/routers/activities.py`: `create_activity` → `activity_created` (after existing `db.flush()`, before mention notifications); `update_activity` → `activity_updated`; `complete_activity` → `activity_completed`; `delete_activity` → `activity_deleted` (fields snapshotted before delete; `delete_activity` now accepts `clk` dependency).
Tests in `tests/test_core_history.py` (pure serialisation round-trips) and `tests/test_history_triggers.py` (API integration). Field-level diffing (slice 3) and timeline UI (slice 4) remain deferred.

## Docker / container image

- **Multi-stage Dockerfile** (repo root): Node 20 stage builds Vite → `app/static/`; Python 3.12 runtime stage installs only prod deps (see `requirements-prod.txt`) and runs gunicorn with `UvicornWorker`.
- **Non-root user**: UID/GID 1001 (`appuser`). `/app` and `/data` are `chown`'d to it before switching with `USER appuser`.
- **Data persistence**: `DATABASE_URL` is read from env (`app/database.py`). Dockerfile sets it to `sqlite:////data/closeloop.db`. Mount `closeloop-data:/data` to persist across restarts. Local dev still defaults to `./closeloop.db`.
- **Build cache**: `COPY requirements-prod.txt` + `RUN pip install` sits above the `COPY app` layer — dep installs are cached unless `requirements-prod.txt` changes.
- **Runtime knobs**: `PORT` (default 8000), `WEB_CONCURRENCY` (default 4 gunicorn workers). See [docs/reference/env-vars.md](docs/reference/env-vars.md).
- **Base image tags**: `python:3.12.9-slim-bookworm`, `node:20.18.0-alpine3.21`. Append `@sha256:<digest>` for immutable CI builds (see header comment in Dockerfile).
- **`.dockerignore`**: covers `venv/`, `__pycache__/`, `.git/`, `tests/`, `e2e/`, `*.db`, IDE/agent dirs.

## When you learn something durable

Add it to the right `docs/` page — do NOT back-fill this file. `AGENTS.md` stays lean; the tree grows.

- Design decision with rationale → new ADR under [docs/architecture/decisions/](docs/architecture/decisions/INDEX.md), following [that dir's README](docs/architecture/decisions/README.md).
- Bigger design in flight → RFC under [docs/proposals/](docs/proposals/INDEX.md).
- Operational procedure → runbook under [docs/operations/runbooks/](docs/operations/runbooks/INDEX.md).
- Post-incident review → [docs/operations/incidents/](docs/operations/incidents/INDEX.md).
- New env var, endpoint, or config knob → the matching [docs/reference/](docs/reference/INDEX.md) page.

Every doc page carries frontmatter (`title`, `status`, `owner`, `last_reviewed`, `tags`). The behavioral discipline for maintaining the tree lives in [.agent/skills/knowledge-tree.md](.agent/skills/knowledge-tree.md) — devclaw runners load it on every task; read it if you're contributing by hand.
