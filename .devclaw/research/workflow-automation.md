# Workflow Automation — Reference CRM Research & Design Synthesis

**Status:** Accepted — implementation begins with slice 1 (rules table + condition evaluation + trigger wiring into existing After-Save hook sites).
**Date:** 2026-07-04
**Scope of this doc:** Reference CRM survey, borrowed/rejected patterns, and slice-by-slice build plan for CloseLoop's user-configurable workflow automation engine.

---

## 1. What We're Building and Why

CloseLoop's domain brief (§13) identifies workflow automation as the next layer on top of the event-driven plumbing already established for notifications (PR #43) and audit history (PR #46–47). The existing After-Save trigger mechanism already fires at every domain mutation; automation adds a user-configurable rules evaluation pass at those same sites, enabling "when X happens and Y is true, do Z" rules without any additional trigger infrastructure.

The two previously hardcoded surfaces that automation generalises:

| Surface | Current state | Automation adds |
|---------|--------------|-----------------|
| In-app notifications | Hardcoded: stage change + deal assigned only | User-defined "notify user X when field Y = Z" |
| Activity/task creation | Manual only | Auto-create a task when a deal enters a stage |

The three design tensions:

1. **Trigger timing** — event-based (fires on domain mutation) vs. scheduled (time-based cron). CloseLoop has no background worker and ADR-0010 prohibits outbound network calls; scheduled triggers require worker machinery CloseLoop does not have. Event-based only for all slices.
2. **Condition/action composition** — visual flow canvas vs. declarative JSON rules vs. inline code. Visual builders require a rich admin UI and are costly to build; hardcoded inline code is not user-configurable. Declarative JSON rules (stored in the DB, evaluated at the trigger site) are the appropriate middle ground for CloseLoop's scope.
3. **Trigger registration** — a second trigger mechanism (ORM hooks, a background scanner, or a pub/sub bus) vs. extending the existing After-Save hook sites. A second mechanism creates two competing trigger paths that must be kept in sync and makes the codebase harder to follow. The After-Save hook sites already exist at every mutation; automation evaluation is an additional pass at those same sites, not a new mechanism.

**Critical architecture constraint (stated explicitly up front):** The rules engine MUST extend the existing After-Save hook mechanism (`create_notification()` / `record_history()` called inline in route handlers, before `db.commit()`). It MUST NOT introduce a second competing trigger mechanism such as SQLAlchemy ORM event hooks (`after_flush` / `after_commit`), a background scanner, a pub/sub event bus, or any other parallel trigger path.

---

## 2. Reference CRM Survey

Five reference CRMs were surveyed. The patterns borrowed and rejected are summarised in §3.

### 2.1 Salesforce (Flow / Process Builder)

**Automation model:** Salesforce offers two overlapping automation layers. *Process Builder* (now deprecated in favour of Flow) fires on record create/edit and evaluates criteria, then executes actions (field updates, send email, create task, invoke Apex). *Flow Builder* is a visual drag-and-drop canvas that supports both event-based (Record-Triggered Flow) and scheduled triggers. Record-Triggered Flows run *After Save* — they share the transaction context and can update related records in the same commit. Criteria are evaluated as a combination of field-value conditions with AND/OR operators, with a visual expression builder.

**Key patterns borrowed:**
- **After-Save execution model.** Salesforce Record-Triggered Flows fire in the same save transaction as the mutation that triggered them. There is no async step, no queue handoff. CloseLoop's existing After-Save hook sites (`deals.py`, `contacts.py`, `activities.py`) already implement this timing contract; automation rule evaluation is an additional step in that same position.
- **Trigger kind as a closed enum.** Each Salesforce flow is configured for a specific `Object` (Deal, Contact) and `Trigger Type` (Create, Update, Delete). The combination maps to a closed set of trigger events. CloseLoop borrows this: the set of trigger kinds is the intersection of the existing `_KIND_MAP` in `app/core/history.py` — no new trigger taxonomy is invented.
- **Declarative condition criteria.** Process Builder / Flow criteria are expressed as field-operator-value triples (`stage EQUALS 'won'`, `value GREATER_THAN 10000`). CloseLoop's condition model follows this shape: `{"field": "stage", "op": "eq", "value": "won"}` — simple, JSON-serialisable, evaluatable as a pure function.
- **Action types: field update, task creation, notification.** Salesforce actions are typed: "Update Records", "Create Records", "Send Notification". CloseLoop adopts the same action taxonomy, starting with `notify_user` and `create_activity` for slice 1–2.

