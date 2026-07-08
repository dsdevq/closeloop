# Activity Timeline — Reference CRM Research & Design Synthesis

**Status:** Accepted — implementation complete through slices 1–2 (typed event model, trigger wiring) and slice 4 (timeline UI + actor resolution). Slice 3 (field-level diffing) remains deferred.
**Date:** 2026-07-03
**Scope of this doc:** Reference CRM survey, borrowed/rejected patterns, and slice-by-slice build plan for CloseLoop's entity-scoped audit history (activity timeline).

---

## 1. What We're Building and Why

CloseLoop's domain brief (§7, §9) identifies per-entity activity timelines as a core CRM surface: every deal, contact, and activity should carry an immutable record of what happened and when. This is **distinct** from the in-app notification centre (ADR-0025):

| Surface | Who reads it | Lifecycle |
|---------|-------------|-----------|
| Notifications (`notifications` table) | Recipient user's inbox | Dismissable; per-user; only created when there is a human recipient |
| Audit history (`history_entries` table) | Anyone with entity access | Append-only; per-entity; created for every domain mutation regardless of who cares |

The key design tensions:

1. **Trigger timing** — write history inline (same transaction as the mutation) vs. async (outbox queue or background worker). Inline is simpler and gives atomic consistency; async requires worker machinery CloseLoop does not have.
2. **Field granularity** — record what happened at the event level ("deal stage changed") vs. the field level ("field X changed from A to B"). Field-level diffing is the richer end-state but requires a before-save snapshot and per-field row emission; deferred to slice 3.
3. **Entity-type routing** — one endpoint per entity type (`GET /deals/{id}/flow`) vs. a single parameterised endpoint (`GET /history?entity_type=deal&entity_id=N`). Single endpoint is simpler and consistent with the `Notification` table shape.
4. **Survivability** — should history rows survive entity deletion? Audit durability says yes. No FK on `entity_id` is the mechanism.

---

## 2. Reference CRM Survey

Five reference CRMs were surveyed. The patterns borrowed and rejected are summarised in §3.

### 2.1 Salesforce (Sales Cloud — Field History Tracking)

**History model:** Salesforce Field History Tracking writes a `FieldHistory` child record **in the same save transaction** as the mutation that triggered it. When a tracked field changes on a record, Salesforce inserts the `FieldHistory` row before the transaction commits. There is no async queue, no background listener — the capture is synchronous and atomic with the mutation.

**Key patterns borrowed:**
- **Same-transaction write (save-triggered capture).** History is written inline, in the same SQLAlchemy transaction as the domain mutation, before `db.commit()`. If the mutation rolls back, the history row rolls back with it — atomic consistency guaranteed. CloseLoop's `record_history()` call sits immediately after the mutation in the route handler, mirroring this pattern exactly.
- **`FieldHistory` child survives parent deletion.** Salesforce's audit intent is that history records are durable beyond the entity's lifecycle. CloseLoop implements this by storing `entity_id` as a plain `INTEGER` with no FK constraint — history entries survive entity deletion.
- **Actor on every row.** Salesforce always records which user triggered the change. CloseLoop carries `actor_id` on every `HistoryEntry`.

**Rejected from Salesforce:**
- **Field-level granularity (one row per changed field).** Salesforce Field History Tracking writes one `FieldHistory` row per changed field. CloseLoop's slice 2 records one event per *mutation* (e.g., `deal_updated` rather than separate rows for title, value). Field-level diffing is the roadmap for slice 3.
- **Trigger configuration as admin metadata.** In Salesforce, Field History Tracking is configured per-object via the Metadata API. CloseLoop wires triggers in code at the call site — no admin-managed records, no configuration layer.

---

### 2.2 HubSpot CRM (Timeline API)

**History model:** HubSpot's Timeline API lets integrations write structured timeline events against a contact or deal. Each event carries a `eventTemplateId` (discriminator), an `objectId` (entity FK), a `timestamp`, and a strongly-typed `extraData` object. The shape of `extraData` is different per event type. HubSpot stores the raw payload and renders the event description from it at read time.

