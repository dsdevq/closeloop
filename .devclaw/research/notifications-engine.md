# Notifications Engine — Reference CRM Research & Design Synthesis

**Status:** Accepted — implementation begins with slice 1 (typed event model + pull retrieval).
**Date:** 2026-07-03
**Scope of this doc:** Reference CRM survey, borrowed/rejected patterns, and slice-by-slice build plan for CloseLoop's in-app notification centre.

---

## 1. What We're Building and Why

CloseLoop's domain brief (§12) identifies four notification surfaces used by best-in-class CRMs:

| Surface | What it shows |
|---------|---------------|
| In-app bell icon + unread count | Task overdue, @mention, deal assigned, stage change on watched deal |
| Email digest | Daily overdue + due-today summary |
| Push (web/mobile) | High-priority alerts |
| User preferences | Per-channel per-event opt-in |

This document covers **surface 1 only** — the in-app notification centre — and specifically the **first reviewable slice**: the typed event model and pull-based retrieval.

Delivery to email/push and the user-preference model are out of scope until the pull model is proven in production.

---

## 2. Reference CRM Survey

### 2.1 Salesforce (Sales Cloud)

**Notification model:** Salesforce exposes *Platform Events* and *Change Data Capture* — a pub/sub event bus where typed events are published by object triggers and consumed by flows, Apex subscribers, or Lightning components. The in-app notification bell (Bell Notifications API) is a separate surface. Each notification has a `notificationTypeId`, `targetId`, `targetPageRef`, and a `messageTitle`/`messageBody`.

**Key patterns borrowed:**
- **Typed events with a discriminator field.** Every Salesforce notification has a type ID that is a stable string key. The payload carries the context needed to render a message without a runtime DB join.
- **Separate notification table, not the audit log.** Salesforce's `ApexEmailNotification`, `CustomNotificationType`, and the org event bus are distinct from the `SetupAuditTrail`. These serve different consumers: notifications are user-facing and dismissable; the audit trail is append-only and system-facing.
- **Recipient FK.** Every Salesforce notification targets a specific user or group — never "everyone." The recipient model is explicit.

**Rejected from Salesforce:**
- **Event bus / Streaming API.** Salesforce uses Bayeux (CometD) long-polling and now also Server-Sent Events for real-time delivery. CloseLoop has no background worker, no socket manager, and ADR-0010 prohibits outbound network calls. A streaming delivery layer would require significant new infrastructure.
- **Custom notification types as admin-managed records.** Salesforce lets admins define notification types via the Metadata API. For CloseLoop, notification kinds are typed in code — fewer moving parts, simpler schema.

---

### 2.2 HubSpot CRM

**Notification model:** HubSpot's in-app notification centre stores notifications as typed records with a `category` string discriminator (`DEAL_NOTE`, `TASK_REMINDER`, `CONTACT_PROPERTY_CHANGE`, etc.). The GET `/notifications` endpoint returns the current user's notifications in reverse-chronological order with `read` status. Notifications are created server-side by HubSpot's automation engine; the API is read-only for external callers.

**Key patterns borrowed:**
- **Pull model for retrieval.** HubSpot's notification API is polled by the client: `GET /notifications?unread=true&limit=N`. No WebSocket needed. The client has a short poll on the bell icon (or SSE if the app is open). CloseLoop adopts the same approach: `GET /notifications` with `?unread_only=true&limit=N`.
- **`unread` flag as a timestamp, not a boolean.** HubSpot stores `readAt` (ISO-8601) rather than a boolean, which enables "recently read" ordering and auditable read history. CloseLoop uses `read_at` (TEXT nullable) on the same logic.
- **Category/kind string in the response.** The frontend can branch on `kind` to render the right icon/copy without understanding the full payload.

**Rejected from HubSpot:**
- **Inline `message` string stored in DB.** HubSpot persists the rendered string in the notification row ("Alex moved Deal X to Proposal"). If deal titles are renamed, the notification shows stale text. CloseLoop stores the **raw event payload** (`payload_json`) and renders the message at read time. The render function is pure and testable.

---

### 2.3 Pipedrive

**Notification model:** Pipedrive has a `GET /notifications` endpoint returning the authenticated user's notifications. Each notification has a `type` key (e.g., `deal_stage_changed`, `activity_marked_done`), a `subject` (plain text), and a `data` object with context. Pipedrive's notification types are documented as a closed enum in their API docs.