**Rejected from Salesforce:**
- **Visual Flow Builder canvas.** Salesforce Flow's drag-and-drop UI is the right end-state for a large platform but is expensive to build and out of scope for CloseLoop's current scale. CloseLoop uses a declarative JSON rule stored in the DB; the admin UI for creating rules is deferred to slice 2.
- **Scheduled / time-based triggers.** Salesforce supports "Scheduled Paths" — run this action 3 days after a deal's close date. CloseLoop has no background worker and ADR-0010 prohibits outbound calls; there is no runtime component that can fire rules on a schedule. Event-based triggers only.
- **Cross-object update actions.** Salesforce flows can cascade updates to related records (update the Contact when the Deal stage changes). This requires a generalized field-write path across entity types and is not needed for slice 1. Deferred.
- **OR-logic in condition criteria.** Salesforce supports complex boolean expressions (AND/OR trees). CloseLoop starts with AND-only conjunctive conditions — sufficient to cover the common patterns (stage = X AND value > Y) without the complexity of a full expression evaluator.

---

### 2.2 HubSpot Workflows

**Automation model:** HubSpot Workflows are the most widely referenced automation model in the SMB CRM segment. A workflow has an *enrollment trigger* (a property-change event or a static/smart list membership change), optional *re-enrollment criteria*, and a linear sequence of *actions* (send email, set property, create task, add to list, branch on condition). Actions execute in order; a "Delay" action pauses the sequence until a time condition is met. Each workflow is associated with a single object type (Deal, Contact, Company).

**Key patterns borrowed:**
- **Single-object-type scope per rule.** HubSpot requires each workflow to be associated with one object type. CloseLoop follows this: each `AutomationRule` carries an `entity_type` column (`"deal"` / `"contact"` / `"activity"`). Rules scoped to deal triggers cannot fire on contact mutations — keeping trigger evaluation O(relevant rules) rather than O(all rules).
- **Enrollment criteria as declarative property filters.** HubSpot's enrollment trigger is a set of property conditions (`Deal Stage is any of ['Closed Won']`, `Deal Amount is greater than 10000`). This maps directly to CloseLoop's `conditions_json` array of `{field, op, value}` objects. The `evaluate_conditions()` pure function in `app/core/automations.py` is the equivalent of HubSpot's criteria evaluator.
- **Action type: "Create task."** HubSpot's "Create task" action is one of its most-used automation actions in deal workflows — automatically create a follow-up activity when a deal moves to a stage. CloseLoop adopts this as the `create_activity` action kind in slice 2.
- **Self-notification suppression.** HubSpot suppresses enrollment for rules where the enrolling actor is the rule creator when the rule's purpose is to alert someone of someone else's action. CloseLoop retains the existing self-notification suppression pattern (actor == recipient → no notification) for automation-triggered notifications.

**Rejected from HubSpot:**
- **Delay actions / time-based sequencing.** HubSpot's "Delay until date" and "Delay for X days" actions require a persistent scheduler that re-activates workflow instances at a future time. CloseLoop has no background worker; all actions must execute synchronously in the same After-Save transaction. Delay actions are explicitly out of scope for all slices in this document.
- **Re-enrollment logic.** HubSpot tracks whether a record has previously enrolled in a workflow and provides re-enrollment criteria (re-enroll if a property changes back). This requires per-record execution state in the DB and significantly complicates the evaluation model. CloseLoop rules are stateless: they fire whenever their trigger and conditions match, with no enrollment history.
- **Branching inside a single rule (If/Then branch action).** HubSpot allows a workflow to branch into two paths based on a mid-sequence condition. CloseLoop keeps rules flat: one trigger + conditions → one action. Multiple outcomes are handled by having multiple rules, not by branching inside a single rule.
- **Email send action.** HubSpot's most common automation action is sending an email. ADR-0010 prohibits runtime outbound network calls; all email delivery is enqueued in the outbox and sent by a separate process. Email automation is out of scope until the outbox layer is production-proven.