**Key patterns borrowed:**
- **Structured `extraData` per kind (no pre-rendered string).** HubSpot stores the raw structured payload, not a rendered message like "Alex moved Deal X to Proposal." If deal titles are renamed, the timeline event is not stale — it is rendered fresh from the payload. CloseLoop stores `meta_json` (serialised typed dataclass) and renders at read time. The `event_to_meta()` / `event_from_meta()` functions are the serialisation seam.
- **Entity-scoped retrieval.** HubSpot's Timeline API is always scoped to a single entity (`GET /crm/v3/objects/deals/{id}/activities`). CloseLoop's `GET /history?entity_type=deal&entity_id=N` is the same shape — always entity-scoped, newest first.
- **No creation endpoint in the public API surface.** HubSpot's Timeline event creation is an internal integration concern; the pull API is what UI consumers use. CloseLoop has no `POST /history` — entries are written exclusively by trigger wiring.

**Rejected from HubSpot:**
- **Per-entity-type path (`GET /crm/v3/objects/{objectType}/{id}/activities`).** HubSpot uses one path segment per object type. CloseLoop uses a single parameterised `GET /history?entity_type=...` endpoint — consistent with the `Notification` table shape and simpler to extend.

---

### 2.3 Attio

**History model:** Attio is the most modern reference CRM for this feature. Each record carries an activity stream with a `notification_type` discriminator and a strongly-typed `payload` object (different schema per type). Attio uses cursor-based pagination (`after_id`) and always surfaces the actor who triggered the activity. History entries survive record deletion.

**Key patterns borrowed:**
- **Structured payload per kind.** Attio's activity stream entries carry a typed payload (`{from_stage, to_stage, deal_id, actor_id}` for stage changes, etc.) — no catch-all nullable columns, no flat message string. CloseLoop implements this as a closed discriminated union: `DealStageChangedEntry(from_stage=..., to_stage=...)`, etc.
- **`actor_id` as a first-class field.** Attio always surfaces who triggered the activity. CloseLoop carries `actor_id` (nullable FK to `users`) on every `HistoryEntry`.
- **History entries survive record deletion.** Attio retains activity stream entries after a record is archived. CloseLoop enforces this by using no FK on `entity_id`.
- **No pre-rendered `message` string in DB.** Same as HubSpot — Attio renders the activity description at read time. CloseLoop stores `meta_json` and renders in the UI layer.

**Rejected from Attio:**
- **Cursor-based pagination (`after_id`).** Attio uses cursor pagination for large history streams. CloseLoop uses a simple `?limit=N` parameter for this slice; cursor pagination is a later optimisation if history grows substantially.
- **Cross-record aggregation view.** Attio provides a global activity feed across all records. CloseLoop's `GET /history` is always scoped to a single entity. Cross-entity aggregation is a later slice.

---

### 2.4 Pipedrive

**History model:** Pipedrive exposes a per-deal activity and history feed (`GET /deals/{id}/flow`) that returns a mix of activity events and field-change log entries. Each entry has a `object` discriminator and a typed payload. The set of event types is documented as a closed enum.

**Key patterns borrowed:**
- **Closed enum of event kinds (`_KIND_MAP`).** Pipedrive documents a fixed, versioned set of history event types. The frontend knows exactly which event types can appear and renders them accordingly. CloseLoop implements this as `_KIND_MAP` in `app/core/history.py` — the single source of truth for the closed kind set, mirroring the notifications engine's `_KIND_MAP`.
- **`kind` string as discriminator.** Pipedrive's `object` field is the discriminator. CloseLoop's `kind: Literal["..."]` on each dataclass serves the same role.

**Rejected from Pipedrive:**
- **Per-entity-type route (`GET /deals/{id}/flow`, `GET /contacts/{id}/flow`).** Pipedrive has separate endpoints per entity type. CloseLoop uses a single `GET /history?entity_type=deal&entity_id=N` endpoint — the `entity_type` parameter generalises across entity types without multiplying routes.

---

### 2.5 Zoho CRM

