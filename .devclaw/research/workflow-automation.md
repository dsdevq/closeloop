# Workflow Automation — Reference CRM Research & Design Synthesis

**Status:** Active — slices 1–3 shipped (rules model + condition evaluation + notify action); scheduled trigger shipped (PRs #56–#58); after-save router wiring and CRUD API are the remaining gaps before the engine is production-callable.
**Date:** 2026-07-04 (original); updated 2026-07-09 to reconcile with shipped implementation and document PHASE 2 gaps.
**Scope of this doc:** Reference CRM survey, borrowed/rejected patterns, and slice-by-slice build plan for CloseLoop's user-configurable workflow automation engine.

---

## 1. What We're Building and Why

CloseLoop's domain brief (§13) identifies workflow automation as the next layer on top of the event-driven plumbing already established for notifications (PRs #41–#47) and audit history (PRs #46, #62–#63). The existing After-Save trigger mechanism already fires at every domain mutation; automation adds a user-configurable rules evaluation pass at those same sites, enabling "when X happens and Y is true, do Z" rules without any additional trigger infrastructure.

The two previously hardcoded surfaces that automation generalises:

| Surface | Current state | Automation adds |
|---------|--------------|-----------------|
| In-app notifications | Hardcoded: stage change + deal assigned only | User-defined "notify user X when field Y = Z" |
| Activity/task creation | Manual only | Auto-create a task when a deal enters a stage |

### Current shipped state (as of 2026-07-09)

| Component | Status | Files |
|-----------|--------|-------|
| `AutomationRule` ORM model + `automation_rules` table | ✅ Shipped | `app/models.py` |
| `_parse_conditions`, `evaluate_conditions`, `execute_automation_rules` | ✅ Shipped | `app/services/automations.py` |
| `_execute_action` stub → `notify` action fully implemented | ✅ Shipped | `app/services/automations.py` |
| `AutomationEvent` notification type | ✅ Shipped | `app/core/notifications.py` |
| Scheduled trigger (`trigger_type="scheduled"`) with CAS claim | ✅ Shipped | `app/services/automations.py`, `app/main.py` |
| **After-save router wiring** (`execute_automation_rules` called inline in route handlers) | ❌ **Missing — critical gap** | `app/routers/deals.py`, `contacts.py`, `activities.py` |
| **CRUD API** for managing rules | ❌ Not started | `app/routers/automation_rules.py` (doesn't exist) |
| `create_activity` action type | ❌ Not started | — |
| Frontend rule builder UI | ❌ Not started | — |

**The engine functions but is not callable from production.** `execute_automation_rules()` exists and is tested in isolation, but no route handler imports or calls it. After-save rules cannot fire until the router wiring is added.

The three design tensions:

1. **Trigger timing** — event-based (fires on domain mutation) vs. scheduled (time-based cron). CloseLoop has no dedicated background worker; ADR-0010 prohibits outbound network calls. Event-based triggers extend the existing After-Save hook. Scheduled triggers were initially rejected then added via an asyncio poller in the FastAPI lifespan (PRs #56–#58).
2. **Condition/action composition** — visual flow canvas vs. declarative JSON rules vs. inline code. Visual builders are costly to build; hardcoded inline code is not user-configurable. Declarative JSON rules (stored in the DB, evaluated at the trigger site) are the appropriate middle ground.
3. **Trigger registration** — a second trigger mechanism (ORM hooks, a background scanner, or a pub/sub bus) vs. extending the existing After-Save hook sites. A second mechanism creates two competing trigger paths. The After-Save hook sites already exist at every mutation.

**Critical architecture constraint:** The after-save rules engine MUST extend the existing After-Save hook mechanism (`create_notification()` / `record_history()` called inline in route handlers, before `db.commit()`). It MUST NOT introduce a second competing trigger mechanism such as SQLAlchemy ORM event hooks (`after_flush` / `after_commit`), a background scanner, a pub/sub event bus, or any other parallel trigger path.

---

## 2. Reference CRM Survey

Five reference CRMs were surveyed. The patterns borrowed and rejected are summarised in §3.

### 2.1 Salesforce (Flow / Process Builder)

**Automation model:** Salesforce offers two overlapping automation layers. *Process Builder* (deprecated in favour of Flow) fires on record create/edit and evaluates criteria, then executes actions (field updates, send email, create task, invoke Apex). *Flow Builder* is a visual drag-and-drop canvas supporting both event-based (Record-Triggered Flow) and scheduled triggers. Record-Triggered Flows run *After Save* — they share the transaction context and can update related records in the same commit. Criteria are evaluated as field-value conditions with AND/OR operators via a visual expression builder.

**Trigger types:** record created, record updated (any field or specific field change), scheduled (relative to record date/time field), platform event published.

**Condition model:** AND/OR boolean expression tree, visual editor. Each leaf: `{field, operator, value}`. Operators: equals, not_equals, contains, starts_with, ends_with, greater_than, less_than, is_null, is_not_null, in, not_in. OR-logic supported.

**Action types:** Update Records, Create Records, Delete Records, Get Records (query), Send Email (via org email service), Custom Notification (in-app bell), Call Apex, Run Subflow, Post to Chatter.

**End-user exposure:** Visual Flow Builder canvas. Drag-and-drop nodes on a canvas; no JSON authoring exposed. Admin-managed metadata records.

**Key patterns borrowed:**
- **After-Save execution model.** Salesforce Record-Triggered Flows fire in the same save transaction as the mutation that triggered them. CloseLoop's existing After-Save hook sites (`deals.py`, `contacts.py`, `activities.py`) already implement this timing contract; automation rule evaluation is an additional step in that same position.
- **Trigger kind as a closed enum.** Each Salesforce flow is configured for a specific `Object` + `Trigger Type` (Create, Update, Delete). CloseLoop borrows this: the set of trigger events is the intersection of the existing `_KIND_MAP` in `app/core/history.py` — no new trigger taxonomy is invented.
- **Declarative condition criteria.** Process Builder / Flow criteria are expressed as field-operator-value triples. CloseLoop's condition model follows this shape: `{"field": "stage", "op": "eq", "value": "won"}`.
- **Action types: field update, task creation, notification.** Salesforce actions are typed: "Update Records", "Create Records", "Send Notification". CloseLoop adopts the same action taxonomy, starting with `notify` and deferring `create_activity` and field-update actions.
- **Structured typed payload for notifications, not pre-rendered string.** Salesforce Custom Notification stores a typed `payload`; `render_notification()` produces the message at read time. CloseLoop's `AutomationEvent` follows this exactly.

**Rejected from Salesforce:**
- **Visual Flow Builder canvas.** Expensive admin UI, out of scope for current scale. CloseLoop uses declarative JSON stored in the DB; the admin UI for creating rules is deferred.
- **OR-logic / complex boolean expression trees.** Salesforce supports complex boolean expressions (AND/OR trees). CloseLoop starts with AND-only conjunctive conditions — sufficient to cover common patterns without a full expression evaluator.
- **Cross-object update actions.** Salesforce flows can cascade updates to related records. Requires a generalised field-write path across entity types; deferred.
- **Scheduled relative-to-date-field triggers.** Salesforce supports "run this action 3 days before close date" — the trigger date is a field on the triggering record, not a fixed time. CloseLoop's scheduled trigger is clock-based only (`interval_minutes` / `run_once_at`), not entity-relative. Entity-relative scheduling requires scanning across all matching records, which is a fundamentally different design (see §8).

---

### 2.2 HubSpot Workflows

**Automation model:** HubSpot Workflows are the most widely referenced automation model in the SMB CRM segment. A workflow has an *enrollment trigger* (a property-change event or a static/smart list membership change), optional *re-enrollment criteria*, and a linear sequence of *actions* (send email, set property, create task, add to list, branch on condition). Actions execute in order; a "Delay" action pauses the sequence until a time condition is met. Each workflow is associated with a single object type (Deal, Contact, Company).

**Trigger types:** contact/deal property change, form submission, list membership change, page view (COS), deal stage change, scheduled recurring (fixed time or relative to property), manual enrollment.

**Condition model:** property-based enrollment criteria (AND-only for enrollment; branching inside the workflow via If/Then branch action supports OR). Operators: is equal to, is not equal to, contains, doesn't contain, is greater than/less than, is known/unknown, is in list, is not in list.

**Action types:** set property value (field update), create task, send email, send internal notification, delay (relative to date or fixed duration), if/then branch, copy value to associated record, rotate to rep (round-robin assignment), add to/remove from list, webhook call.

**End-user exposure:** Visual workflow builder with a step-by-step sequence editor. Each action is a typed card dragged into a linear sequence. No raw JSON exposed to end users.

**Key patterns borrowed:**
- **Single-object-type scope per rule.** HubSpot requires each workflow to be associated with one object type. Note: the shipped `AutomationRule` model does NOT have an `entity_type` column — the original design planned it, but the query in `execute_automation_rules` filters only by `trigger_event`. Entity-type scoping via the trigger event string is implicit (a `deal_stage_changed` event can only be fired from the deals router); an explicit column would improve query efficiency at higher rule counts. See §9 for the deferred design question.
- **Enrollment criteria as declarative property filters.** HubSpot's enrollment trigger is a set of property conditions. This maps to CloseLoop's `conditions_json` array of `{field, op, value}` objects evaluated by `evaluate_conditions()`.
- **Action type: "Create task."** HubSpot's "Create task" is one of its most-used automation actions in deal workflows. CloseLoop adopts this as the `create_activity` action kind (deferred; not yet implemented).
- **Self-notification suppression.** HubSpot suppresses enrollment when the enrolling actor is the rule creator and the rule's purpose is to alert someone else. CloseLoop retains the existing self-notification suppression pattern.
- **`is_active` toggle.** HubSpot has an on/off toggle per workflow. CloseLoop's `is_active` column follows the same pattern.

**Rejected from HubSpot:**
- **Delay actions / time-based sequencing within a single rule.** HubSpot's "Delay until date" and "Delay for X days" actions require a persistent scheduler that re-activates workflow instances at a future time. CloseLoop's scheduled trigger is a full-rule cadence (the whole rule fires at an interval), not a per-record per-step delay mid-sequence.
- **Re-enrollment logic.** HubSpot tracks whether a record has previously enrolled and provides re-enrollment criteria. This requires per-record execution state. CloseLoop rules are stateless: they fire every time their trigger and conditions match, with no enrollment history.
- **Branching inside a single rule (If/Then branch action).** HubSpot allows a workflow to branch into two paths based on a mid-sequence condition. CloseLoop keeps rules flat: one trigger + conditions → one action. Multiple outcomes are handled by multiple rules, not by branching inside a single rule.
- **Email send action.** ADR-0010 prohibits runtime outbound network calls.

---

### 2.3 Pipedrive Automations

**Automation model:** Pipedrive Automations are purely event-based (no scheduled triggers). Each automation has a *trigger event* (Deal created, Deal stage changed, Deal won, Activity added, etc.), optional *conditions* (field filters on the triggering entity), and one or more *actions* (Update deal field, Create activity, Send email, Add follower). The trigger event set is a closed, documented enum.

**Trigger types:** entity created (deal, contact, person, org, lead), entity stage changed, entity field changed (to/from specific value), entity won/lost, entity deleted, activity added/updated/completed.

**Condition model:** field-value filters on the triggering entity AND on related entities (e.g., "deal's owner is"). AND-only. Operators: equals, not equals, contains, starts with, ends with, is empty, is not empty, is any of (multi-value).

**Action types:** Update field (on the triggering entity or related), Create activity, Send email (via Pipedrive mail), Add follower, Move to stage, Mark as won/lost.

**End-user exposure:** wizard-style step-through UI. Trigger → Condition → Action each on their own screen. No visual canvas, no JSON exposed.

**Key patterns borrowed:**
- **Closed trigger event enum matching the existing kind set.** Pipedrive's trigger events (`deal_created`, `deal_stage_changed`, `deal_won`, `activity_added`) map directly to CloseLoop's existing history event kind set. CloseLoop's `trigger_event` column is drawn from the same vocabulary — `execute_automation_rules(db, trigger_event="deal_stage_changed", ...)`.
- **Conditions as field-value filters on the triggering entity snapshot.** Pipedrive conditions check field values at the moment of the trigger event. CloseLoop's `evaluate_conditions()` receives an entity snapshot dict and evaluates the condition list against it.
- **Action: "Create activity."** Pipedrive's most common automation action is creating a follow-up activity/task. This is the second action type CloseLoop plans (deferred).
- **No-op when conditions don't match.** Pipedrive automations silently skip if conditions are not met. CloseLoop's `evaluate_conditions()` returns `False`; the caller skips action execution.

**Rejected from Pipedrive:**
- **Email action (outbound).** Prohibited by ADR-0010.
- **Multi-action sequences within a single automation.** CloseLoop uses one action per rule and composes outcomes by having multiple rules.
- **"Add follower" action.** CloseLoop has no follower/watcher model.
- **Field-change trigger (to/from specific value).** Pipedrive can trigger on "Deal stage changed FROM Prospecting TO Qualification" specifically. CloseLoop's current trigger events are coarser (`deal_stage_changed` fires whenever stage changes, with the old/new values available in the context dict). Attribute-change triggers (requiring before/after snapshot for ALL fields) are deferred to slice 3.

---

### 2.4 Attio Workflows

**Automation model:** Attio is the most modern reference CRM for this feature. Automations are event-based only: they fire on attribute changes, record stage transitions, or record creation. Each automation has a trigger (object + event type), optional attribute-level conditions, and one or more actions (send a notification, update an attribute, create a record). Attio's automation model is notably close to CloseLoop's current hardcoded trigger pattern — each trigger fires inline at the record-mutation point, evaluates conditions, and writes side-effects in the same operation.

**Trigger types:** record created, record attribute changed (to/from any value or specific value), record stage changed, record deleted, comment added (including @mention).

**Condition model:** attribute equality and comparison operators. `equals`, `not_equals`, `greater_than`, `less_than`, `contains`, `is_empty`, `is_not_empty`. AND-only in basic configuration; OR supported via alternative paths.

**Action types:** send in-app notification (to a specific team member or attribute-resolved user), update attribute, create record (in same or related object), send email, call webhook (to an external URL), delay (wait N days).

**End-user exposure:** Visual rule builder with a step-by-step trigger → conditions → actions editor. Attribute pickers use dynamic schema introspection. No raw JSON.

**Key patterns borrowed:**
- **Trigger fires at the mutation site, not via a separate observer.** Attio's engineering blog describes automation triggers as executing "at the point of the attribute write, synchronously, before the response is sent." This is architecturally identical to CloseLoop's After-Save hook: `create_notification()` / `record_history()` are called inline in the route handler, before `db.commit()`. The automation evaluation loop slots into exactly this position.
- **"Notify a team member" as a first-class action type.** Attio's most prominent automation action is sending an in-app notification to a team member. CloseLoop's `notify` action calls the existing `create_notification()` service function — automation is a new caller of an existing service, not a new notification path.
- **`actor_id` as a first-class nullable field on notifications.** Attio always includes who triggered the notification. CloseLoop's `AutomationEvent` carries `actor_id: int | None` — `None` for scheduled rules (no human actor), set from `context["actor_id"]` for after-save rules.
- **`entity_type` + `entity_id` forwarded to the notification row.** Attio includes the linked entity so the frontend can navigate to the correct detail page. `_execute_notify_action` forwards `context.get("entity_type")` and `context.get("entity_id")` to `create_notification()`.
- **Per-entity-type rule scoping (design intent).** Attio automations are scoped to a specific object type. The original CloseLoop design planned an `entity_type` column on `AutomationRule` for this; the shipped model uses implicit scoping via `trigger_event` string instead. See §9.

**Rejected from Attio:**
- **Attribute-level change triggers ("when attribute X changes from A to B").** Attio supports triggers that fire specifically when a given attribute changes from one value to another. This requires capturing old and new values at every trigger site. CloseLoop's current trigger sites pass a snapshot of the entity *after* the mutation; the old value is only captured at specific sites (e.g., `update_deal_stage` has `old_stage`). Generalising before/after capture across all fields for all entities is deferred to slice 3.
- **Webhook / HTTP action.** ADR-0010 prohibits runtime outbound network calls.
- **Multi-step sequences with delays.** No background scheduler machinery for per-record delay steps.

---

### 2.5 Zoho Blueprint and Workflow Rules

**Blueprint model:** Zoho Blueprint is a *stage-machine-oriented* mechanism that overlays a mandatory process on pipeline stages. It enforces that specific actions must be completed (e.g., a field filled in, an activity logged) before a deal can move to the next stage. Blueprint is NOT a general-purpose automation engine — it is a stage-transition gatekeeper that can block saves, a fundamentally different product requirement from "when X happens, do Y."

**Workflow Rules model:** Zoho Workflow Rules are the general-purpose automation engine that parallels CloseLoop's use case. Each rule has: a trigger (record create/edit/delete or time-based), criteria (field-value filters), and actions (email alert, field update, create task, invoke webhook, trigger another workflow).

**Zoho CRM Analytics (is it materially different?):** Zoho CRM Analytics is a reporting and data visualisation product — dashboards, charts, pivot tables, funnel analysis built on top of CRM data. It does not implement trigger-based automation. The only overlap with workflow automation is "scheduled exports" (not triggers on entity mutations) and "anomaly alerts" (threshold-based notification rules on aggregate metrics, not per-record triggers). CloseLoop's Insights dashboard (already shipped; `app/routers/insights.py`) is the analogue. No patterns from CRM Analytics apply to the automation engine design.

**Trigger types (Workflow Rules):** record created, record edited (any field or specific field), record deleted, time-based (fire N days before/after a date field value), scheduled (fixed time).

**Condition model:** AND-only conjunctive criteria. Field-value comparison. Operators: is, isn't, contains, doesn't contain, starts with, doesn't start with, is empty, is not empty, greater than, less than, between, in.

**Action types:** email alert (via Zoho's email service), field update, create task (with assignee + due-offset), invoke webhook, trigger another workflow rule (chaining).

**End-user exposure:** form-based admin UI, one field at a time. No visual canvas.

**Key patterns borrowed:**
- **Workflow Rules declarative model: trigger → criteria → actions.** Zoho Workflow Rules are the most explicit reference for CloseLoop's `AutomationRule` schema: a single row carrying `trigger_event`, `conditions_json`, `action_type`, `action_config_json`.
- **"Create Task" action with owner and due-offset parameters.** Zoho's "Create Task" action supports configuring the assignee and due date (e.g., "due 3 days after trigger date"). CloseLoop's planned `create_activity` action params carry `title`, `type`, `assigned_to_actor` (boolean), and `due_offset_days` (integer). The due offset is resolved at execution time using the injected clock (ADR-0006): `clk.now() + timedelta(days=offset)`.
- **Self-notification suppression.** Zoho's email alert action has a "Don't send to the record owner if they triggered the workflow" option. CloseLoop carries this through the existing `actor_id != recipient_id` guard in `create_notification()`.
- **Fail-closed parse of action config.** Zoho's time-based actions skip the rule if the config is malformed or missing. CloseLoop mirrors this: `_parse_schedule_config` raises `ScheduleConfigParseError`; `_parse_conditions` raises `ConditionsParseError`; `_parse_notify_config` raises `ActionConfigParseError` — all caught by the caller, which skips the rule.

**Rejected from Zoho:**
- **Blueprint (mandatory stage-gating).** Zoho Blueprint enforces that specific actions must be completed before a stage transition is allowed — it blocks the save if pre-conditions are not met. CloseLoop's pipeline transitions already have a state machine (`app/core/stages.py`, `validate_transition()`); Blueprint-style mandatory-action gates are a different product requirement not in current scope.
- **Time-based Workflow Rules (relative to date field).** Requires scanning all matching records at a scheduled time to find those where `field_date + offset >= now`. CloseLoop's scheduled trigger fires the entire rule at a cadence; it does not scan entity records. Entity-relative scheduling is a substantively different design (see §8).
- **"Invoke webhook" action.** ADR-0010 prohibits runtime outbound network calls.
- **Rule chaining (trigger another workflow from an action).** Introduces re-entrancy risk and execution-order complexity. CloseLoop rules are unconditionally non-recursive.

---

## 3. Patterns Summary: Borrowed vs. Rejected

### Borrowed (implemented)

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| After-Save execution timing (same transaction as the mutation) | Salesforce Flow, Attio | `execute_automation_rules()` is designed for inline call in route handlers, before `db.commit()`, alongside `create_notification()` / `record_history()` — **wiring not yet added to routers** |
| Closed trigger event string from existing kind set | Salesforce, Pipedrive | `AutomationRule.trigger_event` drawn from the same vocabulary as `_KIND_MAP` in `app/core/history.py` |
| Declarative `{field, op, value}` condition triples | Salesforce, HubSpot, Zoho | `conditions_json` array on `AutomationRule`; `evaluate_conditions(context, conditions)` pure function in `app/services/automations.py` |
| AND-only conjunctive condition evaluation | Salesforce, Pipedrive, Attio | All conditions must pass; `evaluate_conditions` returns `False` on first non-match |
| Supported condition operators | Pipedrive, Attio (subset) | `eq`, `neq`, `in` — the three shipped ops. `gt`, `lt`, `contains` are NOT yet implemented (planned in original design, not shipped) |
| Fail-closed on malformed config | Zoho, all five | `ConditionsParseError`, `ScheduleConfigParseError`, `ActionConfigParseError` — all caught by callers, which skip the rule rather than erroring or firing |
| Entity snapshot dict passed to condition evaluator | Salesforce, Attio | Route handler builds snapshot dict from entity fields at trigger time; passed as `context` to `execute_automation_rules()` |
| Action type: `notify` (reuses `create_notification()`) | Attio, Salesforce | `_execute_notify_action` calls the existing `create_notification()` — no new notification path |
| Self-notification suppression in automation-triggered notifs | HubSpot, Zoho | Reuses existing `actor_id != recipient_id` guard in `create_notification()` |
| `actor_id` nullable on automation notifications | Attio | `AutomationEvent.actor_id = None` for scheduled rules; set from `context["actor_id"]` for after-save rules |
| Structured typed payload for notifications, rendered at read time | Salesforce, Attio | `AutomationEvent` dataclass; `render_notification()` produces the message; avoids stale-message problem |
| `is_active` toggle per rule | HubSpot, Pipedrive | `AutomationRule.is_active` column; inactive rules are skipped at the query level |
| No public REST creation endpoint (trigger wiring is internal) | Salesforce, HubSpot, Attio | Rules execute via trigger wiring / scheduler, not via `POST /automation-rules/trigger` |
| Trigger-type discriminator on a single table | Salesforce (`TriggerType` enum on Flow) | `trigger_type: "after_save" \| "scheduled"` — both kinds share the `automation_rules` table, not separate tables |
| `last_triggered_at` to prevent double-fire | Salesforce per-record scheduled-action state | `AutomationRule.last_triggered_at` — NULL = never fired; ISO-8601 UTC string after first fire |
| Asyncio background poller for scheduled triggers | HubSpot (server-side scheduler) | `_scheduled_automations_loop()` in `app/main.py` polls every 60 s via `asyncio.create_task` in FastAPI lifespan |
| CAS (compare-and-swap) claim to prevent multi-worker double-fire | (distilled from distributed systems patterns) | Atomic `UPDATE automation_rules SET last_triggered_at = :new WHERE id = :id AND last_triggered_at IS <old>` before firing; `rowcount == 0` → another worker already claimed it |
| Commit claim before condition evaluation | (correctness invariant) | `db.commit()` immediately after `rowcount == 1`, before condition evaluation, so a `conditions=false` outcome does not roll back the claim and re-expose the rule as due |
| `run_once_at` one-shot rules | Zoho (one-time scheduled action) | `{"run_once_at": "2026-08-01T09:00:00"}` — fires once when `now >= run_once_at` and `last_triggered_at IS NULL` |

### Rejected (with rationale)

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Visual flow canvas (drag-and-drop) | Salesforce Flow Builder | Expensive admin UI, out of scope for current scale; JSON rule stored in DB is sufficient |
| OR-logic / complex boolean expression trees | Salesforce, HubSpot | AND-only conjunctive evaluation is sufficient for initial patterns; full expression trees add evaluator complexity |
| Multi-action sequences / chaining | HubSpot, Pipedrive, Zoho | Requires persistent execution state and scheduler; one action per rule, composable by having multiple rules |
| Delay actions within a rule (per-record time delay) | HubSpot, Salesforce, Attio | Requires a persistent scheduler that re-activates paused per-record rule instances; incompatible with synchronous After-Save execution |
| Attribute-change trigger (from A to B) | Attio, Pipedrive | Requires generalised before/after snapshot for all fields at all trigger sites; deferred to slice 3 |
| Time-based trigger relative to entity date field | Salesforce, Zoho | Requires scanning all matching entity rows at scheduled times to find those where `field + offset >= now`; fundamentally different from the clock-based scheduled trigger CloseLoop uses; deferred or out of scope |
| Outbound actions (email, webhook) | Pipedrive, HubSpot, Zoho, Attio | ADR-0010 prohibits runtime outbound network calls |
| Re-enrollment tracking per record | HubSpot | Requires per-record execution history table; rules are stateless (fire every time trigger + conditions match) |
| Rule chaining / recursive firing | Zoho | Re-entrancy risk; action execution does not re-evaluate the rule set |
| SQLAlchemy ORM hooks (`after_flush` / `after_commit`) | (natural alternative) | Creates a second competing trigger mechanism alongside the explicit After-Save hook calls; makes trigger sites implicit and harder to follow — same rejection reason as in `activity-timeline.md §3` and ADR-0026 |
| Background scanner for trigger detection | Zoho, (natural alternative) | No background worker machinery for event-based rules; same rejection as in `notifications-engine.md §2.5`. (Scheduled triggers use an asyncio poller, which is a different, bounded design: it polls rule metadata, not entity rows.) |
| Blueprint mandatory-action gates | Zoho | Different product requirement (blocking saves); pipeline transitions already have state machine in `app/core/stages.py` |
| Entity-type column on `AutomationRule` for explicit scoping | HubSpot, Attio | Not in the shipped schema. Implicit scoping via `trigger_event` string is functionally equivalent (a `deal_stage_changed` event physically can only be emitted by `deals.py`). An explicit column would improve query efficiency and enable validation at rule creation time; deferred to CRUD API slice |
| `created_by_id` and `updated_at` on `AutomationRule` | HubSpot, Pipedrive | Not in the shipped schema. `created_at` is present. `created_by_id` and `updated_at` deferred to CRUD API slice (needed for admin UI display) |
| `gt`, `lt`, `contains` condition operators | Attio, Salesforce | Planned in original design, not yet implemented. Shipped ops: `eq`, `neq`, `in`. An unknown op returns `False` (fail-closed). Adding these is straightforward in `evaluate_conditions()` and deferred to condition model slice |
| Zoho Blueprint (mandatory-gate model) | Zoho Blueprint | Different product requirement (blocking saves before stage move); CloseLoop's pipeline already has `validate_transition()`; no business requirement for mandatory-gate automation |
| Zoho CRM Analytics (reporting/dashboard) | Zoho CRM Analytics | Not an automation engine; materially different product surface (aggregated reporting, not per-record triggers); no relevant patterns for the automation engine |

---

## 4. Architecture: Extending the After-Save Hook Mechanism

The existing codebase has one trigger mechanism: **explicit inline calls in route handlers, before `db.commit()`**. Every domain mutation already calls `record_history()` and, for appropriate events, `create_notification()`. The automation evaluation pass is a third call in the same position.

### Current trigger site pattern (before automation wiring)

```python
# Current After-Save pattern in app/routers/deals.py (update_deal_stage)
record_history(db, entity_type="deal", entity_id=deal.id, event=..., clk=clk)
create_notification(db, recipient_id=..., event=..., entity_type="deal", entity_id=deal.id, clk=clk)
db.commit()
```

### Extended trigger site pattern (with automation wiring — not yet added)

```python
# Extended After-Save pattern — same position, same transaction
from app.services.automations import execute_automation_rules

record_history(db, entity_type="deal", entity_id=deal.id, event=..., clk=clk)
create_notification(db, recipient_id=..., event=..., entity_type="deal", entity_id=deal.id, clk=clk)
execute_automation_rules(
    db,
    trigger_event="deal_stage_changed",
    context={
        "deal_id": deal.id,
        "deal_title": deal.title,
        "stage": new_stage_name,
        "old_stage": old_stage_name,
        "value": deal.value,
        "owner_id": deal.owner_id,
        "actor_id": current_user.id,
        "entity_type": "deal",
        "entity_id": deal.id,
    },
    clk=clk,
)
db.commit()
```

`execute_automation_rules(db, *, trigger_event, context, clk)` in `app/services/automations.py`:
1. Queries `automation_rules` for rows where `trigger_event = ?` and `trigger_type = "after_save"` and `is_active = 1`.
2. For each matching rule, calls `_parse_conditions()` (fail-closed on `ConditionsParseError`).
3. Calls `evaluate_conditions(conditions, context)` — pure function, no DB I/O.
4. If conditions pass, calls `_execute_action(db, rule, context, clk)`.
5. Returns count of rules that fired (used in tests).

The caller still owns the transaction. The automation service layer follows the same contract as `create_notification()` and `record_history()`: `db.add()` but NOT `db.commit()`.

### Scheduled trigger architecture (shipped)

`run_scheduled_automations(db, *, clk)` in `app/services/automations.py` is the transaction-owning path for scheduled rules. It is called exclusively by `_scheduled_automations_loop()` in `app/main.py`, which runs as an `asyncio.create_task` in the FastAPI lifespan, polling every 60 s.

Unlike `execute_automation_rules`, the scheduler:
- Owns its DB transactions (commits the CAS claim before condition evaluation)
- Passes an empty `context = {}` (no entity snapshot — scheduled rules must use unconditional conditions or future entity scanning)
- Has no `actor_id` in context (no human actor for scheduled triggers)

The CAS (compare-and-swap) claim sequence:
```sql
-- If rule has never fired (NULL case):
UPDATE automation_rules SET last_triggered_at = :new
 WHERE id = :id AND last_triggered_at IS NULL

-- If rule has previously fired (non-NULL case):
UPDATE automation_rules SET last_triggered_at = :new
 WHERE id = :id AND last_triggered_at = :old
```

`rowcount == 0` → another Gunicorn worker already claimed this rule this cycle → skip. SQLite serialises concurrent writers through its write lock, so exactly one worker's `UPDATE` wins. The claim is committed before condition evaluation — `db.commit()` immediately after `rowcount == 1` — so a `conditions=false` outcome does not roll back the claim and re-expose the rule as due on the next cycle.

---

## 5. What Was Wrong in the Original Design (Resolved Divergences)

The original research doc (written 2026-07-04 as a planning document) proposed several schema details and patterns that diverged from what was actually implemented. These are recorded here to prevent re-deriving the same decisions:

| Original plan | Actual implementation | Why it changed |
|--------------|----------------------|----------------|
| Column `trigger_kind` | Column `trigger_event` | "event" is more precise: it names the specific mutation event, not an abstract trigger kind |
| Column `action_kind` | Column `action_type` | Consistent naming with `trigger_type` discriminator; "type" is the prevailing vocabulary in the codebase |
| Column `action_params_json` | Column `action_config_json` | "config" aligns with `schedule_config_json`; "params" implied positional parameters |
| Column `entity_type` on `AutomationRule` | Not present | Implicit scoping via `trigger_event` string is functionally equivalent; avoids redundant filtering |
| Condition ops: `eq, neq, gt, lt, contains` | Shipped ops: `eq, neq, in` | `gt`, `lt`, `contains` deferred; `in` (multi-value equality) was added — more useful for stage matching than `gt`/`lt` for current slice |
| `created_by_id` FK | Not present | Deferred to CRUD API slice |
| `updated_at` column | Not present | Deferred to CRUD API slice |
| Scheduled triggers: "permanently deferred" | Shipped in PRs #56–#58 | asyncio poller in FastAPI lifespan proved feasible without dedicated worker machinery; CAS claim solves the multi-worker race |
| `action_type = "notify_user"` | `action_type = "notify"` | Shorter; the recipient resolution handles "which user" |

---

## 6. Schema Design (Actual)

```
automation_rules
  id                    INTEGER PK
  name                  TEXT NOT NULL             human-readable label
  trigger_type          TEXT NOT NULL DEFAULT 'after_save'
                                                   "after_save" | "scheduled"
  trigger_event         TEXT NOT NULL DEFAULT ''   event string for after_save rules
                                                   (e.g. "deal_stage_changed");
                                                   empty string for scheduled rules
  conditions_json       TEXT                       nullable = unconditional fire;
                                                   JSON array of {field, op, value}
  action_type           TEXT NOT NULL             "notify" (shipped); future: "create_activity", "update_field"
  action_config_json    TEXT NOT NULL DEFAULT '{}' typed parameters for the action kind
  schedule_config_json  TEXT                       required for scheduled rules; NULL for after_save
                                                   {"interval_minutes": N} or {"run_once_at": "<ISO-8601>"}
  last_triggered_at     TEXT                       ISO-8601 UTC; NULL = never fired
                                                   updated atomically by CAS claim in run_scheduled_automations
  is_active             INTEGER NOT NULL DEFAULT 1  1 = active; 0 = disabled (skipped at query level)
  created_at            TEXT NOT NULL             ISO-8601 UTC (injected clock, ADR-0006)
```

Index: `(trigger_event, trigger_type, is_active)` — supports the `WHERE trigger_event=? AND trigger_type=? AND is_active=1` query at each after-save trigger site.

### `conditions_json` shape (list of `{field, op, value}` objects)

```json
[
  {"field": "stage", "op": "eq", "value": "won"},
  {"field": "owner_id", "op": "in", "value": [1, 2, 3]}
]
```

Empty list (`[]`) or NULL means "no conditions — always fire when trigger matches."  
Supported `op` values: `"eq"`, `"neq"`, `"in"` (shipped); `"gt"`, `"lt"`, `"contains"` (planned, not yet implemented).  
Unknown `op` → `evaluate_conditions` returns `False` (fail-closed).

### `action_config_json` shape for `"notify"` action type

```json
{"recipient_id": 42}
```
Static recipient — always notifies user 42.

```json
{"recipient_field": "owner_id"}
```
Dynamic recipient — resolves `context["owner_id"]` at fire time. Used for "notify the deal owner" rules where the owner varies per entity.

Missing recipient key → no notification, debug log. `"{}"` is a valid no-op placeholder (backward-compatible with test fixtures).

### `action_config_json` shape for planned `"create_activity"` action type (not yet implemented)

```json
{"title": "Follow-up call", "type": "call", "assigned_to_actor": true, "due_offset_days": 2}
```

---

## 7. Trigger Event Vocabulary

After-save rules use `trigger_event` strings drawn from the same vocabulary as `HistoryEntry.kind` in `app/core/history.py` (`_KIND_MAP`). The context dict passed to `execute_automation_rules` must always include `actor_id`, `entity_type`, and `entity_id` to enable the `notify` action to create a correctly attributed `Notification` row.

| trigger_event | Router + function | Context keys | Status |
|--------------|-------------------|-------------|--------|
| `deal_created` | `deals.py` → `create_deal` | deal_id, deal_title, stage, value, owner_id, actor_id, entity_type="deal", entity_id | ❌ Not wired |
| `deal_stage_changed` | `deals.py` → `update_deal_stage`, `update_deal` | deal_id, deal_title, stage (new), old_stage, value, owner_id, actor_id, entity_type, entity_id | ❌ Not wired |
| `deal_assigned` | `deals.py` → `update_deal` | deal_id, deal_title, owner_id (new), old_owner_id, actor_id, entity_type, entity_id | ❌ Not wired |
| `deal_updated` | `deals.py` → `update_deal` | deal_id, deal_title, stage, value, owner_id, actor_id, entity_type, entity_id | ❌ Not wired |
| `contact_created` | `contacts.py` → `create_contact` | contact_id, contact_name, owner_id, actor_id, entity_type="contact", entity_id | ❌ Not wired |
| `contact_updated` | `contacts.py` → `update_contact` | contact_id, contact_name, owner_id, actor_id, entity_type, entity_id | ❌ Not wired |
| `activity_created` | `activities.py` → `create_activity` | activity_id, activity_type, deal_id, contact_id, actor_id, entity_type="activity", entity_id | ❌ Not wired |
| `activity_completed` | `activities.py` → `complete_activity` | activity_id, activity_title, deal_id, contact_id, actor_id, entity_type, entity_id | ❌ Not wired |

---

## 8. Slice Plan (Updated)

### Slice 1 ✅ Done (PRs #53–#55): Rules model + condition evaluation

- `AutomationRule` ORM model in `app/models.py`
- `_parse_conditions`, `evaluate_conditions`, `execute_automation_rules` in `app/services/automations.py`
- Fail-closed `ConditionsParseError` invariant
- Tests in `tests/test_core_automations.py`
- **NOT included in shipped slice 1:** router wiring (listed as a deliverable in original doc; deferred)

### Scheduled trigger ✅ Done (PRs #56–#58)

- `trigger_type` discriminator, `schedule_config_json`, `last_triggered_at` columns
- `_parse_schedule_config`, `is_due`, `run_scheduled_automations` in `app/services/automations.py`
- `_scheduled_automations_loop()` asyncio poller in `app/main.py`
- CAS claim + commit-guard invariant
- Tests in `tests/test_automation_triggers.py` (67 test cases including commit-guard regression + concurrency test)

### Notify action ✅ Done (automation engine slice 3)

- `_parse_notify_config`, `_resolve_notify_recipient`, `_execute_notify_action` in `app/services/automations.py`
- `AutomationEvent` dataclass + `render_notification()` in `app/core/notifications.py`
- `_execute_action` dispatches `"notify"` to `_execute_notify_action`
- Unknown `action_type` → logged at warning + skipped (forward-compatible)
- Tests in `tests/test_automation_notification_action.py`

---

### Slice NEXT — After-Save Router Wiring (critical gap)

**What:** Call `execute_automation_rules()` inline in each of the 8 router trigger sites listed in §7, following the exact pattern already established for `record_history()` and `create_notification()`.

**Why this matters:** Without this wiring, after-save automation rules exist in the DB and are evaluated when called directly, but are never called during actual API requests. The engine is dormant.

**Implementation contract:**
- Import `execute_automation_rules` in `app/routers/deals.py`, `contacts.py`, `activities.py`
- Call it at each trigger site, **after** `record_history()` and `create_notification()`, **before** `db.commit()`
- Build the `context` dict from entity fields at that point in the handler (entity is flushed, so `.id` is available; the mutation is applied but not committed)
- Pass `actor_id=current_user.id` in every context dict
- Pass `entity_type` and `entity_id` in every context dict (needed by `_execute_notify_action` to populate the Notification row's navigation fields)

**Tests:** API integration tests in `tests/test_automation_triggers.py` should be extended — currently the scheduled-trigger tests cover `run_scheduled_automations` only. After-save trigger wiring tests should hit the API endpoint (e.g., `PATCH /deals/{id}/stage`) and assert that matching rules fire.

---

### Slice CRUD API — Rule Management

**What:** `app/routers/automation_rules.py` with full CRUD endpoints.

**Design notes:**
- `GET /automation-rules` — list all rules, ordered by `created_at DESC`
- `POST /automation-rules` — create; validate `trigger_type`, `trigger_event` (for after_save rules), `action_type`, condition `op` values, `schedule_config_json` (for scheduled rules)
- `GET /automation-rules/{id}` — get single rule; 404 if not found
- `PATCH /automation-rules/{id}` — update name, conditions, action config, `is_active`; 404 if not found
- `DELETE /automation-rules/{id}` — returns 204

**Role check:** Admin/manager only (same pattern as `pipeline.py`; `rep` role cannot manage automation rules).

**Validation:** `trigger_event` must be in the known event vocabulary (§7); `action_type` must be in the known action set; condition `op` values must be supported ops; `schedule_config_json` parsed via `_parse_schedule_config` at creation time to reject malformed config before it reaches the poller.

---

### Slice 3 (deferred) — Field-Level Condition Matching (from_value / to_value)

**What:** `entity_snapshot` extended to include `{"old_stage": ..., "new_stage": ...}` etc. New condition ops: `changed_from`, `changed_to`. Enables "deal stage changed from 'lead' to 'qualified'" conditions.

**Prerequisite:** After-save router wiring must be complete; the before-value must be captured in the handler before the mutation is applied.

---

### Slice 4 (deferred) — `create_activity` Action Type

**What:** `_execute_action` dispatches `"create_activity"` to `_execute_create_activity_action`. Creates an `Activity` row via `db.add()` (same transaction, caller owns commit). `action_config_json` shape: `{"title": "...", "type": "call", "assigned_to_actor": true, "due_offset_days": 2}`.

**Integration with history engine:** Creating an activity via automation should still fire `record_history()` for `activity_created` and emit `activity_created` trigger event. This creates a recursion risk: an `activity_created` after-save rule could fire `create_activity` which creates another activity, triggering the same rule again. Guard: set a flag on the automation-created Activity (e.g., `is_automated=1` column or pass `skip_automation=True` to the trigger site) to prevent recursive firing.

---

### Slice 5 (deferred) — Rule Execution Log + Frontend Rule Builder

**What:**
- `automation_executions` table: rule_id, entity_type, entity_id, trigger_event, fired_at, action_type, outcome (`fired` / `skipped_conditions` / `error`).
- `GET /automation-rules/{id}/executions` — recent execution log for debugging.
- Frontend rule builder: trigger event picker, condition builder (field selector + op + value), action type selector + config form, is_active toggle.

---

## 9. Open Design Questions for PHASE 2

These were not resolved in the shipped slices and must be decided before implementing the CRUD API and router wiring:

**Q1: Should `AutomationRule` have an explicit `entity_type` column?**

The original design planned it; the shipped schema omits it. The `trigger_event` string implicitly carries entity type information (`deal_stage_changed` implies `entity_type="deal"`). An explicit column enables:
- Validation at rule creation time ("this trigger event doesn't match the selected entity type")
- More efficient DB queries if rule count grows (add `entity_type` to the index)
- Clearer intent in the rule's representation

Decision: add `entity_type` to the `AutomationRule` model as part of the CRUD API slice. Not a breaking change — existing rows get `entity_type` backfilled from `trigger_event` prefix.

**Q2: What context keys does each trigger site pass, and how are they standardised?**

The notify action resolves recipient via `context["owner_id"]` or `context["recipient_id"]`, and gets navigation context from `context["entity_type"]` / `context["entity_id"]`. The `create_activity` action will need `context["actor_id"]` for assignment and `context["deal_id"]` / `context["contact_id"]` for the created activity's FK.

Decision: define a standard context shape per trigger event in §7 (already done above) and enforce it with tests. The context dict is the public contract between the trigger site and the action handlers.

**Q3: How should the scheduled trigger interact with entity scanning?**

Currently, scheduled rules fire the `notify` action with an empty context (no entity). A scheduled rule cannot currently say "notify the owner of every deal in stage X" — it can only notify a hardcoded `recipient_id`. Entity-relative scheduled triggers require:
- Querying all matching entities at fire time (e.g., all deals in stage "won" for more than 30 days)
- Evaluating conditions against each entity's snapshot
- Creating one notification per matching entity

This is a fundamentally different execution model from the current scheduled trigger (one fire → one action). It is closer to Salesforce's Scheduled Paths or Zoho's time-based actions. Defer to a separate slice.

---

## 10. Key Design Conclusion

The workflow automation rules engine is **not a new trigger mechanism**. It is an evaluation pass that runs at the existing After-Save hook sites — the same sites where `create_notification()` and `record_history()` are already called, in the same position (after the domain mutation, before `db.commit()`), under the same transaction ownership contract.

This is the only architecture consistent with:
- CloseLoop's single-process, single-SQLite deployment model
- ADR-0010's prohibition on runtime outbound network calls (which rules out a separate event bus or background scanner)
- ADR-0001's separation of pure core functions from I/O (condition evaluation is pure; DB reads and writes live in services)
- The established pattern from the notifications engine (PR #43) and audit history (PR #46–47)

The scheduled trigger (asyncio poller in FastAPI lifespan + CAS claim) is the only exception: it owns its own transactions and runs outside the request-response cycle, but it does not violate ADR-0010 (no outbound calls) and does not introduce a second event bus (it polls the `automation_rules` table directly, not an intermediate queue).

Any implementation that introduces ORM hooks, a background worker with its own event queue, a pub/sub bus, or any trigger path that is not either (a) an explicit call in a route handler or (b) `run_scheduled_automations()` called by the asyncio poller **conflicts with this design and must be rejected**.

The most important next step is the after-save router wiring: calling `execute_automation_rules()` inline in the 8 trigger sites listed in §7. All other slices depend on this being in place.
