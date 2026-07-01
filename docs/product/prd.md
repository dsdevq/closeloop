---
title: Product Requirements Document
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [product, prd, contract]
---

# CloseLoop — PRD

> This is the product contract for CloseLoop, authored at kickoff. It is the spec the build is judged against. Do not change it without explicit instruction from the owner.

## 1. One-paragraph vision

CloseLoop is a lightweight, single-binary CRM for a freelancer or a small sales team who currently live in spreadsheets and lose deals to forgotten follow-ups. It tracks contacts, deals moving through a sales pipeline, and the activities/reminders that drive them forward — and it does the arithmetic the spreadsheet can't: a weighted pipeline forecast, an automatic lead score, an overdue-follow-up queue, and a saved-filter search. It is fully self-contained — Python + FastAPI + SQLite, vanilla HTML/CSS/JS, zero external services and zero outbound network calls — so it boots from a clean checkout, serves a clickable preview on localhost, and is auditable end-to-end by a pytest suite that pins its core logic.

## 2. Target user & the job it does

**Primary user:** an independent freelancer or a 2–5 person sales team running a manageable book of deals (tens to low hundreds open at once).

**The job:** "When I'm deciding who to call today and how much revenue I can realistically count on this quarter, give me a trustworthy answer in one screen — without me maintaining formulas, and without my data leaving this machine." Concretely: surface who is overdue for follow-up, tell me which leads are hottest, and forecast the pipeline by stage probability so I'm not fooling myself with raw deal totals.

## 3. Core entities / data model

SQLite (single file, `closeloop.db`). Foreign keys ON. Timestamps stored as ISO-8601 UTC text.