**Key patterns borrowed:**
- **Closed enum of kinds.** Pipedrive documents a fixed set of notification types. This makes frontend rendering predictable: the bell dropdown knows exactly which icons and copy patterns to use. CloseLoop implements this as a discriminated union in `app/core/notifications.py` with a `_KIND_MAP` dict that is the single source of truth.
- **`entity_type` + `entity_id` on each notification.** Pipedrive includes the linked entity type and ID so the frontend can link the notification to the right detail page. CloseLoop adds `entity_type` and `entity_id` columns on the `Notification` model.
- **Unread count as a separate cheap endpoint.** Pipedrive exposes `GET /notifications/get-unread-count` as a lightweight endpoint the header can poll frequently without loading the full notification list.

**Rejected from Pipedrive:**
- **`subject` as a pre-rendered string stored in DB.** Same reason as the HubSpot rejection above — stale-message problem.

---

### 2.4 Attio

**Notification model:** Attio is the most modern of the reference CRMs for this feature. Notifications are returned with a `notification_type` discriminator and a strongly typed `payload` object. The payload schema is different per type. Attio uses cursor-based pagination (`after_id`) rather than offset pagination. The notification centre shows who triggered it (actor) and links to the entity.

**Key patterns borrowed:**
- **Structured `payload` per kind.** Attio's `notification_type: "comment_mention"` payload has `{author_id, record_id, record_type, comment_id, body_snippet}` — all structured, not a flat message string. CloseLoop stores this as `payload_json` containing a serialized typed dataclass. `event_from_payload()` + `render_notification()` are the deserialization and rendering seam.
- **`actor_id` as a first-class field.** Attio always includes who triggered the notification. CloseLoop adds `actor_id` as a nullable FK on `Notification` — nullable because system-generated events (task overdue) have no human actor.
- **Recipient-scoped isolation.** Attio's notification API is always scoped to the authenticated user. CloseLoop enforces `recipient_id = current_user.id` on all queries — no cross-user leakage.

**Rejected from Attio:**
- **Cursor-based pagination.** Attio uses `after_id` cursor pagination for large notification histories. CloseLoop uses a simple `limit` parameter for this slice. Cursor pagination is a later optimisation if notification history grows.
- **Record-presence in the notification card.** Attio resolves the record title at read time (separate DB join). CloseLoop embeds `entity_type`/`entity_id` and the rendered message (from payload) — the frontend navigates to the entity using the IDs, no additional join needed.

---

### 2.5 Zoho CRM

**Notification model:** Zoho has both a *Notification Centre* (bell icon, in-app) and a *Notification API* for webhooks. The in-app centre is driven by a backend process that scans for overdue tasks, @mentions, and record changes on a schedule. Notifications are grouped by day in the UI.

**Key patterns borrowed:**
- **@mention as an explicit notification kind.** Zoho treats `mention` as a first-class notification type with its own payload schema (author, entity, snippet). CloseLoop defines `MentionEvent` in the kind enum. (@mention *parsing* — i.e., extracting `@user` from note bodies — is deferred to a later slice; this slice defines the event type so the schema is ready.)

**Rejected from Zoho:**
- **Polling workers for overdue-task detection.** Zoho uses background jobs that scan for overdue tasks and insert notification rows. CloseLoop has no background worker machinery. Overdue-task notification creation will be triggered synchronously at the point where overdue tasks are queried (later slice), not by a background scan.
- **Day-grouping in the API response.** Zoho groups notifications by date in the response. CloseLoop returns a flat list; grouping is a frontend concern.

---