---

### 2.3 Pipedrive Automations

**Automation model:** Pipedrive Automations are purely event-based (no scheduled triggers). Each automation has a *trigger event* (Deal created, Deal stage changed, Deal won, Activity added, etc.), optional *conditions* (field filters on the triggering entity), and one or more *actions* (Update deal field, Create activity, Send email, Add follower). The trigger event set is a closed, documented enum.

**Key patterns borrowed:**
- **Closed trigger event enum matching the existing kind set.** Pipedrive's trigger events (`deal_created`, `deal_stage_changed`, `deal_won`, `deal_lost`, `activity_added`) map directly to CloseLoop's existing history event kind set (`_KIND_MAP` in `app/core/history.py`). CloseLoop borrows this mapping: `AutomationRule.trigger_kind` is drawn from the same closed set as `HistoryEntry.kind`. No new taxonomy is needed; the trigger kind vocabulary is already established.
- **Conditions as field-value filters on the triggering entity snapshot.** Pipedrive conditions check field values at the moment of the trigger event (e.g., "Deal Stage equals Closed Won"). CloseLoop's `evaluate_conditions()` receives an entity snapshot dict (the field values at the time of the mutation) and evaluates the condition list against it — the same model.
- **Action: "Create activity."** Pipedrive's most common automation action is creating a follow-up activity/task. This is the second action type CloseLoop plans (slice 2), after `notify_user`.
- **No-op when conditions don't match.** Pipedrive automations silently skip if conditions are not met. CloseLoop's `evaluate_conditions()` returns `False`; the caller skips action execution. No error, no logging for non-matching rules.

**Rejected from Pipedrive:**
- **Email action (outbound).** Prohibited by ADR-0010.
- **Multi-action sequences within a single automation.** Pipedrive allows chaining actions in one automation (update field, then create activity, then send email). CloseLoop uses one action per rule and composes outcomes by having multiple rules with the same trigger. This keeps rule evaluation stateless and the execution model simple.
- **"Add follower" action.** Pipedrive can add a user as a follower of a deal via automation. CloseLoop has no follower/watcher model. Out of scope.

---

### 2.4 Attio Automations

**Automation model:** Attio is the most modern reference CRM for this feature. Automations are event-based only: they fire on attribute changes, record stage transitions, or record creation. Each automation has a trigger (object + event type), optional attribute-level conditions, and one or more actions (send a notification, update an attribute, create a record). Attio's automation model is notably close to CloseLoop's current hardcoded trigger pattern — each trigger fires inline at the record-mutation point, evaluates conditions, and writes side-effects in the same operation.

**Key patterns borrowed:**
- **Trigger fires at the mutation site, not via a separate observer.** Attio's engineering blog describes automation triggers as executing "at the point of the attribute write, synchronously, before the response is sent." This is architecturally identical to CloseLoop's existing After-Save hook: `create_notification()` / `record_history()` are called inline in the route handler, before `db.commit()`. The automation evaluation loop slots into exactly this position.
- **"Notify a team member" as a first-class action type.** Attio's most prominent automation action is sending an in-app notification to a team member. CloseLoop's `notify_user` action calls the existing `create_notification()` service function — automation is a new caller of an existing service, not a new notification path.
- **Condition: attribute equality and comparison operators.** Attio conditions use `equals`, `not_equals`, `greater_than`, `less_than`, `contains` operators on strongly-typed attributes. CloseLoop's condition model uses `eq`, `neq`, `gt`, `lt`, `contains` — the same set, expressed as JSON.
- **Per-entity-type rule scoping.** Attio automations are scoped to a specific object type (Deals, People, Companies). CloseLoop's `AutomationRule.entity_type` column enforces the same scoping — a deal-scoped rule is never evaluated during a contact mutation.

