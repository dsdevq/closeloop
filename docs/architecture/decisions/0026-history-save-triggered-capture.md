---
id: "0026"
title: Activity timeline — save-triggered audit history capture
status: accepted
date: 2026-07-03
owner: "@dsdevq"
tags: [history, audit, data-model, api, architecture]
supersedes: null
superseded-by: null
---

# ADR-0026 — Activity timeline — save-triggered audit history capture

## Context

CloseLoop's domain brief (§7, §9) identifies per-entity activity timelines as a core CRM surface: every deal, contact, and activity should carry an immutable record of what happened and when. This is distinct from the in-app notification centre (ADR-0025):

| Surface | Who reads it | Lifecycle |
|---------|-------------|-----------|
| Notifications (`notifications` table) | Recipient user's inbox | Dismissable; per-user; only created when there is a human recipient |
| Audit history (`history_entries` table) | Anyone with entity access | Append-only; per-entity; created for every domain mutation regardless of who cares |

Five reference CRMs were surveyed in `.devclaw/research/activity-timeline.md`. The key tensions are:

1. **Trigger timing** — write history inline (same transaction as the mutation) vs. async (outbox queue or background worker). Inline is simpler and gives atomic consistency; async requires worker machinery CloseLoop does not have.
2. **Field granularity** — record what happened at the event level (deal stage changed) vs. the field level (field X changed from A to B). Field-level diffing is the richer end-state but requires a before-save snapshot and per-field row emission; deferred to a later slice.
3. **Entity-type routing** — one endpoint per entity type (Pipedrive `GET /deals/{id}/flow`) vs. a single parameterised endpoint (`GET /history?entity_type=deal&entity_id=N`). Single endpoint is simpler and consistent with the `Notification` table shape.
4. **Survivability** — should history rows survive entity deletion? Audit durability says yes. No FK on `entity_id` is the mechanism.

## Decision

### Trigger mechanism — Salesforce Field History Tracking (borrowed)

History rows are written **inline in the FastAPI route handler**, in the same SQLAlchemy transaction as the domain mutation, before `db.commit()`. This is identical to the Salesforce Field History Tracking pattern: when a tracked field changes, Salesforce writes a `FieldHistory` child record in the same save transaction.

This is also the same shape as the notification triggers established in ADR-0025: `record_history()` is called inside the handler, just like `create_notification()`. There is one trigger mechanism in CloseLoop. Adding more trigger sites does not add a new pattern.

**Rejected: outbox / async queue** — write a mutation event to an outbox table; a background worker reads and writes history. Rejected: CloseLoop has no background worker machinery; ADR-0010 prohibits outbound calls.

**Rejected: SQLAlchemy ORM event hooks (`after_flush` / `after_commit`)** — detect field changes automatically from ORM state. Rejected: would introduce a second, hidden trigger mechanism alongside the explicit notification triggers, making the codebase harder to follow.

**Rejected: database-layer CDC** — Zoho uses a CDC layer at the storage level. Rejected: application-layer trigger wiring provides the same semantic guarantees with less infrastructure.

### Typed event model (`app/core/history.py` — ADR-0001 pure module)

A closed discriminated union of twelve dataclasses, each with `kind: Literal["..."]`, mirroring the notifications event model:

| Kind | Trigger point |
|------|--------------|
| `deal_created` | `POST /deals` |
| `deal_stage_changed` | `PATCH /deals/{id}/stage` and `PATCH /deals/{id}` with `stage_id` |
| `deal_assigned` | `PATCH /deals/{id}` when `owner_id` changes |
| `deal_updated` | `PATCH /deals/{id}` for non-structural fields (title, value, etc.) |
| `deal_deleted` | `DELETE /deals/{id}` |
| `contact_created` | `POST /contacts` |
| `contact_updated` | `PATCH /contacts/{id}` |
| `contact_deleted` | `DELETE /contacts/{id}` |
| `activity_created` | `POST /activities` |
| `activity_updated` | `PATCH /activities/{id}` |
| `activity_completed` | `POST /activities/{id}/complete` |
| `activity_deleted` | `DELETE /activities/{id}` |

`_KIND_MAP` is the single source of truth (Pipedrive pattern). `event_to_meta()` / `event_from_meta()` are the serialisation seam.

**Structured payload per kind** — borrowed from Attio's activity stream and HubSpot's Timeline API. Each event carries exactly the fields needed to describe what happened: `DealStageChangedEntry` carries `from_stage`/`to_stage`; `ActivityCreatedEntry` carries `deal_id` and `contact_id`. No catch-all nullable columns.

**No pre-rendered strings** — same rejection as ADR-0025: stale-message problem when entity names change. `meta_json` stores the raw typed event; rendering is a UI concern.

### ORM model (`app/models.py` — `history_entries` table)