## 3. Patterns Summary: Borrowed vs. Rejected

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| Typed events with `kind` discriminator | Salesforce, Pipedrive | `app/core/notifications.py` — discriminated union dataclasses with `kind: Literal["..."]` |
| Pull model: `GET /notifications` | HubSpot, Pipedrive, Attio | `app/routers/notifications.py` — no WebSocket/SSE |
| `read_at` timestamp (not boolean) | HubSpot, Attio | `Notification.read_at` nullable TEXT |
| Separate notifications table (not audit log) | Salesforce, Attio | `notifications` table; `event_log` retained for audit |
| `recipient_id` FK + per-user isolation | All five | `Notification.recipient_id` → users, enforced in all queries |
| `actor_id` FK (nullable) | Attio, Salesforce | `Notification.actor_id` → users, nullable for system events |
| `entity_type` + `entity_id` | Pipedrive, Attio | Columns on `Notification`; frontend navigation target |
| Structured `payload_json` (not pre-rendered string) | Attio | `payload_json` = serialised typed dataclass; rendered at read time |
| Unread count as a cheap separate endpoint | Pipedrive | `GET /notifications/unread-count` |
| `MentionEvent` kind in the type set | Zoho | Defined in this slice; parsing deferred |

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Event bus / Streaming API (WebSocket/SSE) | Salesforce, HubSpot | No background worker, no socket manager in CloseLoop; ADR-0010 prohibits outbound calls |
| Pre-rendered message string stored in DB | HubSpot, Pipedrive | Stale-message problem on entity renames; CloseLoop renders from payload at read time |
| Admin-managed notification type records | Salesforce | Over-engineered for CloseLoop's scope; kinds are a code enum |
| Background polling workers | Zoho | No worker machinery; creation is lazy/synchronous (later slice) |
| Cursor-based pagination | Attio | Simple `limit` is sufficient for this slice; add cursors if notification history grows |
| Day-grouping in API response | Zoho | Frontend concern; backend returns flat list |

---

## 4. Slice Plan

### Slice 1 (this PR): Typed event model + pull retrieval

**Deliverables:**
- `app/core/notifications.py` — pure typed event definitions (discriminated union dataclasses + `event_to_payload`, `event_from_payload`, `render_notification`)
- `Notification` ORM model in `app/models.py` (`notifications` table)
- `app/routers/notifications.py` — pull API: `GET /notifications`, `GET /notifications/unread-count`, `POST /notifications/{id}/read`, `POST /notifications/read-all`
- Full test coverage: `tests/test_core_notifications.py` (pure) + `tests/test_notifications.py` (API)
- ADR-0025

**Explicitly out of scope:**
- After-Save routing (trigger wiring that creates notifications on stage change, deal assign, etc.)
- `TaskOverdueEvent` generation from the overdue-task scan
- `@mention` parsing from note bodies
- Email digest delivery (outbox integration)
- Frontend bell icon / notification dropdown

---

### Slice 2 (next): After-Save routing + stage-transition trigger

**Deliverables:**
- Stage-transition hook in `app/routers/deals.py` that calls `create_notification(db, recipient_id, StageChangedEvent(...))`
- Deal-assigned trigger on owner_id change
- Tests for trigger wiring

---

### Slice 3 (later): Overdue-task notifications + @mention parsing

**Deliverables:**
- `create_overdue_notifications(db, clk)` function (called from a lazy "check" endpoint or a Today-queue request)
- `parse_mentions(body: str) -> list[str]` pure function in `app/core/notifications.py`
- Integration with note-saving path

---

### Slice 4 (later): Email digest + user preferences

**Deliverables:**
- Outbox integration: daily digest from unread notifications
- `notification_preferences` table (per-user, per-kind, per-channel)
- Preference-respecting gate in trigger wiring

---

## 5. Schema Design

```
notifications
  id              INTEGER PK
  recipient_id    INTEGER → users(id) ON DELETE CASCADE   -- always set
  actor_id        INTEGER → users(id) ON DELETE SET NULL  -- nullable (system events)
  kind            TEXT NOT NULL                           -- discriminator key
  entity_type     TEXT                                    -- "deal" / "activity" / "contact" / NULL
  entity_id       INTEGER                                 -- PK of the linked entity / NULL
  payload_json    TEXT NOT NULL                           -- serialised NotificationEvent
  read_at         TEXT                                    -- NULL = unread; ISO-8601 string when read
  created_at      TEXT NOT NULL                           -- ISO-8601 UTC
```

Index: `(recipient_id, read_at)` — supports the `WHERE recipient_id = ? AND read_at IS NULL` query for unread counts.

---

## 6. API Surface (Slice 1)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/notifications` | Bearer | List current user's notifications, newest first. `?unread_only=true`, `?limit=N` (default 50). |
| GET | `/notifications/unread-count` | Bearer | `{"unread_count": N}` — lightweight bell badge query. |
| POST | `/notifications/{id}/read` | Bearer | Mark one notification read. 404 if not found or owned by another user. |
| POST | `/notifications/read-all` | Bearer | Mark all current user's unread notifications read. Returns 204. |

Notifications are created by trigger wiring (slice 2+), not by an explicit API endpoint. This is consistent with Salesforce/HubSpot/Attio: the notification creation API is internal (service function), not a public REST endpoint.