**Rejected from Attio:**
- **Attribute-level change triggers ("when attribute X changes from A to B").** Attio supports triggers that fire specifically when a given attribute changes from one value to another (not just that the record was mutated). This requires capturing old and new values at every trigger site. CloseLoop's current trigger sites already capture before/after state for notification purposes (see `update_deal` in `app/routers/deals.py`, lines 406–408), but generalising this to all entity types and all fields for rule evaluation adds complexity deferred to slice 3 (field-level condition matching).
- **Webhook / HTTP action.** Attio can POST to an external URL as an automation action. ADR-0010 prohibits runtime outbound network calls; webhook actions are out of scope for all slices.
- **Multi-step sequences with delays.** Same rejection as HubSpot: no background worker to resume paused sequences.

---

### 2.5 Zoho Blueprint / Zoho Workflow Rules

**Automation model:** Zoho offers two overlapping automation mechanisms. *Workflow Rules* are event-based (trigger on record create, edit, or delete) + time-based (fire N days before/after a field date). Each rule has criteria (field-value filters) and actions (email alert, field update, create task, invoke webhook, trigger another workflow). *Blueprint* is a different, stage-machine-oriented mechanism: it overlays a mandatory process on the pipeline stages, enforcing that specific actions must be completed before a deal can move to the next stage.

**Key patterns borrowed:**
- **Workflow Rules declarative model: trigger → criteria → actions.** Zoho Workflow Rules are the most explicit reference for CloseLoop's `AutomationRule` schema: a single row carrying `trigger_kind`, `conditions_json`, `action_kind`, `action_params_json`. The evaluation model is identical: load matching rules for the trigger kind, evaluate criteria, execute action if criteria pass.
- **"Create Task" action with owner and due-offset parameters.** Zoho's "Create Task" action supports configuring the assignee and due date (e.g., "due 3 days after trigger date"). CloseLoop's `create_activity` action params carry `title`, `type`, `assigned_to_actor` (boolean — assign to the actor who triggered the rule), and `due_offset_days` (integer, optional). The due offset is resolved at execution time using the injected clock (ADR-0006): `clk.now() + timedelta(days=offset)`.
- **Self-notification suppression in "Email Alert" actions.** Zoho's email alert action has a "Don't send to the record owner if they triggered the workflow" checkbox. CloseLoop carries this through the existing `actor_id != recipient_id` guard in `create_notification()` — automation-triggered notifications reuse the same suppression logic.

**Rejected from Zoho:**
- **Blueprint (mandatory stage-gating).** Zoho Blueprint enforces that specific actions must be completed before a stage transition is allowed — it blocks the save if pre-conditions are not met. CloseLoop's pipeline transitions already have a state machine (`app/core/stages.py`, `validate_transition()`); Blueprint-style mandatory-action gates are a fundamentally different product requirement not in the current scope.
- **Time-based Workflow Rules.** Zoho allows rules to fire "X days after the close date field." This requires background worker infrastructure. CloseLoop has none; time-based triggers are out of scope for all slices.
- **"Invoke webhook" action.** ADR-0010 prohibits runtime outbound network calls.
- **Rule chaining (trigger another workflow from an action).** Zoho allows a workflow action to trigger another workflow, creating chains. This introduces re-entrancy risk and execution-order complexity. CloseLoop rules are unconditionally non-recursive: executing an action does not re-evaluate the rule set for that action's side effects.

---

