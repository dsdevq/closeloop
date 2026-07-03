---
id: "0025"
title: Notifications engine — typed event model and pull-based retrieval
status: accepted
date: 2026-07-03
owner: "@dsdevq"
tags: [notifications, data-model, api, architecture]
supersedes: null
superseded-by: null
---

# ADR-0025 — Notifications engine — typed event model and pull-based retrieval

## Context

CloseLoop's domain brief (§12) identifies an in-app notification centre as a core CRM surface: deal assignment, stage changes, task overdue alerts, and @mentions all need to surface to the responsible rep without requiring them to poll every entity manually.

Five reference CRMs were surveyed in full before this implementation (`.devclaw/research/notifications-engine.md`). The key tensions are:

1. **Delivery model** — push (WebSocket/SSE) vs. pull (polling `GET /notifications`). Push requires a persistent socket manager or background delivery worker; CloseLoop has neither, and ADR-0010 prohibits outbound network calls.
2. **Message storage** — pre-render the human-readable string and store it, or store the raw typed payload and render at read time. Pre-rendering risks stale text when entity names are later changed.
3. **Type system** — open schema (any JSON blob) vs. closed discriminated union. Closed sets make frontend rendering predictable and catch missing cases at compile / type-check time.
4. **Separation of concerns** — use the existing `event_log` (audit log) as the notification store, or keep a separate `notifications` table with its own lifecycle (read/unread, per-user isolation, dismissal).

## Decision

### Typed event model (`app/core/notifications.py` — ADR-0001 pure module)

A **closed discriminated union** of four dataclasses, each with a `kind: Literal["..."]` field that acts as the runtime discriminator:

| Kind | Borrowed from |
|------|--------------|
| `deal_assigned` | Salesforce (typed `notificationTypeId`), Pipedrive (closed enum of `type` keys) |
| `stage_changed` | Salesforce, Pipedrive |
| `task_overdue` | Zoho (first-class notification kind for overdue tasks) |
| `mention` | Zoho (`mention` as an explicit notification kind with its own payload schema) |

`_KIND_MAP` is the single source of truth; `ALL_KINDS` is the exported frozenset used by callers to validate.

`event_to_payload(event)` serialises to JSON via `dataclasses.asdict()` (which includes `init=False` fields such as `kind`). `event_from_payload(payload)` deserialises: pops `kind`, looks up the class, and calls `cls(**rest)` — raising `ValueError` on unknown kinds or missing fields. `render_notification(event)` is a pure function that maps each event to a one-line human-readable string, rendered at read time (not stored).

**Borrowed:** Attio's structured per-kind payload — each event carries exactly the fields needed to render its message without a DB join at read time. Salesforce's `actor_id` as a first-class field (nullable; system-generated events have no actor).

**Rejected:** HubSpot and Pipedrive both store a pre-rendered `subject`/`message` string in the notification row. If a deal title is renamed, those strings go stale. CloseLoop stores `payload_json` (the raw event) and renders at read time; the render function is pure and testable in isolation.

### ORM model (`app/models.py` — `notifications` table)

```
id              INTEGER PK
recipient_id    INTEGER → users(id) ON DELETE CASCADE  (NOT NULL)
actor_id        INTEGER → users(id) ON DELETE SET NULL  (nullable)
kind            TEXT NOT NULL
entity_type     TEXT  ("deal" / "activity" / "contact" / NULL)
entity_id       INTEGER
payload_json    TEXT NOT NULL
read_at         TEXT  (NULL = unread; ISO-8601 UTC when read)
created_at      TEXT NOT NULL
```

Composite index on `(recipient_id, read_at)` supports the `WHERE recipient_id=? AND read_at IS NULL` pattern used by unread-count queries.

**`read_at` is a nullable timestamp, not a boolean** — borrowed from HubSpot (which stores `readAt` as ISO-8601) and Attio. This enables "recently read" ordering and an auditable read history without a schema migration if read-history reporting is added later.

**Separate table, not the audit log** — borrowed from Salesforce and Attio. The `event_log` table is system-facing and append-only (audit trail); the `notifications` table is user-facing, dismissable, and has a distinct lifecycle.

**`entity_type` + `entity_id`** — borrowed from Pipedrive and Attio. The frontend can link the notification to the right detail page using these fields; no additional DB join is needed at render time.

### Pull API (`app/routers/notifications.py`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/notifications` | List current user's notifications, newest first. `?unread_only=true`, `?limit=N` (default 50). |
| GET | `/notifications/unread-count` | Lightweight `{"unread_count": N}` for bell-badge polling. |
| POST | `/notifications/{id}/read` | Mark one notification read. 404 if not found or owned by another user. Idempotent. |
| POST | `/notifications/read-all` | Mark all unread notifications read. Returns 204. |

All queries are scoped to `recipient_id = current_user.id` — cross-user notification leakage is structurally impossible.

**Pull model borrowed from HubSpot, Pipedrive, and Attio** — all three expose `GET /notifications` polled by the client, with no WebSocket or SSE. The unread-count endpoint (`GET /notifications/unread-count`) is borrowed from Pipedrive, which provides it as a cheap, frequently-polled endpoint for the bell badge.

**No public creation endpoint** — consistent with Salesforce, HubSpot, and Attio: notification creation is an internal service operation (trigger wiring, later slice), not a public REST endpoint.

## Consequences

- **Trigger wiring is decoupled.** Slice 2 adds the after-save hooks that call `create_notification(db, recipient_id, event)` — no schema change needed.
- **Frontend rendering is deterministic.** The closed `kind` set means the bell dropdown can enumerate exactly which icons and copy patterns it needs; there are no open-ended payloads to handle defensively.
- **Render is testable in isolation.** `render_notification` is pure; all four render paths are tested in `tests/test_core_notifications.py` without any DB fixture.
- **No background worker needed.** Task-overdue notification creation will be triggered synchronously at query time (later slice), not by a background scan (rejected: Zoho pattern).
- **No cursor pagination yet.** The `limit` parameter is sufficient for this slice. Cursor-based pagination (`after_id`) — borrowed from Attio — is a later optimisation if notification history grows substantially.

## Alternatives considered

- **WebSocket / SSE push delivery** — Salesforce (CometD) and HubSpot (SSE) both push real-time notifications. Rejected: CloseLoop has no background worker, no socket manager, and ADR-0010 prohibits outbound calls. The pull model is operationally simpler and sufficient for a single-tenant CRM.
- **Admin-managed notification type records** — Salesforce allows admins to define `CustomNotificationType` records via the Metadata API. Rejected: over-engineered for CloseLoop's scope; the kind set is a code enum.
- **Background polling worker for overdue-task detection** — Zoho uses a background job that scans for overdue tasks. Rejected: CloseLoop has no worker machinery; overdue-task notification creation is lazy/synchronous (later slice).
- **Cursor-based pagination** — Attio uses `after_id` cursor pagination. Deferred: `limit` is sufficient for the notification volumes expected in a single-tenant CRM. Add cursors if notification history grows.
- **Day-grouping in the API response** — Zoho groups notifications by date server-side. Rejected: frontend concern; backend returns a flat, reverse-chronological list.
- **Using the `event_log` table** — simpler schema (no new table), but `event_log` is append-only, system-facing, and has no per-user lifecycle. Mixing user-dismissable notifications into the audit log conflates two different concerns.
