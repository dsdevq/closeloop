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

## v3 — Activity Timeline / Audit History

**Introduced:** 2026-07-06 (slices 1–2 + 4; PRs #46, #60, #61)
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

`frontend/src/components/EntityTimeline.tsx` is a shared React component: fetches `/history?entity_type=X&entity_id=N` via `apiFetch`, renders a bulleted chronological list with event label, timestamp, and actor name; handles loading / error / empty states.  Wired into `DealDetailView`, `ContactDetailView`, and `ActivityDetailView`.  `HistoryEntry` TypeScript type lives in `frontend/src/types.ts`.

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