## 3. Patterns Summary: Borrowed vs. Rejected

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| After-Save execution timing (same transaction as the mutation) | Salesforce Flow, Attio | Automation evaluation call added inline in route handlers, before `db.commit()`, alongside existing `create_notification()` / `record_history()` calls |
| Closed trigger kind enum | Salesforce, Pipedrive | `AutomationRule.trigger_kind` drawn from `_KIND_MAP` in `app/core/history.py` — no new taxonomy |
| Per-entity-type rule scoping | HubSpot, Attio, Pipedrive | `AutomationRule.entity_type` column; only rules matching the mutated entity type are evaluated |
| Declarative `{field, op, value}` condition triples | Salesforce, HubSpot, Zoho | `conditions_json` array on `AutomationRule`; `evaluate_conditions(entity_snapshot, conditions)` pure function in `app/core/automations.py` |
| AND-only conjunctive condition evaluation | Salesforce, Pipedrive, Attio | All conditions in the list must pass; no OR logic in slice 1 |
| Entity snapshot dict passed to condition evaluator | Salesforce, Attio | Route handler builds snapshot dict from entity fields at trigger time; passed to `evaluate_automation_rules()` in `app/services/automations.py` |
| Action type: `notify_user` (reuses `create_notification()`) | Attio, Zoho | `execute_automation_action()` calls the existing `create_notification()` service function — no new notification path |
| Action type: `create_activity` with due-offset params | Zoho, Pipedrive | `action_params_json` carries `title`, `type`, `assigned_to_actor`, `due_offset_days`; resolved at execution time using injected clock |
| Self-notification suppression in automation-triggered notifs | HubSpot, Zoho | Reuses existing `actor_id != recipient_id` guard in `create_notification()` |
| No creation endpoint for rules in the trigger path | Salesforce, HubSpot, Attio | No `POST /automation-rules/trigger` — rules execute via trigger wiring, not via API |

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Visual flow canvas (drag-and-drop) | Salesforce Flow Builder | Expensive admin UI, out of scope for current scale; JSON rule stored in DB is sufficient |
| Scheduled / time-based triggers | Salesforce, HubSpot, Zoho | ~~No background worker; ADR-0010 prohibits outbound calls; no runtime component can fire rules on a schedule~~ **Reversal:** this pattern was subsequently implemented (see `DOMAIN.md §ScheduledTrigger`). A minimal asyncio poller (`_scheduled_automations_loop` in `app/main.py`) provides the background worker without violating ADR-0010 (no outbound calls). The full Salesforce "Scheduled Paths" pattern (trigger N days after a *field* value) remains deferred. |
| Multi-action sequences / chaining | HubSpot, Pipedrive, Zoho | Requires persistent execution state and scheduler; one action per rule, composable by having multiple rules |
| Delay actions within a rule | HubSpot, Salesforce | Requires persistent scheduler to resume paused rule instances; incompatible with synchronous After-Save execution |
| OR-logic / complex boolean expression trees | Salesforce, HubSpot | AND-only conjunctive evaluation is sufficient for initial patterns; full expression trees add evaluator complexity |
| Attribute-change trigger (from A to B) | Attio | Requires generalised before/after snapshot for all fields; deferred to slice 3 |
| Outbound actions (email, webhook) | Pipedrive, HubSpot, Zoho, Attio | ADR-0010 prohibits runtime outbound network calls |
| Re-enrollment tracking per record | HubSpot | Requires per-record execution history table; rules are stateless (fire every time trigger + conditions match) |
| Rule chaining / recursive firing | Zoho | Re-entrancy risk; action execution does not re-evaluate the rule set |
| SQLAlchemy ORM hooks (`after_flush` / `after_commit`) | (natural alternative) | Creates a second competing trigger mechanism alongside the explicit After-Save hook calls; makes trigger sites implicit and harder to follow — same rejection reason as in `activity-timeline.md §3` |
| Blueprint mandatory-action gates | Zoho | Different product requirement (blocking saves); pipeline transitions already have state machine in `app/core/stages.py` |
| Background scanner for trigger detection | Zoho, (natural alternative) | No background worker machinery; same rejection as in `notifications-engine.md §2.5` |

---

## 4. Architecture: Extending the After-Save Hook Mechanism

The existing codebase has one trigger mechanism: **explicit inline calls in route handlers, before `db.commit()`**. Every domain mutation already calls `record_history()` and, for appropriate events, `create_notification()`. The automation evaluation pass is a third call in the same position.

Concretely, a trigger site today looks like:

```python
# existing After-Save pattern in app/routers/deals.py
record_history(db, entity_type="deal", entity_id=deal.id, event=..., clk=clk)
create_notification(db, recipient_id=..., event=..., entity_type="deal", entity_id=deal.id, clk=clk)
db.commit()
```

With automation added:

```python
# extended After-Save pattern — same position, same transaction
record_history(db, entity_type="deal", entity_id=deal.id, event=..., clk=clk)
create_notification(db, recipient_id=..., event=..., entity_type="deal", entity_id=deal.id, clk=clk)
execute_automation_rules(db, trigger_kind="deal_stage_changed", entity_type="deal",
                          entity_snapshot={"stage": deal.stage, "value": deal.value, ...},
                          actor=current_user, clk=clk)
db.commit()
```