**History model:** Zoho uses a Change Data Capture (CDC) layer at the storage level: field changes are captured by the storage engine before surfacing to the application. The CDC layer emits structured change events that the audit history pipeline consumes. Zoho also has an in-app activity timeline per record.

**Key patterns borrowed:**
- **CDC as a concept (not the implementation).** Zoho's CDC approach demonstrates that audit capture should be as close to the data mutation as possible — ideally in the same atomic unit. CloseLoop achieves this via application-layer inline trigger wiring (same transaction), which gives the same semantic guarantee without requiring storage-level infrastructure.

**Rejected from Zoho:**
- **Database-layer CDC.** Zoho's CDC operates at the storage engine level (triggers, WAL capture). For CloseLoop's SQLite + in-process deployment model, application-layer trigger wiring (`record_history()` call in the route handler) provides the same semantic guarantees — every mutation is captured in the same transaction — with no storage infrastructure requirements.
- **Separate audit microservice.** Zoho's enterprise deployment routes history to a separate audit service. CloseLoop has no microservice infrastructure and no requirement for one; history writes share the single SQLite database.

---

## 3. Patterns Summary: Borrowed vs. Rejected

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| Save-triggered, same-transaction write | Salesforce Field History Tracking | `record_history()` called inline in route handler, before `db.commit()` |
| History survives entity deletion | Salesforce, Attio | `entity_id` on `HistoryEntry` is a plain `INTEGER` — no FK constraint |
| `actor_id` on every history row | Salesforce, Attio | `HistoryEntry.actor_id` nullable FK → `users`, set from `event.actor_id` |
| Structured payload per kind (no pre-rendered string) | HubSpot Timeline API, Attio | `meta_json` = serialised typed dataclass; rendered at read time |
| Closed enum of event kinds (`_KIND_MAP`) | Pipedrive | `_KIND_MAP` in `app/core/history.py` — single source of truth |
| `kind` string as discriminator | Pipedrive, Attio | `kind: Literal["..."]` field on each dataclass; `HistoryEntry.kind` column |
| Entity-scoped retrieval (not cross-entity) | HubSpot, Attio | `GET /history?entity_type=deal&entity_id=N` — single entity per query |
| No creation endpoint in the public API | HubSpot, Attio | No `POST /history`; entries written exclusively by trigger wiring |

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Async outbox / event queue for history writes | (natural alternative) | No background worker machinery; ADR-0010 prohibits outbound calls; atomicity requires same-transaction write |
| SQLAlchemy ORM hooks (`after_flush` / `after_commit`) | (natural alternative) | Hidden second trigger mechanism; makes the codebase harder to follow alongside explicit notification triggers |
| Database-layer CDC | Zoho | Application-layer wiring provides equivalent semantic guarantees with no storage infrastructure |
| Separate audit microservice | Zoho | No microservice infrastructure; single-process deployment is the product invariant |
| FK on `entity_id` | — | Would cascade-delete history when entity is deleted; audit durability is the point |
| Pre-rendered `message` string in DB | HubSpot (old pattern), Pipedrive | Stale-message problem on entity renames; `meta_json` rendered at read time |
| Per-entity-type route (`GET /deals/{id}/flow`) | Pipedrive | Single parameterised endpoint is simpler and consistent with `Notification` shape |
| Cursor-based pagination (`after_id`) | Attio | Simple `?limit=N` is sufficient for this slice; add cursors if history grows |
| Field-level granularity (one row per changed field) | Salesforce | Deferred to slice 3; event-level entries sufficient for slice 1–2 scope |

---

## 4. Slice Plan

### Slice 1 (PR #46 foundation): Typed event model + persistence

