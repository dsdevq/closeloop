---
title: CloseLoop Domain Concepts
status: living
owner: "@dsdevq"
last_reviewed: 2026-07-05
tags: [domain, crm, automation]
---

# CloseLoop — Domain Concepts

This file documents first-class domain concepts and their relationships as they are
introduced.  It is **append-only by convention**: each versioned section adds new
concepts without rewriting earlier ones.  For design rationale see the ADR index
([docs/architecture/decisions/INDEX.md](docs/architecture/decisions/INDEX.md)) and the
research docs under `.devclaw/research/`.

---

## v1 — Workflow Automation Rules

**Introduced:** 2026-07-04 (automation-engine slices 1–2; PRs #53–#55)
**Research basis:** `.devclaw/research/workflow-automation.md`

### AutomationRule

An `AutomationRule` is a user-configurable "when X happens and Y is true, do Z"
instruction persisted in the `automation_rules` table.  Key properties:

- `name` — human-readable label.
- `trigger_type` — `"after_save"` (fires inline at the mutation site, same
  transaction) or `"scheduled"` (fires on a time-based cadence; see §v2).
  Default: `"after_save"`.
- `trigger_event` — used by `after_save` rules only: the specific event string that
  arms the rule (e.g. `"deal_stage_changed"`).  Empty string for scheduled rules.
- `conditions_json` — ordered list of `{field, op, value}` triples evaluated
  AND-conjunctively against the entity snapshot.  `NULL` / `"[]"` = unconditional
  fire.  Non-empty but unparseable → `ConditionsParseError` → rule skipped
  (fail-closed; see `_parse_conditions` in `app/services/automations.py`).
- `action_type` — what to do when conditions pass (e.g. `"notify"`).
- `action_config_json` — typed parameters for the action kind.
- `is_active` — `1` = active (evaluated), `0` = disabled (skipped entirely).
- `created_at` — ISO-8601 UTC creation timestamp.

Rules are stateless: they fire every time their trigger + conditions match.  There
is no per-record enrollment history (HubSpot re-enrollment tracking is explicitly
rejected — see `.devclaw/research/workflow-automation.md §2.2 Rejected`).

### After-Save trigger

`after_save` rules fire inline in the route handler, after the domain mutation,
before `db.commit()` — the same position as `create_notification()` and
`record_history()`.  The `trigger_event` string maps to the following events:

| trigger_event          | When it fires                                      |
|------------------------|----------------------------------------------------|
| `deal_created`         | `POST /deals` succeeds                             |
| `deal_stage_changed`   | Stage actually changes (PATCH /stage or /deals)    |
| `deal_assigned`        | `owner_id` changes in PATCH /deals                 |
| `deal_updated`         | Non-structural field (title/value) changes         |
| `contact_created`      | `POST /contacts` succeeds                          |
| `contact_updated`      | Non-empty PATCH /contacts/{id}                     |
| `activity_created`     | `POST /activities` succeeds                        |
| `activity_completed`   | `POST /activities/{id}/complete`                   |

`execute_automation_rules(db, *, trigger_event, context, clk)` in
`app/services/automations.py` is the evaluation entry point: queries active
`after_save` rules, evaluates each rule's conditions against `context` (an entity
snapshot dict), and calls `_execute_action` for rules that match.  No second trigger
mechanism is introduced — ORM hooks and background scanners are explicitly rejected
(same rationale as ADR-0026 and `.devclaw/research/workflow-automation.md §8`).

### Condition

A **Condition** is a single field-value filter: `{field: str, op: str, value: Any}`.
Rules carry a list of conditions evaluated AND-conjunctively (all must pass).
Empty list → unconditional fire.  Supported operators: `eq`, `neq`, `in`.
An unrecognised operator or missing context field evaluates to `False` (fail-closed).

---

## v2 — Scheduled Trigger