```
id           INTEGER PK
entity_type  TEXT NOT NULL     "deal" / "contact" / "activity"
entity_id    INTEGER NOT NULL  no FK — survives entity deletes
actor_id     INTEGER → users(id) ON DELETE SET NULL  (nullable)
kind         TEXT NOT NULL     discriminator; closed enum
meta_json    TEXT NOT NULL     serialised HistoryEvent
occurred_at  TEXT NOT NULL     ISO-8601 UTC (injected clock, ADR-0006)
```

Composite index on `(entity_type, entity_id, occurred_at)` — supports the `WHERE entity_type=? AND entity_id=? ORDER BY occurred_at DESC` pattern.

**`entity_id` has no FK constraint** — Salesforce's audit design intent: history rows are durable audit records that survive deletion of the entity they describe. A `REFERENCES deals(id) ON DELETE CASCADE` would destroy the audit trail when a deal is deleted.

**`actor_id` FK with `ON DELETE SET NULL`** — consistent with the `Notification` model. Nullable because future system-generated entries (e.g., automated stage moves) will have no human actor.

### Service layer (`app/services/history.py`)

`record_history(db, *, entity_type, entity_id, event, clk)` — the single DB-write entry point. `actor_id` is derived from `event.actor_id`. Calls `db.add()` but does NOT commit — caller owns the transaction (same convention as `create_notification`).

### Pull API (`app/routers/history.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/history` | List history entries. Required: `?entity_type=deal&entity_id=N`. Optional: `?limit=N` (default 50). Returns newest first. |

No creation endpoint — history entries are written exclusively by trigger wiring. Consistent with Salesforce, HubSpot, and Attio: the history creation API is internal.

Entity-scoped retrieval borrowed from HubSpot Timeline API and Attio — always filtered to a single entity. Cross-entity aggregation is a later slice.

## Consequences

- **Atomic consistency.** A mutation that fails (DB constraint violation, handler exception) never writes a partial history row — both the mutation and the history entry are rolled back together.
- **Single trigger mechanism.** The `record_history()` call pattern is identical to the existing `create_notification()` pattern. Any engineer who understands one understands the other.
- **Audit durability.** History entries survive entity deletion because `entity_id` has no FK constraint.
- **Field-level diffing deferred.** Slice 3 will add `old_value`/`new_value` per changed field. This slice records the event kind and structured context; the diff is computable from two adjacent `deal_updated` entries and the entity snapshot at that time.
- **No pagination for this slice.** `limit` is sufficient. Cursor-based pagination (`after_id`, borrowed from Attio) is a later optimisation if history grows substantially.

## Alternatives considered

- **Outbox / async queue for history writes** — rejected (no background worker, ADR-0010).
- **SQLAlchemy ORM hooks** — rejected (hidden second trigger mechanism).
- **Database-layer CDC** — rejected (application-layer is simpler, equivalent guarantees).
- **FK on `entity_id`** — rejected (would destroy audit trail on entity delete; audit durability is the point of this table).
- **Pre-rendered `message` string in DB** — rejected (same stale-message problem as in ADR-0025).
- **Per-entity-type route** (`GET /deals/{id}/flow`) — rejected (Pipedrive pattern); single parameterised endpoint is simpler and consistent with the `Notification` table.

## Design pivot: FieldHistory/app/core/timeline.py → HistoryEntry/app/core/history.py

An earlier branch (commit 88855b7, "slice 1 — field-level FieldHistory model") proposed a finer-grained implementation: `app/core/timeline.py` defined a `FieldHistory` dataclass with `field_name`, `old_value`, and `new_value` fields, writing one row per changed field per mutation. This design mirrors Salesforce Field History Tracking at its most literal: every changed field produces a separate `FieldHistory` child record.

**Why superseded by the coarser event-level model shipped in PR #46:**

1. **Field-level diffing requires a before-save snapshot.** To know that `deal.title` changed from "Alpha" to "Beta", the handler must capture the old value before applying the mutation. This adds non-trivial coupling to every route handler and every field that participates in tracking. For slices 1–2, this overhead is not justified by the audit use case being addressed (timeline of what events happened, and when).

2. **Event-level metadata is sufficient for this slice's scope.** A timeline rendered from `DealStageChangedEntry(from_stage="lead", to_stage="qualified")` fully answers the primary audit question — who changed what and when — without per-field rows. The `DealUpdatedEntry` kind captures that non-structural fields were touched; which specific fields changed is the slice 3 enhancement.

3. **One row per mutation, not one row per field.** The event-level model produces a compact, readable timeline: three events for a deal that was created, had its stage changed, and was then renamed. The field-level model would produce potentially dozens of rows for a single PATCH that touches multiple fields — harder to paginate and render efficiently.

**Explicit tradeoff recorded here:** An event-level timeline cannot answer "what was the deal title at 14:32 on Tuesday?" — it can only answer "who changed non-structural fields at 14:32 on Tuesday." Field-level `old_value`/`new_value` diffing (the precise answer) is the slice 3 deliverable, layered on top of the existing event model rather than replacing it. This is a deliberate, argued decision — not a silent replacement of the earlier branch's work.

`app/core/timeline.py` from commit 88855b7 was never merged. `app/core/history.py` is the canonical implementation.