`execute_automation_rules()` in `app/services/automations.py`:
1. Queries `automation_rules` for rows where `trigger_kind = ?` and `entity_type = ?` and `is_active = 1`.
2. For each matching rule, calls `evaluate_conditions(entity_snapshot, rule.conditions)` (pure function, no DB I/O).
3. If conditions pass, calls `execute_automation_action(db, rule, actor, clk)` — which in turn calls either `create_notification()` or inserts a new `Activity` row, both of which call `db.add()` but do NOT commit.
4. Returns the list of rules that fired (used in tests to assert trigger behaviour).

The caller still owns the transaction. The automation service layer follows the same contract as `create_notification()` and `record_history()`: `db.add()` but NOT `db.commit()`.

**This is the only trigger mechanism.** There are no ORM hooks, no background scanner, no pub/sub bus. The automation engine is a consumer of the existing event vocabulary, not a producer of a new one.

---

## 5. Slice Plan

### Slice 1 (this implementation): Rules table + condition evaluation + trigger wiring

**Deliverables:**
- `app/core/automations.py` — pure typed definitions: `Condition` dataclass (`field`, `op`, `value`), `AutomationAction` dataclass, `evaluate_conditions(entity_snapshot: dict, conditions: list[Condition]) -> bool`, `SUPPORTED_OPS: frozenset` (`eq`, `neq`, `gt`, `lt`, `contains`), `SUPPORTED_TRIGGER_KINDS: frozenset` (intersection with `_KIND_MAP`), `SUPPORTED_ENTITY_TYPES: frozenset`.
- `AutomationRule` ORM model in `app/models.py` (`automation_rules` table).
- `app/services/automations.py` — `execute_automation_rules(db, *, trigger_kind, entity_type, entity_snapshot, actor, clk)` (query + evaluate + execute loop) and `execute_automation_action(db, rule, actor, clk)` (dispatches to `create_notification()` or `Activity` insert).
- Trigger wiring: `execute_automation_rules()` called inline in `app/routers/deals.py` at `create_deal`, `update_deal_stage`, `update_deal`; in `app/routers/contacts.py` at `create_contact`, `update_contact`; in `app/routers/activities.py` at `create_activity`, `complete_activity`.
- Tests: `tests/test_core_automations.py` (pure — `evaluate_conditions` all ops, edge cases, empty conditions → always fires) + `tests/test_automation_triggers.py` (API integration — rule fires on trigger, rule skips on condition mismatch, inactive rules skip).

**Explicitly out of scope:**
- REST API for creating/updating/deleting rules (slice 2).
- `create_activity` action type (slice 2).
- Field-level (from_value/to_value) condition matching (slice 3).
- Scheduled triggers (permanently deferred — no background worker).
- Visual rule builder UI (later).

---

### Slice 2: CRUD API for automation rules + `create_activity` action

**Deliverables:**
- `app/routers/automation_rules.py` — `GET /automation-rules`, `POST /automation-rules`, `GET /automation-rules/{id}`, `PATCH /automation-rules/{id}`, `DELETE /automation-rules/{id}` (admin-only endpoints, role check on `current_user.role`).
- Validation: `trigger_kind` must be in `SUPPORTED_TRIGGER_KINDS`; `action_kind` must be in `{"notify_user", "create_activity"}`; `conditions` validated against `SUPPORTED_OPS`.
- `create_activity` action type wired into `execute_automation_action()`: inserts `Activity` row with `due_at = clk.now() + timedelta(days=due_offset_days)`.
- Tests for CRUD API + `create_activity` action firing.

---

### Slice 3: Field-level condition matching (from_value / to_value)

**Deliverables:**
- `entity_snapshot` extended to include `{"field": {"old": before_value, "new": after_value}}` for mutation events where before/after state is already captured (deals: `old_stage`, `old_owner_id`; generalised for contacts in this slice).
- New condition op: `changed_from` / `changed_to` — matches against the `old` or `new` value respectively.
- Conditions can now target "deal stage changed from 'lead' to 'qualified'" specifically.