**Introduced:** 2026-07-05 (PRs #56–#58; `fix/persist-scheduled-automation-claim-when`)
**Research basis:** `.devclaw/research/workflow-automation.md` — Salesforce Scheduled
Actions / HubSpot Workflow Delay-Step / Zoho Time-Based Action patterns.

### ScheduledTrigger

`trigger_type = "scheduled"` rules fire on a time-based cadence managed by a
background asyncio poller rather than by domain-mutation call sites.  All other rule
properties (`conditions_json`, `action_type`, `action_config_json`, `is_active`)
are shared with `after_save` rules — `trigger_type` is a discriminator on the
single `automation_rules` table, not a second rule concept.

#### schedule_config_json

JSON object stored on the rule row.  Two supported shapes:

```json
{"interval_minutes": 30}
```

Recurring rule — fires every *N* minutes.  `interval_minutes` must be a positive
integer (`bool` and `float` are rejected even though Python's `isinstance` would
otherwise accept `True` as `int`).

```json
{"run_once_at": "2026-08-01T09:00:00"}
```

One-shot rule — fires once when `reference_time >= run_once_at` and
`last_triggered_at IS NULL` (i.e. the rule has never fired).  Once fired the rule
is expired and will not fire again.

Missing, blank, or structurally invalid `schedule_config_json` raises
`ScheduleConfigParseError` in `_parse_schedule_config`; the caller
(`run_scheduled_automations`) catches it and skips the rule — **fail-closed**.
A scheduled rule with no valid config must never fire.

#### last_triggered_at

ISO-8601 UTC string stored on the rule row; `NULL` = the rule has never fired.
Updated atomically by the CAS claim mechanism (see below) before each execution
cycle.  Callers that read an unparseable value log a warning and treat the rule as
never fired (belt-and-suspenders: the CAS mechanism writes the value, so corruption
indicates an external write).

#### is_due() semantics

`is_due(schedule_config, last_triggered_at, reference_time)` in
`app/services/automations.py` is a **pure function** — no I/O, no side effects,
no DB access.  It is the testable seam between the scheduling logic and the poller.

- `interval_minutes` mode:
  - `last_triggered_at is None` → always due (first poll).
  - Otherwise: due when `reference_time >= last_triggered_at + timedelta(minutes=N)`.
- `run_once_at` mode:
  - Due when `last_triggered_at is None AND reference_time >= run_once_at`.
  - Not due (`False`) once `last_triggered_at` is set (rule has already fired; expired).
- Unknown mode → `False` (safe default — unknown kind must never fire).

All datetime comparison strips `tzinfo` so naive and aware datetimes compare without
raising; all stored times are UTC (ADR-0006).

#### CAS claim mechanism (PR #58)

`run_scheduled_automations(db, *, clk)` in `app/services/automations.py` is the
sole execution path for scheduled rules.  Unlike `execute_automation_rules`, it owns
its own DB transactions (the asyncio poller in `app/main.py` is its only caller;
it never runs inline in a request handler).

For each rule that `is_due()` returns `True`, the function uses a
**compare-and-swap (CAS)** atomic `UPDATE` to claim the rule before executing it:

```sql
-- null case (never fired)
UPDATE automation_rules SET last_triggered_at = :new
 WHERE id = :id AND last_triggered_at IS NULL

-- previously-fired case
UPDATE automation_rules SET last_triggered_at = :new
 WHERE id = :id AND last_triggered_at = :old
```

If `rowcount == 0`, another Gunicorn worker already claimed the rule this cycle and
the current worker skips without firing.  SQLite serialises concurrent writers
through its write lock, so exactly one worker's `UPDATE` wins per poll cycle.

**Commit-guard invariant (PR #58's specific fix):** The CAS claim
(`last_triggered_at` UPDATE) is committed to the database *immediately after
`rowcount == 1` is confirmed, **before** condition evaluation*.  This ensures the
claim persists even when conditions subsequently evaluate to `False`.  Without this
`db.commit()`, a `conditions=false` outcome would roll back the `UPDATE` at the end
of the function (inside `if fired: db.commit()`), silently re-exposing the rule as
due on the next poll cycle and defeating the exactly-once guarantee.

Full sequence for each rule in a `run_scheduled_automations` call:

1. `_parse_schedule_config(rule.schedule_config_json)` — `ScheduleConfigParseError`
   → log and skip (fail-closed).
2. Parse `last_triggered_at` from stored ISO-8601 string — unparseable → log
   warning and treat as `None` (never fired).
3. `is_due(config, last_triggered_at, clk.now())` — `False` → skip (not yet due).
4. Issue CAS `UPDATE` → `rowcount == 0` → skip (another worker already claimed).
5. `db.commit()` — claim committed **unconditionally**, before conditions.
6. `_parse_conditions(rule.conditions_json)` — `ConditionsParseError` → log and
   skip (fail-closed; claim is already committed, so the rule is not re-exposed).
7. `evaluate_conditions(conditions, {})` — scheduled rules carry no entity snapshot;
   field-condition rules will not match against `{}` (silently skipped — future
   slice will provide a context dict).
8. `_execute_action(db, rule, {}, clk)`.

#### Reference CRM analogues

| CRM | Scheduled trigger pattern | What CloseLoop borrows |
|-----|--------------------------|------------------------|
| Salesforce | "Scheduled Actions" on Record-Triggered Flows — single `TriggerType` field on the Flow record (`RecordAfterSave` vs `Scheduled`) | `trigger_type` discriminator on a single `automation_rules` table; `last_triggered_at` to prevent double-firing (analogous to Salesforce's per-record scheduled-action state) |
| HubSpot | "Workflow Delay Step (relative to date property)" — `is_active` toggle; conditions re-evaluated at fire time, not at enrollment | `is_active` flag; `is_due()` decoupled from condition evaluation so timing and predicate are separate concerns |
| Zoho | "Time-Based Action" — fail-closed parse of action config; skips rule if config is malformed or missing | Fail-closed `_parse_schedule_config` / `ScheduleConfigParseError`; same pattern as `_parse_conditions` / `ConditionsParseError` for after_save rules |

See `.devclaw/research/workflow-automation.md` for the full reference CRM survey and
the borrowed-vs-rejected rationale.

---

## v3 — Notification

**Introduced:** 2026-07-05 (notifications engine slices 1–3; PRs #41–#47)
**Research basis:** `.devclaw/research/notifications-engine.md`

### Notification

A `Notification` is an in-app alert delivered to a specific recipient user.
It is written by trigger wiring (after-save hooks in route handlers, same
transaction as the domain mutation) and consumed by the pull API.  There is
no WebSocket or Server-Sent Events delivery — the client polls
`GET /notifications` (ADR-0025; Pipedrive / HubSpot pull-model pattern).

**Schema (`notifications` table):**

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `recipient_id` | INTEGER → `users.id` ON DELETE CASCADE | Always set; every notification targets one user |
| `actor_id` | INTEGER → `users.id` ON DELETE SET NULL | Nullable — system events (e.g. `TaskOverdueEvent`) have no human actor |
| `kind` | TEXT NOT NULL | Discriminator key matching a `NotificationEvent` subclass (see `app/core/notifications.py`) |
| `entity_type` | TEXT | `"deal"` / `"activity"` / `"contact"` / `NULL` — navigation target for the frontend |
| `entity_id` | INTEGER | PK of the linked entity; `NULL` for system events with no entity |
| `payload_json` | TEXT NOT NULL | Serialised typed `NotificationEvent`; rendered to a message string at read time via `render_notification()` |
| `read_at` | TEXT | `NULL` = unread; ISO-8601 UTC string when marked read |
| `created_at` | TEXT NOT NULL | ISO-8601 UTC (injected clock, ADR-0006) |

**Composite index:** `(recipient_id, read_at)` — supports the
`WHERE recipient_id = ? AND read_at IS NULL` unread-count query.

**Key design decisions (see `.devclaw/research/notifications-engine.md` §3):**

*Borrowed:*
- **`read_at` timestamp, not a boolean** — HubSpot stores `readAt` (ISO-8601)
  rather than a flag; Attio does the same.  Enables "recently read" ordering
  and an auditable read history.
- **Structured `payload_json`, not a pre-rendered string** — Attio stores a
  typed payload object and renders the message at read time.  Pre-rendered
  strings (HubSpot, Pipedrive) show stale text after entity renames.
  `render_notification()` is pure and independently testable.
- **Pull model** — HubSpot, Pipedrive, and Attio all expose `GET /notifications`
  polled by the client.  No WebSocket or SSE needed (compatible with ADR-0010).
- **Closed `kind` enum** — Pipedrive documents a fixed set of notification types;
  CloseLoop mirrors this as a discriminated-union in `app/core/notifications.py`
  with `_KIND_MAP` as the single source of truth.
- **`actor_id` as a first-class nullable FK** — Attio and Salesforce both surface
  who triggered the notification.  Nullable because system events (overdue tasks)
  have no human actor.
- **`entity_type` + `entity_id`** — Pipedrive and Attio include the linked entity
  so the frontend can navigate to the correct detail page without a join.
- **Unread count as a separate lightweight endpoint** — Pipedrive exposes
  `GET /notifications/get-unread-count`; CloseLoop mirrors as
  `GET /notifications/unread-count`.
- **`MentionEvent` as a first-class kind** — Zoho treats @mention as a distinct
  notification type with its own payload schema.

*Rejected:*
- **Event bus / Streaming API** — Salesforce Bayeux / HubSpot SSE require a
  socket manager and background infrastructure that CloseLoop does not have;
  ADR-0010 prohibits outbound calls.
- **Pre-rendered message string in DB** — HubSpot and Pipedrive store the
  rendered string ("Alex moved Deal X to Proposal"), which becomes stale on
  entity renames.
- **Admin-managed notification type records** — Salesforce lets admins define
  types via the Metadata API; over-engineered for CloseLoop's scope.
- **Background polling workers for overdue-task detection** — Zoho uses
  background jobs; CloseLoop has no worker machinery (creation is lazy /
  synchronous, triggered at the point a query surfaces overdue items).
- **Cursor-based pagination** — Attio uses `after_id`; simple `limit` is
  sufficient for this slice.
- **Day-grouping in the API response** — Zoho groups by date in the response;
  CloseLoop returns a flat list (grouping is a frontend concern).

**Pull API surface (`app/routers/notifications.py`):**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | List current user's notifications, newest first. `?unread_only=true`, `?limit=N` (default 50). |
| GET | `/notifications/unread-count` | `{"unread_count": N}` — lightweight bell-badge query. |
| POST | `/notifications/{id}/read` | Mark one notification read (idempotent). 404 if not found or owned by another user. |
| POST | `/notifications/read-all` | Mark all current user's unread notifications read. Returns 204. |

Notifications are created by service-layer trigger wiring
(`app/services/notifications.py` → `create_notification()`), never by a
public REST endpoint.  Self-notifications are suppressed (actor == recipient).

**Trigger sites (slices 2–3):**
- `app/routers/deals.py` — `StageChangedEvent` on stage change; `DealAssignedEvent` on owner change.
- `app/routers/activities.py` — `MentionEvent` per unique mentioned user when a note is created or its body updated (note type only; call/email/meeting bodies skipped).

**Related files:**
- `app/core/notifications.py` — pure event model, serialisation, rendering, `parse_mentions()`
- `app/services/notifications.py` — `create_notification()` (DB write entry point), `resolve_mentioned_users()`
- `tests/test_core_notifications.py` — pure unit tests (event serialisation, render, parse_mentions)
- `tests/test_notifications.py` — API integration tests
- `tests/test_notification_model.py` — ORM model unit tests (state fields, cascade, SET NULL)
- `tests/test_notification_triggers.py` — after-save trigger wiring tests
- `tests/test_mention_triggers.py` — @mention trigger tests
- [ADR-0025](docs/architecture/decisions/0025-notifications-pull-model.md)