- **contacts** — `id PK`, `name`, `email`, `company`, `title`, `phone`, `source` (referral/inbound/outbound/event/other), `created_at`, `updated_at`. A person/account.
- **deals** — `id PK`, `contact_id FK→contacts`, `title`, `amount` (cents, integer), `currency`, `stage` (enum: `lead`, `qualified`, `proposal`, `negotiation`, `won`, `lost`), `expected_close_date`, `created_at`, `updated_at`, `closed_at` (nullable). A revenue opportunity. **Many deals per contact.**
- **stage_transitions** — `id PK`, `deal_id FK→deals`, `from_stage`, `to_stage`, `occurred_at`, `note`. Append-only audit log of every stage move; powers velocity/aging metrics. **Many per deal.**
- **activities** — `id PK`, `deal_id FK→deals` (nullable), `contact_id FK→contacts` (nullable), `type` (call/email/meeting/note/task), `subject`, `body`, `due_at` (nullable — present ⇒ it's a reminder), `completed_at` (nullable), `created_at`. The follow-up/reminder engine.
- **saved_views** — `id PK`, `name`, `entity` (deals/contacts/activities), `filter_json` (serialized filter AST), `created_at`. Persisted search/filter definitions.
- **outbox** — `id PK`, `to_addr`, `subject`, `body`, `kind` (email/sms), `status` (queued/sent/failed), `created_at`, `sent_at`. **Stub boundary** — "sent" mail lands here, never on a wire.
- **event_log** — `id PK`, `ts`, `actor`, `verb`, `entity`, `entity_id`, `meta_json`. Structured usage/audit stream feeding the stats view.

Relationships: contact 1—N deals; deal 1—N stage_transitions; deal/contact 1—N activities; saved_views and outbox standalone.

## 4. MVP scope (milestones M1–M4)

**M1 — Skeleton & data layer.** FastAPI app boots, SQLite schema + migrations, FK enforcement, `/health` endpoint, structured JSON logging middleware, seed script. Outcome: server runs, DB initializes from clean checkout, health is green.

**M2 — Contacts & deals CRUD + pipeline board.** REST endpoints for contacts/deals with validation; stage transitions go through the state machine (§5) and append to `stage_transitions`. Vanilla-JS kanban board: columns per stage, deal cards, drag-to-move calling the transition endpoint. Outcome: a user can manage contacts and move deals through the pipeline in the browser.

**M3 — Activities, reminders & forecast.** Activity/reminder CRUD; overdue computation; "Today" queue (overdue + due-today). Weighted pipeline forecast endpoint and dashboard tile. Lead score computed and shown on contact/deal cards. Outcome: the daily-driver screen works — who to chase, what's forecast.

**M4 — Search/saved views, outbox & stats.** Filter AST evaluator with a query UI; save/load named views. Outbox-backed "send follow-up" action (queues, never sends). In-app stats view reading `event_log`. Outcome: usable v1 — searchable, observable, with a faked comms boundary.

## 5. The machine-verifiable core

Pure, dependency-free functions (no DB, no clock-as-global — time injected) the pytest suite pins hard:

1. **Deal-pipeline stage state machine.** Legal transitions only: `lead→qualified→proposal→negotiation→won`, with `lost` reachable from any open stage, and `won`/`lost` terminal (no resurrection). Illegal transitions raise; legal ones return the transition record. Tests enumerate the full transition matrix (valid + every invalid pair).

2. **Weighted pipeline forecast.** `forecast = Σ(open_deal.amount × stage_probability)` with a fixed probability map (lead .10, qualified .25, proposal .50, negotiation .75; won/lost excluded). Returns total weighted value, unweighted open total, and per-stage breakdown. Tests pin exact integer-cent arithmetic, empty pipeline, and exclusion of closed deals.

3. **Lead score (0–100).** Deterministic weighted sum over: recency of last activity, deal amount band, source weight, stage progression, and engagement count (number of completed activities) — with a documented decay on staleness. Tests pin scores for fixed fixtures and assert monotonicity (more recent engagement / further stage ⇒ higher score, all else equal).

4. **Overdue / reminder computation.** Given `now`, partition reminders into overdue / due-today / upcoming / completed; compute days-overdue. Tests cover timezone-normalized boundaries (just-before vs just-after midnight UTC), completed-excluded, and null-due-date handling.

5. **Filter AST evaluator.** A small boolean query language (`AND`/`OR`/`NOT` over field-op-value leaves: `eq, neq, gt, lt, gte, lte, contains, in`) evaluated against entity rows. Tests pin operator semantics, nesting, type coercion, and unknown-field rejection. This is reused by saved_views.

6. **Deal velocity / stage aging.** From `stage_transitions`, compute time-in-stage and total cycle time per deal, plus average days-per-stage across won deals. Tests pin against synthetic transition logs.

## 6. Iteration backlog (post-MVP, numbered)

1. **Stats dashboard (observability).** In-app view + `/stats` endpoint: usage counters from `event_log` (entities created, transitions, reminders completed) **and per-endpoint metrics** — request count, p50/p95 latency, error rate — captured by the logging middleware. *(observability feature)*
2. **Forecast scenarios & probability overrides** — let the user tune the stage-probability map and run best/expected/worst cases; extends the forecast core with new pinned cases. *(deepens verifiable core)*
3. **Lead-score model v2** — add temporal decay curves and configurable weights, with backtesting fixtures. *(deepens verifiable core)*
4. **Bulk import/export** — CSV in/out for contacts & deals with row-level validation report.
5. **Activity recurrence** — recurring reminders (RRULE-lite expansion engine, itself unit-tested).
6. **Tags & segmentation** — many-to-many tags on contacts/deals, queryable via the filter AST.
7. **Notifications via outbox digest** — a daily "overdue + due-today" digest composed into the outbox table (still no real send).
8. **Deal-rotting alerts** — flag deals stagnant in a stage beyond a stage-specific SLA, derived from the velocity core.

## 7. Non-goals / explicitly out of scope

- **No real email/SMS send.** The comms boundary is the `outbox` table; "send" = insert a `queued` row. A test-only `mark_sent` flips status. No SMTP, no providers, no network.
- **No real auth / multi-tenancy.** Single local user; a static actor string in `event_log`. No login, no orgs, no row-level security.
- **No payments / billing / invoicing.** `amount` is a tracked number only.
- **No external enrichment / lookups / webhooks / OAuth.** Zero outbound calls at runtime — enforced by a test that asserts no socket egress during the suite.
- **No build step / SPA framework / CDN assets.** Vanilla HTML/CSS/JS served by FastAPI; all assets local.
- **No background workers / message queues.** Reminder evaluation is on-request (computed against `now`), not a daemon.

## 8. Definition of done for the MVP

A reviewer and an automated gate can confirm:

1. **Clean boot:** fresh checkout → `pip install -r requirements.txt` → one documented command starts the server; DB auto-initializes; `/health` returns `200` with `{status: ok, db: ok, version}`.
2. **Clickable preview:** localhost UI loads with no console errors; user can create a contact, create a deal, drag it across pipeline stages, add a reminder, and see it in the "Today" queue.
3. **Core pinned:** `pytest` passes with **all six §5 components covered**, including the full stage-transition matrix and exact-cent forecast math; coverage on the core logic module ≥ 90%.
4. **Self-containment proven:** suite includes a test asserting **no outbound network connections** at runtime; "send follow-up" writes an `outbox` row and sends nothing.
5. **Observable:** every request emits a structured JSON log line (method, path, status, latency, request-id); `event_log` records domain events; the in-app stats view renders live usage counters.
6. **Determinism:** all time-dependent logic accepts an injected `now`; no test depends on wall-clock or network; suite is green in CI from a clean container.
7. **Documented contract:** README with run/test commands and an OpenAPI schema served at `/docs`.

---

## Build conventions (devclaw run rules)

- **Stack:** Python + FastAPI + SQLite backend; vanilla HTML/CSS/JS frontend, no build step.
- **Layout:** `requirements.txt` at the repo root; the test suite under `tests/` runnable by `python -m pytest` from the repo root; a documented run command in the README. The **verify gate is `pip install -q -r requirements.txt && python -m pytest -q`** — it must be green from M1 onward (M1 ships at least a `/health` smoke test).
- **Every change ships with tests; never weaken, skip, or delete existing tests.**
- **Keep the memory artifacts current** (`ARCHITECTURE.md`, `DECISIONS.md`, `BACKLOG.md`) as part of every task's definition of done — see those files.