---

### Slice 4 (later): Rule execution log + frontend rule builder

**Deliverables:**
- `automation_executions` table: rule_id, entity_type, entity_id, trigger_kind, fired_at, action_kind, outcome (`success` / `skipped` / `error`).
- `GET /automation-rules/{id}/executions` — recent execution log for debugging.
- Frontend rule builder: trigger kind picker, condition builder, action type selector.

---

## 6. Schema Design

```
automation_rules
  id                INTEGER PK
  name              TEXT NOT NULL             human-readable label
  entity_type       TEXT NOT NULL             "deal" / "contact" / "activity"
  trigger_kind      TEXT NOT NULL             from SUPPORTED_TRIGGER_KINDS
  conditions_json   TEXT NOT NULL DEFAULT '[]'  serialised list[Condition]
  action_kind       TEXT NOT NULL             "notify_user" / "create_activity"
  action_params_json TEXT NOT NULL            serialised action parameters (per action_kind)
  is_active         INTEGER NOT NULL DEFAULT 1  0 = disabled, 1 = active
  created_by_id     INTEGER → users(id) ON DELETE SET NULL
  created_at        TEXT NOT NULL             ISO-8601 UTC
  updated_at        TEXT NOT NULL             ISO-8601 UTC
```

Index: `(entity_type, trigger_kind, is_active)` — supports the `WHERE entity_type=? AND trigger_kind=? AND is_active=1` query at each trigger site.

**`conditions_json` shape (list of `{field, op, value}` objects):**

```json
[
  {"field": "stage", "op": "eq", "value": "won"},
  {"field": "value",  "op": "gt", "value": 5000}
]
```

Empty list (`[]`) means "no conditions — always fire when trigger matches."

**`action_params_json` shape for `notify_user`:**

```json
{"recipient_id": 42, "message_template": "Deal {deal_title} moved to {stage}"}
```

`recipient_id` is a user PK. `message_template` is rendered by a pure function in `app/core/automations.py` with the entity snapshot as context variables.

**`action_params_json` shape for `create_activity`:**

```json
{"title": "Follow-up call", "type": "call", "assigned_to_actor": true, "due_offset_days": 2}
```

`assigned_to_actor: true` assigns the created activity to the user who triggered the rule (the actor). `due_offset_days` is resolved at execution time using the injected clock (ADR-0006).

---

## 7. API Surface (Slice 2)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/automation-rules` | Bearer (admin/manager) | List all rules, ordered by `created_at DESC`. |
| POST | `/automation-rules` | Bearer (admin/manager) | Create a rule. Validates `trigger_kind`, `action_kind`, condition `op` values. Returns 201. |
| GET | `/automation-rules/{id}` | Bearer (admin/manager) | Get a single rule. 404 if not found. |
| PATCH | `/automation-rules/{id}` | Bearer (admin/manager) | Update name, conditions, action params, or `is_active`. 404 if not found. |
| DELETE | `/automation-rules/{id}` | Bearer (admin/manager) | Delete a rule. Returns 204. |

Rules are executed by trigger wiring (slice 1), not by an explicit API endpoint. This is consistent with the notifications and history services: the execution path is internal, not a public REST endpoint.

---

## 8. Key Design Conclusion

The workflow automation rules engine is **not a new trigger mechanism**. It is an evaluation pass that runs at the existing After-Save hook sites — the same sites where `create_notification()` and `record_history()` are already called, in the same position (after the domain mutation, before `db.commit()`), under the same transaction ownership contract.

This is the only architecture consistent with:
- CloseLoop's single-process, single-SQLite deployment model
- ADR-0010's prohibition on runtime outbound network calls (which rules out a separate event bus or background scanner)
- ADR-0001's separation of pure core functions from I/O (condition evaluation is pure; DB reads and writes live in services)
- The established pattern from the notifications engine (PR #43) and audit history (PR #46–47)

Any implementation that introduces ORM hooks, a background worker, a pub/sub bus, or any trigger path that is not an explicit call in a route handler **conflicts with this design and must be rejected**.
