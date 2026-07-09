---
title: CloseLoop Domain Concepts
status: living
owner: "@dsdevq"
last_reviewed: 2026-07-09
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
- `app/services/automations.py` — `AutomationEvent` when an automation rule with `action_type="notify"` fires (see §v4 AutomationAction).

**Related files:**
- `app/core/notifications.py` — pure event model, serialisation, rendering, `parse_mentions()`
- `app/services/notifications.py` — `create_notification()` (DB write entry point), `resolve_mentioned_users()`
- `tests/test_core_notifications.py` — pure unit tests (event serialisation, render, parse_mentions)
- `tests/test_notifications.py` — API integration tests
- `tests/test_notification_model.py` — ORM model unit tests (state fields, cascade, SET NULL)
- `tests/test_notification_triggers.py` — after-save trigger wiring tests
- `tests/test_mention_triggers.py` — @mention trigger tests
- [ADR-0025](docs/architecture/decisions/0025-notifications-pull-model.md)

---

## v4 — AutomationAction (notify)

**Introduced:** 2026-07-06 (automation engine slice 3)
**Research basis:** `.devclaw/research/notifications-engine.md` §2–3; `.devclaw/research/workflow-automation.md`

### AutomationAction — `notify`

When an `AutomationRule` with `action_type = "notify"` fires (via `execute_automation_rules` or `run_scheduled_automations`), `_execute_notify_action` in `app/services/automations.py` creates an in-app `Notification` row through `create_notification()` — the same service entry point used by the after-save triggers in `app/routers/deals.py` and `app/routers/activities.py`.

**`action_config_json` shape:**

```json
{"recipient_id": 42}
```

Static recipient — always notifies user 42.

```json
{"recipient_field": "owner_id"}
```

Dynamic recipient — resolves `context["owner_id"]` at fire time.  Useful for "notify the deal owner" rules where the owner varies per entity.

**Fail-closed contract:**
- `action_config_json` is not valid JSON or not an object → `ActionConfigParseError` → action skipped (logged at warning), same pattern as `ConditionsParseError` / `ScheduleConfigParseError`.
- No `recipient_id` / `recipient_field` key present, or the resolved value is not a positive integer → no notification, debug log.  `"{}"` is explicitly a valid no-op placeholder (backward-compatible with existing test fixtures).

**Self-notification suppression:** if `context["actor_id"]` equals the resolved `recipient_id`, no notification is created — same guard as the after-save triggers in `app/routers/deals.py`.

**`AutomationEvent` payload (in `app/core/notifications.py`):**

| Field | Type | Description |
|-------|------|-------------|
| `kind` | `"automation"` | Discriminator key |
| `rule_id` | `int` | ID of the `AutomationRule` that fired |
| `rule_name` | `str` | Human-readable rule name at fire time |
| `actor_id` | `int \| None` | User who triggered the after-save event; `None` for scheduled rules |

`render_notification()` produces `'Automation rule "<rule_name>" was triggered'` at read time.  Storing `rule_id`/`rule_name` (not a pre-rendered string) avoids the stale-message problem on rule rename (rejected HubSpot / Pipedrive pattern).

**Reference CRM patterns (borrowed vs. rejected):**

| Pattern | Source | Decision |
|---------|--------|----------|
| Server-side automation notification (not a public REST endpoint) | HubSpot automation engine | Borrowed — `_execute_notify_action` is an internal service call |
| Typed structured payload, not a pre-rendered string | Salesforce Custom Notification Type | Borrowed — `AutomationEvent` dataclass; rendered at read time |
| `actor_id` as a first-class nullable field | Attio | Borrowed — `None` for scheduled rules (no human actor); set from `context["actor_id"]` for after-save rules |
| `entity_type` + `entity_id` for frontend navigation | Pipedrive, Attio | Borrowed — forwarded from `context` to `Notification` row |
| Embedding a full domain event (e.g. `StageChangedEvent`) in the action payload | — | Rejected — couples `action_config_json` to specific domain shapes; `entity_type`/`entity_id` on the Notification row is sufficient for navigation |
| Background worker for dispatch | Zoho | Rejected — action fires inline in `_execute_action`, same transaction as the trigger |

