---
title: CloseLoop Domain Concepts
status: living
owner: "@dsdevq"
last_reviewed: 2026-07-04
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

**Introduced:** 2026-07-04 (PR: workflow-automation slice 1)
**Research basis:** `.devclaw/research/workflow-automation.md`

### Rule

An `AutomationRule` is a user-configurable "when X happens and Y is true, do Z"
instruction persisted in the `automation_rules` table.  Each rule is scoped to a
single entity type and fires at most once per domain mutation (no re-entrancy).

Key properties:
- `name` — human-readable label.
- `entity_type` — `"deal"` / `"contact"` / `"activity"`.  A rule scoped to
  `"deal"` is *never* evaluated during a contact or activity mutation.
- `trigger_kind` — the specific event that arms the rule (see **Trigger** below).
- `conditions_json` — ordered list of `{field, op, value}` triples evaluated
  AND-conjunctively against an entity snapshot.  Empty list = unconditional fire.
- `action_kind` — what to do when conditions pass (`"notify_user"` in slice 1;
  `"create_activity"` in slice 2).
- `action_params_json` — typed parameters for the action (see **Action** below).
- `is_active` — `1` = active (evaluated), `0` = disabled (skipped entirely).
- `created_by_id` → `users.id` ON DELETE SET NULL — rules survive user deletion.

Rules are stateless: they fire every time their trigger + conditions match.  There
is no per-record enrollment history (HubSpot re-enrollment tracking is explicitly
rejected — see `.devclaw/research/workflow-automation.md §2.2 Rejected`).

### Trigger

A **Trigger** is the combination of `entity_type` + `trigger_kind` that identifies
when a rule is eligible to fire.  The `trigger_kind` vocabulary is the closed set
drawn from `app/core/history._KIND_MAP` (Pipedrive/Salesforce closed trigger-event-enum
pattern) — no separate trigger taxonomy is defined for automation:

| trigger_kind           | entity_type | When it fires                                  |
|------------------------|-------------|------------------------------------------------|
| `deal_created`         | deal        | `POST /deals` succeeds                         |
| `deal_stage_changed`   | deal        | Stage actually changes (PATCH /stage or /deals)|
| `deal_assigned`        | deal        | `owner_id` changes in PATCH /deals             |
| `deal_updated`         | deal        | Non-structural field (title/value) changes     |
| `deal_deleted`         | deal        | `DELETE /deals/{id}` (wired in slice 3)        |
| `contact_created`      | contact     | `POST /contacts` succeeds                      |
| `contact_updated`      | contact     | Non-empty PATCH /contacts/{id}                 |
| `contact_deleted`      | contact     | `DELETE /contacts/{id}` (wired in slice 3)     |
| `activity_created`     | activity    | `POST /activities` succeeds                    |
| `activity_completed`   | activity    | `POST /activities/{id}/complete`               |
| `activity_updated`     | activity    | Non-empty PATCH /activities/{id} (slice 3)     |
| `activity_deleted`     | activity    | `DELETE /activities/{id}` (slice 3)            |

Triggers fire **After-Save**: inline in the route handler, after the domain mutation,
before `db.commit()` — the same position as `create_notification()` and
`record_history()`.  There is no separate trigger mechanism (ORM hooks, background
scanner, pub/sub bus — all explicitly rejected, same rationale as ADR-0026).

**Scheduled/time-based triggers are permanently out of scope**: CloseLoop has no
background worker and ADR-0010 prohibits runtime outbound network calls.

### Condition

A **Condition** is a single field-value filter: `{field: str, op: str, value: Any}`.
Rules carry a list of conditions evaluated AND-conjunctively (all must pass).
Empty list → unconditional fire.

Supported operators (`app/core/automations.SUPPORTED_OPS`):

| op         | Semantics                                          | Attio equivalent   |
|------------|----------------------------------------------------|--------------------|
| `eq`       | `actual == expected`                               | `equals`           |
| `neq`      | `actual != expected`                               | `not_equals`       |
| `gt`       | `actual > expected` (None → False)                 | `greater_than`     |
| `lt`       | `actual < expected` (None → False)                 | `less_than`        |
| `contains` | `str(expected).lower() in str(actual).lower()`     | `contains`         |

OR-logic / complex boolean expression trees are explicitly rejected (slice 1 covers
the vast majority of practical CRM automation patterns with AND-only).

The **entity snapshot** passed to condition evaluation is a plain `dict[str, Any]`
built from the entity's field values at the time of the mutation.  Snapshot shape
per entity type:

*Deal snapshot:*
`{title, value, stage, stage_id, owner_id, contact_id, probability, from_stage}`

*Contact snapshot:*
`{name, email, phone, company, owner_id, lead_score}`

*Activity snapshot:*
`{title, type, deal_id, contact_id, owner_id, completed_at}`

### Action

An **Action** is the side effect executed when a rule's trigger fires and all
conditions pass.  Each rule carries exactly one action (`action_kind` +
`action_params_json`).  Multiple outcomes are composed by having multiple rules
with the same trigger — no branching or chaining within a single rule.

#### `notify_user` (slice 1)

Send an in-app notification to a specified user via the existing
`create_notification()` service — automation is a new *caller* of the existing
notification path, not a new one.

`action_params_json` shape:
```json
{
  "recipient_id": 42,
  "message_template": "Deal {title} moved to {stage}"
}
```

- `recipient_id` — PK of the target User row.
- `message_template` — Python `str.format_map` template rendered against the entity
  snapshot at fire time.  Unknown placeholders are preserved as-is.

Self-notification suppression applies: if `recipient_id == actor.id`, the
notification is silently skipped (HubSpot / Zoho pattern).

The resulting `Notification` row carries `kind = "automation_triggered"` and a
pre-rendered `message` in `payload_json` (`AutomationTriggeredEvent` in
`app/core/notifications.py`).

#### `create_activity` (slice 2 — not yet implemented)

Auto-create an activity/task when the rule fires.

`action_params_json` shape (preview):
```json
{
  "title": "Follow-up call",
  "type": "call",
  "assigned_to_actor": true,
  "due_offset_days": 2
}
```