**Deliverables:**
- `app/core/history.py` — pure typed event definitions: closed discriminated union of 12 dataclasses (`DealCreatedEntry`, `DealStageChangedEntry`, `DealAssignedEntry`, `DealUpdatedEntry`, `DealDeletedEntry`, `ContactCreatedEntry`, `ContactUpdatedEntry`, `ContactDeletedEntry`, `ActivityCreatedEntry`, `ActivityUpdatedEntry`, `ActivityCompletedEntry`, `ActivityDeletedEntry`). `_KIND_MAP` is the single source of truth. `event_to_meta()` / `event_from_meta()` are the serialisation seam.
- `HistoryEntry` ORM model in `app/models.py` (`history_entries` table)
- `app/services/history.py` — `record_history(db, *, entity_type, entity_id, event, clk)` single DB-write entry point
- `app/routers/history.py` — `GET /history?entity_type=...&entity_id=N[&limit=N]` pull API
- Tests: `tests/test_core_history.py` (pure serialisation round-trips) + `tests/test_history_triggers.py` (API integration)
- ADR-0026

**Explicitly out of scope (no async queue, no background worker — see rejected alternatives above):**
- Async outbox or event queue for history writes
- SQLAlchemy ORM hooks (`after_flush` / `after_commit`)
- Database-layer CDC
- Field-level diffing (old_value / new_value per changed field)
- Timeline UI

---

### Slice 2 (PR #46): Trigger wiring

**Deliverables:**
- `record_history()` wired into all domain route handlers: `deals.py`, `contacts.py`, `activities.py`
- Trigger sites follow the notification-trigger pattern from ADR-0025: inline in the handler, before `db.commit()`
- Tests in `tests/test_history_triggers.py`

---

### Slice 3 (later): Field-level diffing

**Deliverables:**
- Before-save snapshot of tracked fields in each mutation handler
- `old_value` / `new_value` pair per changed field, stored in or alongside `meta_json`
- The event-level `*UpdatedEntry` kinds remain; field-level detail is additive

---

### Slice 4 (done — PRs #60, #61): Timeline UI

**Deliverables:**
- `frontend/src/components/EntityTimeline.tsx` — shared React component; fetches `GET /history`, renders bulleted list with `renderLabel(kind, meta)`, timestamp, actor name; handles loading / error / empty states.
- `HistoryEntry` TypeScript type added to `frontend/src/types.ts`.
- Wired into `DealDetailView`, `ContactDetailView`, `ActivityDetailView`.
- `GET /history` response extended with `actor_name` (User.full_name via `joinedload`).
- Actor-name API tests in `tests/test_history_triggers.py::TestHistoryActorName`.
- E2e smoke tests in `e2e/history.spec.ts` (deal / contact / activity timeline panels).

---

## 5. Schema Design

```
history_entries
  id            INTEGER PK
  entity_type   TEXT NOT NULL     "deal" / "contact" / "activity"
  entity_id     INTEGER NOT NULL  no FK — survives entity deletion (Salesforce audit durability)
  actor_id      INTEGER → users(id) ON DELETE SET NULL  nullable (system events have no actor)
  kind          TEXT NOT NULL     discriminator; closed enum (_KIND_MAP)
  meta_json     TEXT NOT NULL     serialised HistoryEvent (typed dataclass)
  occurred_at   TEXT NOT NULL     ISO-8601 UTC (injected clock, ADR-0006)
```

Composite index on `(entity_type, entity_id, occurred_at)` — supports the canonical `WHERE entity_type=? AND entity_id=? ORDER BY occurred_at DESC` query.

**`entity_id` has no FK constraint.** This is the Salesforce audit durability pattern: history rows must survive deletion of the entity they describe. A `REFERENCES deals(id) ON DELETE CASCADE` would destroy the audit trail when a deal is deleted — the opposite of what an audit log is for.

**`actor_id` FK with `ON DELETE SET NULL`.** Consistent with the `Notification` model. Nullable because future system-generated entries (e.g., automated stage moves) will have no human actor.

---

## 6. API Surface

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/history` | Bearer | List history entries for a single entity, newest first. Required: `?entity_type=deal\|contact\|activity` and `?entity_id=N`. Optional: `?limit=N` (default 50). 422 if `entity_type` is not a known value or `limit < 1`. |

No `POST /history` — history entries are written exclusively by trigger wiring. This is consistent with Salesforce, HubSpot, and Attio: the history creation path is internal to the application, not a public REST endpoint.