**Related files:**
- `app/services/automations.py` — `_parse_notify_config`, `_resolve_notify_recipient`, `_execute_notify_action`, `_execute_action`
- `app/core/notifications.py` — `AutomationEvent` dataclass, `render_notification()`
- `app/services/notifications.py` — `create_notification()` (shared DB-write entry point)
- `tests/test_automation_notification_action.py` — 36 unit + integration tests

---

## v5 — Activity Timeline / Audit History

**Introduced:** 2026-07-06 (slices 1–2 + 4; PRs #46, #62, #63)
**Research basis:** `.devclaw/research/activity-timeline.md`

### HistoryEntry

A `HistoryEntry` is an immutable append-only record of a domain mutation, stored in the `history_entries` table.  It is distinct from a `Notification`:

| Surface | Who reads it | Lifecycle |
|---------|-------------|-----------|
| `notifications` | Recipient user's inbox | Dismissable; per-user; only when there is a human recipient |
| `history_entries` | Anyone with entity access | Append-only; per-entity; every domain mutation, unconditionally |

Key properties:

- `entity_type` — `"deal"` / `"contact"` / `"activity"`.
- `entity_id` — plain `INTEGER`, **no FK constraint**. History entries survive deletion of the entity they describe (audit durability; Salesforce Field History Tracking pattern).
- `actor_id` — nullable FK → `users(id) ON DELETE SET NULL`. Nullable to accommodate future system-generated entries (e.g. automated stage moves).  Resolved to `actor_name` (User.full_name) in API responses via `joinedload(HistoryEntry.actor)` — single-query eager load, no N+1.
- `kind` — string discriminator; member of the closed enum defined by `_KIND_MAP` in `app/core/history.py`.
- `meta_json` — serialised typed dataclass. Rendered at read time, never pre-rendered as a message string — avoids the stale-label problem on entity renames (HubSpot / Attio pattern).
- `occurred_at` — ISO-8601 UTC, set by the injected clock (ADR-0006).

Composite index on `(entity_type, entity_id, occurred_at)` — supports the canonical `WHERE entity_type=? AND entity_id=? ORDER BY occurred_at DESC` query.

### Closed kind set

`_KIND_MAP` in `app/core/history.py` is the single source of truth for the closed event-kind enum (Pipedrive `GET /deals/{id}/flow` pattern):

| kind | Trigger site |
|------|-------------|
| `deal_created` | `POST /deals` |
| `deal_stage_changed` | `PATCH /deals/{id}/stage` or `PATCH /deals/{id}` when `stage_id` changes |
| `deal_assigned` | `PATCH /deals/{id}` when `owner_id` changes to a non-null user |
| `deal_updated` | `PATCH /deals/{id}` when non-structural fields (title, value) are in the payload |
| `deal_deleted` | `DELETE /deals/{id}` (title snapshotted before `db.delete()`) |
| `contact_created` | `POST /contacts` |
| `contact_updated` | `PATCH /contacts/{id}` when payload is non-empty |
| `contact_deleted` | `DELETE /contacts/{id}` (name snapshotted before `db.delete()`) |
| `activity_created` | `POST /activities` |
| `activity_updated` | `PATCH /activities/{id}` when payload is non-empty |
| `activity_completed` | `POST /activities/{id}/complete` |
| `activity_deleted` | `DELETE /activities/{id}` (fields snapshotted before `db.delete()`) |

### Trigger mechanism

`record_history(db, *, entity_type, entity_id, event, clk)` in `app/services/history.py` is the single DB-write entry point.  It calls `db.add()` but does **NOT** commit — the caller (the route handler) owns the transaction.  Triggers fire inline in the route handler after the domain mutation, before `db.commit()`, mirroring the notification trigger pattern (ADR-0025) and the automation trigger pattern (§v1).  History capture is **unconditional on actor** — unlike notifications, which suppress self-actions, history records every mutation regardless of who performed it.

### Correctness invariants

- Empty-payload PATCH never writes history (guarded in `update_contact`, `update_activity`; non-structural-field guard in `update_deal`).
- `complete_activity` returns HTTP 400 on double-complete; history entry is written exactly once per completion.
- Bulk import (`import_deals`, `import_contacts`) produces one `deal_created` / `contact_created` entry per successfully imported row — the audit trail covers imports.
- Delete handlers snapshot the entity name/title before `db.delete()` so the history entry carries a human-readable label for the now-deleted entity.

### Structured payload (meta_json)

Each typed history event dataclass carries exactly the fields needed to describe the event — no catch-all nullable columns, no flat message string.  `event_to_meta()` serialises to `meta_json`; `event_from_meta()` deserialises back to the typed dataclass.  The UI `renderLabel(kind, meta)` function maps each kind to a human-readable string at read time (HubSpot Timeline API / Attio pattern).

### API surface

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/history` | Bearer | List history entries for a single entity, newest-first. Required: `?entity_type=deal\|contact\|activity` and `?entity_id=N`. Optional: `?limit=N` (default 50). 422 if `entity_type` is unknown or `limit < 1`. Response includes `actor_name` resolved from `User.full_name`. |

No `POST /history` — entries are written exclusively by trigger wiring.  This matches Salesforce, HubSpot, and Attio: the history creation path is internal to the application.

### Timeline UI

`frontend/src/components/EntityTimeline.tsx` is a shared React component: fetches `/history?entity_type=X&entity_id=N` via `apiFetch`, renders a bulleted list of labelled events (kind → human-readable string via `renderLabel`), timestamps, and actor names; handles loading / error / empty states.  Wired into all three detail views: `DealDetailView`, `ContactDetailView`, `ActivityDetailView`.  `HistoryEntry` TypeScript type lives in `frontend/src/types.ts`.

### Reference CRM analogues

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| Save-triggered, same-transaction write | Salesforce Field History Tracking | `record_history()` called inline in route handler, before `db.commit()` |
| History survives entity deletion | Salesforce, Attio | `entity_id` is plain `INTEGER` — no FK constraint |
| `actor_id` on every row (resolved at read time) | Salesforce, Attio | `HistoryEntry.actor_id` nullable FK; `actor_name` resolved via eager join in `GET /history` |
| Structured payload per kind, no pre-rendered string | HubSpot Timeline API, Attio | `meta_json` = serialised typed dataclass; rendered at read time by `renderLabel` |
| Closed enum of event kinds (`_KIND_MAP`) | Pipedrive `GET /deals/{id}/flow` | `_KIND_MAP` in `app/core/history.py` — single source of truth |
| `kind` string as discriminator | Pipedrive, Attio | `kind: Literal["..."]` field on each dataclass; `HistoryEntry.kind` column |
| Entity-scoped retrieval (not cross-entity) | HubSpot Timeline API, Attio | `GET /history?entity_type=deal&entity_id=N` — always a single entity per query |
| No `POST /history` creation endpoint | HubSpot, Attio | Entries written exclusively by trigger wiring |

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Async outbox / event queue for history writes | — | No background worker; ADR-0010 prohibits outbound calls; same-transaction write is simpler and gives atomicity |
| SQLAlchemy ORM hooks (`after_flush` / `after_commit`) | — | Hidden second trigger mechanism; contradicts explicit inline pattern established for notifications and automations |
| Database-layer CDC | Zoho | Application-layer inline wiring gives equivalent atomicity guarantees; no storage infrastructure needed for SQLite single-process model |
| Separate audit microservice | Zoho | No microservice infrastructure; single-process deployment is the product invariant |
| FK on `entity_id` | — | Would cascade-delete history on entity deletion; audit durability is the point |
| Pre-rendered `message` string in DB | HubSpot (older endpoints), Pipedrive variants | Stale-message problem when entities are renamed; `meta_json` + `renderLabel` at read time avoids it |
| Per-entity-type route (`GET /deals/{id}/flow`) | Pipedrive | Single parameterised endpoint is simpler and consistent with the `Notification` pull-API shape |
| Cursor-based pagination (`after_id`) | Attio | `?limit=N` is sufficient for current data volumes; cursor pagination deferred to a later slice |
| Field-level granularity (one row per changed field) | Salesforce Field History Tracking | Deferred to a future slice; event-level entries are sufficient for slices 1–2 and 4 |

See `.devclaw/research/activity-timeline.md` for the full reference CRM survey and the slice-by-slice build plan.

---

## v6 — CI/CD & Deploy

**Introduced:** 2026-07-08 (ESLint gate + deploy documentation; PR on `feat/add-eslint-gate-document-deploy`)
**Research basis:** `.devclaw/research/cicd-deploy.md`

### ContainerImage

CloseLoop is packaged as a **multi-stage Docker image** built by the `Dockerfile` at the repo root. Two stages:

| Stage | Base image | Purpose |
|-------|-----------|---------|
| `frontend-build` | `node:20.18.0-alpine3.21` | `npm ci` + `npm run build` (`tsc -b && vite build`). Writes `app/static/` — the compiled Vite bundle. |
| `runtime` | `python:3.12.9-slim-bookworm` | Installs `requirements-prod.txt` (6 packages only; pytest + httpx excluded). Copies `app/` from the workspace and `app/static/` from `frontend-build`. Runs gunicorn + UvicornWorker. |

Key properties:

- **Non-root user** (`appuser`, UID/GID 1001) — avoids collision with the VPS host `lifekit` user (UID 1000). `/app` and `/data` are `chown`'d before `USER appuser`.
- **Layer ordering** — `COPY requirements-prod.txt` + `RUN pip install` precedes `COPY app ./app`; source-only edits never bust the slow dependency cache.
- **`HEALTHCHECK`** — `curl -fsS http://127.0.0.1:${PORT:-8000}/health`; Docker marks the container unhealthy if the app cannot respond within 5 s (3 retries, 30 s interval, 15 s start period).
- **Loopback binding** — the `docker run` command pins `-p 127.0.0.1:${PORT}:${PORT}`; Tailscale (`tailscale serve --https=8372`) serves the external surface.
- **`DATABASE_URL`** defaults to `sqlite:////data/closeloop.db`. The `/data` path maps to the `closeloop-data` named volume — the database survives a container replacement.
- **Dev deps excluded** — `requirements.txt` (adds pytest + httpx) is never baked into the image. The production image carries only `requirements-prod.txt`. Test-time access is via volume-mount in `ci-docker.yml`.

### ContainerGate

`.github/workflows/ci-docker.yml` is a separate CI job (runs on every PR and push) that validates the **exact binary that ships**, not just the Python source:

1. Build `closeloop:<sha>` + `closeloop:test-cache` using `--cache-from closeloop:test-cache`.
2. Volume-mount `tests/` and `requirements.txt` (excluded from the image by `.dockerignore`) into the built container.
3. Run `python -m pytest -q --ignore=tests/test_e2e_playwright.py tests/` inside the container as root (acceptable for a throwaway test container; the image still runs as `appuser` in production).
4. Remove the `<sha>` tag; keep `:test-cache` for the next run.

Playwright tests are excluded because Chromium is not in the Python runtime image — those run in the `ci.yml` test job against the source tree. The `:test-cache` tag is kept separate from `:latest` (the deploy tag) and they are never mixed.

### DeployContract

**Trigger:** every push to `main` runs the `deploy` job in `.github/workflows/ci.yml`, gated on the `test` job passing. The `test` job runs: pytest → `npm run typecheck` (`tsc -b`) → `npm run lint` (ESLint).

**Container-swap sequence:**

1. **Record** the running container's image SHA (`docker inspect closeloop --format '{{.Image}}'`). Empty string on first deploy.
2. **Build** `closeloop:<commit-sha>` + `closeloop:latest` using `--cache-from closeloop:latest` — before stopping the old container, keeping the outage window to milliseconds.
3. **Swap** — `docker rm -f closeloop || true` then `docker run -d --name closeloop --restart unless-stopped -p "127.0.0.1:${PORT}:${PORT}" -e PORT -v closeloop-data:/data closeloop:<sha>`.
4. **Verify** — poll `GET http://127.0.0.1:${PORT}/health` up to 30 × 2 s. Exit 0 on first success; exit 1 if never healthy.
5. **Rollback** — if step 4 fails and step 1 captured a prior SHA: restore the prior container from that SHA and re-pin `:latest`.
6. **Prune** — `docker image prune -f` always runs (`if: always()`).

**Concurrency:** `group: deploy-closeloop, cancel-in-progress: false` — concurrent deploys queue rather than cancel; a mid-swap cancellation would leave the service down.

**Ownership boundary:** devclaw's `_project_owns_its_deploy` check (in `devclaw/goal/tick.py`) detects the `Dockerfile` at the workspace root and skips its own auto-deploy. One merge → one deploy from closeloop's own CI. No devclaw-spun throwaway containers accumulate on the VPS.

**Invariants callers can rely on:**

- `closeloop-data:/data` is preserved across every swap — the database never loses data on deploy.
- `GET /health` is the stable health probe surface: `{"status": "ok", "db": "ok", "version": "...", "timestamp": "..."}`.
- `:latest` always reflects the currently running container after a successful deploy.
- Automatic rollback requires a prior successful deploy (prior SHA must be non-empty).

### Reference CRM analogues

**Borrowed:**

| Pattern | Source | How used in CloseLoop |
|---------|--------|----------------------|
| Test inside the production container | HubSpot (CI job runs the same image that ships) | `ci-docker.yml` volume-mounts `tests/` + `requirements.txt` into the built image; pytest runs inside |
| Build before stop | HubSpot, Pipedrive | `docker build` precedes `docker rm -f` — the old container keeps serving during the image build |
| SHA-tagged image for rollback | Pipedrive (ECR + per-commit tag) | Each deploy produces `closeloop:<commit-sha>`; prior SHA is snapshotted before building; used to restore if health check fails |
| Singleton container swap | Attio (single-tenant VPS, stop/start pattern) | `docker rm -f closeloop \|\| true` + `docker run -d --name closeloop` — atomic swap via named container |
| Health-check gate before declaring success | Attio, HubSpot (readiness probe) | Poll `GET /health` 30 × 2 s; declare failure and trigger rollback if never healthy |
| Prune dangling images after swap | Attio, Zoho | `docker image prune -f` on `if: always()` |
| Named volume for data persistence | Zoho (Docker Compose named volume) | `closeloop-data:/data` survives every container replacement |
| `--restart unless-stopped` | Zoho Compose | Container auto-restarts after VPS reboots without a compose daemon |
| `--cache-from :latest` for layer reuse | HubSpot (registry cache), Pipedrive (ECR cache) | `--cache-from closeloop:latest` (deploy job), `--cache-from closeloop:test-cache` (container gate) |

**Rejected:**

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Kubernetes + Helm rolling deploy | HubSpot (internal k8s) | Single-VPS deployment; no cluster infrastructure |
| AWS ECS task-definition swap | Pipedrive | No external AWS infrastructure; images built and stored on the runner VPS |
| Docker Compose | Zoho self-hosted tier | No multi-container dependency; direct `docker run` is simpler and matches the devclaw pattern |
| Blue/green with a load balancer | Salesforce/HubSpot production | Overkill for a singleton deployment; brief outage during swap is acceptable |
| Per-PR ephemeral review containers | Salesforce (Heroku review apps) | No infra for per-PR containers on `lifekit-vps` |
| Container registry push (ECR / GCR) | Pipedrive, HubSpot | No external registry; images built and stored on the runner VPS |
| ESLint inside the container or Dockerfile | — | ESLint is a dev-time Node tool; the Python runtime image has no Node. Runs in the `test` job against the source tree |
| Build test deps into the production image | — | `requirements.txt` (adds pytest + httpx) is never baked into `requirements-prod.txt`; kept out of the shipped binary entirely |

See `.devclaw/research/cicd-deploy.md` for the full reference CRM survey and the rationale behind each choice.

---

## v7 — Workflow Automation (Phase 2 complete: wiring + CRUD + UI)

**Introduced:** 2026-07-09 (Phase 2 — after-save router wiring, CRUD API, frontend rule manager; `feat/wire-after-save-triggers-add-crud-api`)
**Research basis:** `.devclaw/research/workflow-automation.md`

This section synthesises the complete workflow automation engine now that Phase 2 is shipped. The concepts introduced piecemeal in §v1 (AutomationRule, After-Save trigger, Condition), §v2 (ScheduledTrigger), and §v4 (AutomationAction `notify`) are restated here as a unified Trigger → Condition → Action execution model and tied explicitly to the Notification system (§v3) and Activity Timeline (§v5).  §v1–§v4 remain authoritative for per-concept detail; this section documents the integration invariants and the Phase 2 additions (CRUD API, frontend).

---

### Unified execution model: Trigger → Condition → Action

Every automation rule encodes exactly one "when X happens and Y is true, do Z" instruction.  The three phases of execution never change:

```
  Domain mutation
       │
       ▼
  record_history()          ← history entry written (§v5)
       │
       ▼
  create_notification()     ← hardcoded alert, if applicable (§v3)
       │
       ▼
  execute_automation_rules()← user-defined rules evaluated here
       │
       ▼
  db.commit()               ← single commit; all writes atomic
```

This call order is the invariant.  All three steps share the same SQLAlchemy session and commit.  `execute_automation_rules()` is never called before `record_history()`, ensuring the audit trail is always written regardless of what rules match.  If the commit fails, no notification, no history entry, and no automation side-effect is persisted.

#### After-save rules

For `trigger_type = "after_save"` rules, `execute_automation_rules(db, *, trigger_event, context, clk)` in `app/services/automations.py` is the evaluation entry point:

1. Query `automation_rules` for rows where `trigger_event = ?` AND `trigger_type = "after_save"` AND `is_active = 1`.
2. For each matching rule, parse `conditions_json` via `_parse_conditions()` — `ConditionsParseError` → skip (fail-closed).
3. Call `evaluate_conditions(conditions, context)` — pure function, no DB I/O.  Returns `False` on first non-matching condition (AND-conjunctive).
4. If conditions pass, dispatch to `_execute_action(db, rule, context, clk)`.
5. Return a count of rules that fired (used in tests).

The `context` dict is the entity snapshot at the moment of mutation.  It is built by the route handler from the entity fields after the mutation has been applied (post-`db.flush()`, pre-`db.commit()`).  Every context dict must include `actor_id`, `entity_type`, and `entity_id` — these are required by `_execute_notify_action` to populate the `Notification` row's navigation fields.

#### Scheduled rules

For `trigger_type = "scheduled"` rules, `run_scheduled_automations(db, *, clk)` is the execution path.  It is called exclusively by the `_scheduled_automations_loop()` asyncio task in `app/main.py` (FastAPI lifespan, polling every 60 s).  Unlike after-save rules, the scheduler owns its transactions and passes an empty `context = {}` (no entity snapshot).  See §v2 for the full CAS claim sequence and commit-guard invariant.

---

### After-save trigger sites (Phase 2 — all 8 wired)

`execute_automation_rules()` is now called inline at every domain-mutation site, immediately after `record_history()` and any `create_notification()` call, before `db.commit()`:

| trigger_event | Router + handler | Context keys included |
|--------------|------------------|-----------------------|
| `deal_created` | `deals.py` → `create_deal` | `deal_id`, `deal_title`, `stage`, `value`, `owner_id`, `actor_id`, `entity_type="deal"`, `entity_id` |
| `deal_stage_changed` | `deals.py` → `update_deal_stage`, `update_deal` | `deal_id`, `deal_title`, `stage` (new), `old_stage`, `value`, `owner_id`, `actor_id`, `entity_type`, `entity_id` |
| `deal_assigned` | `deals.py` → `update_deal` | `deal_id`, `deal_title`, `owner_id` (new), `old_owner_id`, `actor_id`, `entity_type`, `entity_id` |
| `deal_updated` | `deals.py` → `update_deal` | `deal_id`, `deal_title`, `stage`, `value`, `owner_id`, `actor_id`, `entity_type`, `entity_id` |
| `contact_created` | `contacts.py` → `create_contact` | `contact_id`, `contact_name`, `owner_id`, `actor_id`, `entity_type="contact"`, `entity_id` |
| `contact_updated` | `contacts.py` → `update_contact` | `contact_id`, `contact_name`, `owner_id`, `actor_id`, `entity_type`, `entity_id` |
| `activity_created` | `activities.py` → `create_activity` | `activity_id`, `activity_type`, `deal_id`, `contact_id`, `actor_id`, `entity_type="activity"`, `entity_id` |
| `activity_completed` | `activities.py` → `complete_activity` | `activity_id`, `activity_title`, `deal_id`, `contact_id`, `actor_id`, `entity_type`, `entity_id` |

The trigger event vocabulary is drawn from the same closed set as `_KIND_MAP` in `app/core/history.py` — no new event taxonomy is introduced.  `trigger_event` strings used for automation rules are a subset of the history kind strings (delete events are excluded because the entity is gone before the context dict could be populated).

---

### Integration with the Notification system (§v3)

**There is no separate notification pipeline for automation-fired alerts.**  When a rule with `action_type = "notify"` matches:

1. `_execute_action` dispatches to `_execute_notify_action` in `app/services/automations.py`.
2. `_execute_notify_action` calls `create_notification(db, *, recipient_id, event, entity_type, entity_id, clk)` from `app/services/notifications.py` — the **same** DB-write entry point used by the hardcoded after-save triggers in `deals.py` and `activities.py`.
3. The resulting `Notification` row lands in the `notifications` table with `kind = "automation"` and an `AutomationEvent` payload (see §v4 for the payload schema).
4. The row is read by `GET /notifications` exactly like any other notification.
5. Self-notification suppression (`actor_id == recipient_id`) is inherited from `create_notification()` — no additional guard is needed in the automation layer.

**Integration invariants:**

- `_execute_notify_action` is a caller of `create_notification()`, not an alternative implementation of it.
- Automation-fired notifications are not distinguishable from hardcoded notifications at the DB or API level — only `kind = "automation"` and the `AutomationEvent` payload identify their origin.
- The `notifications` table has exactly one write path: `create_notification()`.  The automation layer adds a new *caller* of that path, not a new path.

**Reference:** Attio's "Notify a team member" automation action calls the same internal notification service as hardcoded triggers; Salesforce Custom Notifications are also created via the same `Notification` object regardless of whether the writer is a Flow, an Apex trigger, or platform code.

---

### Integration with the Activity Timeline (§v5)

**There is no parallel history-capture mechanism for automation executions.**  The integration between automation rules and the activity timeline is positional: `execute_automation_rules()` is called at the same 8 trigger sites where `record_history()` is called, in the same transaction.

Key integration properties:

- **Automation rules do not write history entries.** The `record_history()` call captures the domain mutation (e.g., `deal_stage_changed`) regardless of whether any rule matches. The automation's side-effect (a notification) is not itself recorded in `history_entries`.
- **Both are atomic with the mutation.** `record_history()` calls `db.add()` (no commit); `execute_automation_rules()` calls `_execute_notify_action` which calls `create_notification()` which calls `db.add()` (no commit). All writes are committed together via the single `db.commit()` at the end of the route handler.
- **Automation failures do not suppress history.** If `execute_automation_rules()` raises an unexpected exception and the transaction rolls back, `record_history()` also rolls back — consistent with the general atomicity invariant. The converse also holds: a `ConditionsParseError` that causes a rule to be skipped does not prevent `record_history()` from writing.
- **Call order is history-first.** `record_history()` is always called before `execute_automation_rules()`. If a handler does not call `record_history()` (e.g., delete events, which snapshot fields before `db.delete()`), `execute_automation_rules()` is also not called at that site — delete events are not in the trigger event vocabulary.

**Reference:** Salesforce Record-Triggered Flows fire after the `FieldHistory` rows are written in the same transaction; the audit trail is populated unconditionally before automation actions run.

---

### CRUD API (`app/routers/automation_rules.py`)

Rules are managed via a REST API restricted to admin and manager roles (`_require_admin_or_manager`, same pattern as `app/routers/pipeline.py`):

| Method | Path | Status | Description |
|--------|------|--------|-------------|
| GET | `/automation-rules` | 200 | List all rules, ordered by `created_at DESC`. |
| POST | `/automation-rules` | 201 | Create a rule. Validates `trigger_type`, `trigger_event`, `action_type`, condition ops, `schedule_config_json`. HTTP 422 for all semantic failures (ADR-0002). |
| GET | `/automation-rules/{id}` | 200 | Get a single rule by ID. 404 if not found. |
| PATCH | `/automation-rules/{id}` | 200 | Update `name`, `trigger_event`, `conditions_json`, `action_config_json`, `schedule_config_json`, `is_active`. 404 if not found. 422 for invalid values. |
| DELETE | `/automation-rules/{id}` | 204 | Delete a rule. 404 if not found. `Response(status_code=204)` (ADR: use `Response`, not plain return). |

**Validation contract (fail-closed, consistent with `app/services/automations.py`):**
- `trigger_type` must be `"after_save"` or `"scheduled"`.
- `trigger_event` must be in the known event vocabulary for `after_save` rules; empty for `scheduled` rules.
- `action_type` must be in `_KNOWN_ACTION_TYPES` (`{"notify"}` as of Phase 2).
- `conditions_json` conditions must use known ops (`eq`, `neq`, `in`) and include `field` and `value` keys.
- `action_config_json` is validated via `_parse_notify_config` for `notify` action type.
- `schedule_config_json` is validated via `_parse_schedule_config` for `scheduled` rules.

This router is for managing rule *definitions* only — it does not trigger rule execution. Rule execution is performed exclusively by the after-save wiring in route handlers and by `run_scheduled_automations()` called from the asyncio poller.

---

### Frontend (`frontend/src/features/automations/AutomationRulesView.tsx`)

`AutomationRulesView` is a self-contained form-based admin panel: lists existing rules, creates new rules via an inline form, toggles `is_active`, and deletes rules. It is visible only when the authenticated user has `role = "admin"` or `role = "manager"`. Wired as the `"automations"` tab in `AppHeader` and `App.tsx`. Uses `apiFetch` (not bare `fetch`; ADR requirement).

---

### Reference CRM patterns (Phase 2 additions)

| Pattern | Source | Decision |
|---------|--------|----------|
| CRUD admin UI, not a visual canvas | Zoho Workflow Rules (form-based UI) | Borrowed — `AutomationRulesView` is a form-based list + create panel; visual canvas (Salesforce Flow Builder, HubSpot workflow canvas) rejected as expensive and out of scope |
| Single-object-type scope per rule via trigger_event | HubSpot (each workflow scoped to one object type) | Borrowed implicitly — `trigger_event` string carries the entity type (`deal_stage_changed` can only fire from `deals.py`); explicit `entity_type` column deferred |
| `is_active` toggle | HubSpot, Pipedrive | Borrowed — admin UI surfaces the toggle; inactive rules are excluded at the DB query level |
| Admin/manager-only write access | HubSpot (admin-managed workflows) | Borrowed — `_require_admin_or_manager` guards all write endpoints; rep role cannot manage rules |
| CRUD validation at rule creation time | Zoho (workflow rule editor validates config before save) | Borrowed — `POST /automation-rules` validates all config at write time, so a malformed rule never reaches the evaluator |
| Notify action as internal service call, not a public endpoint | HubSpot, Attio | Borrowed — `_execute_notify_action` calls `create_notification()` internally; there is no `POST /automation-rules/trigger` or `POST /notifications` public endpoint |
| Multi-action sequences within a single rule | HubSpot, Pipedrive, Zoho | Rejected — one action per rule; multiple outcomes compose via multiple rules, no per-rule branching or sequencing |
| Rule execution log (`automation_executions` table) | HubSpot (workflow enrollment history), Salesforce | Deferred — a future `automation_executions` table with `fired_at`, `outcome`, and error details is planned but not implemented; no execution log exists in Phase 2 |
| `create_activity` action type | Pipedrive ("Create activity" automation action), Zoho ("Create task" action) | Deferred — planned as the next action type; not yet implemented; guard against recursion required (automated Activity must suppress its own `activity_created` trigger) |

**Rejected patterns affecting integration specifically:**

| Pattern | Source | Why rejected |
|---------|--------|-------------|
| ORM hooks (`after_flush` / `after_commit`) as trigger mechanism | SQLAlchemy | Creates a hidden second trigger path alongside the explicit inline calls; contradicts ADR-0026 and the established After-Save hook discipline; trigger sites must be explicit and traceable |
| Background scanner for after-save trigger detection | Zoho, general pattern | No background worker machinery; scanner would create a parallel event pipeline competing with the inline hook; same rejection rationale as `activity-timeline.md §3` and ADR-0026 §Rejected alternatives |
| Separate notification table for automation-fired alerts | — | Rejected by design: `create_notification()` is the single write path; automation is a new caller, not a new path; separate table would create two notification stores with divergent read APIs |
| Webhook / HTTP action dispatched from `_execute_action` | Pipedrive, HubSpot, Zoho, Attio | ADR-0010 prohibits runtime outbound network calls |

See `.devclaw/research/workflow-automation.md` for the full reference CRM survey and the complete borrowed-vs-rejected rationale behind the rule model and condition evaluator design.
