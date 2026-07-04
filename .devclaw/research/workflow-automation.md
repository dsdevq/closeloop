# Workflow Automation — Reference CRM Research & Design Synthesis

**Status:** Accepted — implementation begins with slice 1 (AutomationRule data model + scheduled trigger parsing).
**Date:** 2026-07-04
**Scope of this doc:** Reference CRM survey, borrowed/rejected patterns, and slice-by-slice build plan for CloseLoop's workflow automation engine.

---

## 1. What We're Building and Why

CloseLoop's domain brief (§13) identifies workflow automation as the next major surface after notifications and history: reps should be able to define rules that fire automatically when a deal or contact is saved, or on a time-based schedule (e.g., "7 days after expected close date, create a follow-up task"). This removes manual follow-up toil and closes the loop between CRM data and rep action.

Two trigger families emerged from the reference CRM survey:

| Trigger family | Description | Reference CRM term |
|----------------|-------------|-------------------|
| **After-Save** | Fires synchronously when a matching entity mutation is committed | Salesforce "Record-Triggered Flow" · HubSpot "Property-Based Enrollment" · Pipedrive "Automation Trigger on Deal Update" |
| **Scheduled** | Fires on a time-based cadence — either a fixed interval or *N* days before/after a date field on the entity | Salesforce "Scheduled Actions" · HubSpot "Delay Step (relative to date property)" · Zoho "Time-Based Action" |

Both trigger families share the same rule shape: a trigger, a set of conditions evaluated against the entity, and an action config. They differ only in **when** the rule fires. This document argues that both must be first-class in the data model from day one, even if the scheduler-wiring (execution path for scheduled rules) is deferred to a follow-up PR.

---

## 2. Reference CRM Survey

### 2.1 Salesforce (Flow Builder — Record-Triggered Flows + Scheduled Actions)

**Automation model:** Salesforce's Flow Builder exposes two trigger types on a single "Flow" record:
1. **Record-Triggered (After-Save):** The flow fires every time a record matching the object type and entry conditions is saved. The flow runs synchronously in the same transaction context (for immediate actions) or is queued for async execution (for scheduled actions attached to the same flow).
2. **Scheduled Actions within a Record-Triggered Flow:** Salesforce lets users attach "scheduled action paths" to an after-save flow. Each path fires *N* hours/days/weeks *after a date field* on the record (e.g., "3 days after Close Date"). The scheduler re-evaluates the conditions at fire time, not at trigger time.

**Key patterns borrowed:**
- **Single rule concept with two trigger modes.** Salesforce does not have separate "Record-Triggered Flow" and "Scheduled Flow" tables — a single Flow record has a `TriggerType` field (`RecordBeforeSave`, `RecordAfterSave`, or `Scheduled`). CloseLoop adopts this: a single `automation_rules` table with a `trigger_type` column (`after_save` | `scheduled`). No parallel table, no second rule concept.
- **Scheduled actions anchor to a date field on the entity.** Salesforce's scheduled paths specify: (a) a date-type field on the triggering object, and (b) a +/- offset in days/hours. This "field_offset" mode is clean, composable, and avoids hardcoded timestamps. CloseLoop implements this as `ScheduleConfig(mode="field_offset", anchor_field="expected_close_date", offset_days=3)`.
- **`last_fired_at` to prevent double-firing.** Salesforce's scheduler tracks when a flow last fired for a given record to suppress duplicate executions within the same window. CloseLoop stores `last_fired_at` on the rule row (not the entity) for interval-mode rules where the cadence is entity-independent. The `is_rule_due()` function uses `last_fired_at` as its interval fence.

**Rejected from Salesforce:**
- **Async action queue within the same flow.** Salesforce queues scheduled actions in a separate async queue (`AsyncApexJob`). CloseLoop has no background worker machinery (ADR-0010: outbound-call-free). The scheduler wiring will be a synchronous scan, not an async queue.
- **Per-record schedule tracking.** Salesforce tracks scheduled action state per record (each record gets its own "scheduled to fire at" entry). For CloseLoop's first slice, `last_fired_at` is at the rule level (not per-entity), which is correct for interval-mode rules and sufficient for the initial scheduled-action use cases (field_offset mode re-evaluates at fire time).

---

### 2.2 HubSpot Workflows (Delay / Time-Based Steps)

**Automation model:** HubSpot Workflows supports two enrollment triggers: property-based (a contact/deal enters the workflow when a property matches a filter) and scheduled (a fixed date or relative-to-property delay). Within a workflow, "delay steps" pause execution for a fixed duration or until *N* days before/after a date property. The Workflow record itself has a single `type` field distinguishing the trigger mode.

**Key patterns borrowed:**
- **Delay-scheduling relative to a date property.** HubSpot's "X days before/after [date property]" is the canonical form of field_offset scheduling. The reference CRM most cited by CRM practitioners when they ask for "send a follow-up task 7 days before deal close date." CloseLoop's `ScheduleConfig.mode = "field_offset"` with `offset_days` (which may be negative for "before") is directly modeled on this pattern.
- **`is_enrolled` / `is_active` flag on the rule.** HubSpot workflows can be turned on/off without deletion. CloseLoop stores `is_active` (INTEGER 1/0) on `AutomationRule` — toggling a rule off pauses execution without data loss.
- **Conditions evaluated at enrollment AND at fire time.** HubSpot re-evaluates conditions when a scheduled step fires, not just when enrollment occurs. CloseLoop's `is_rule_due()` is stateless — it only tells the scheduler "is it time?" — the condition evaluation is the caller's responsibility. This matches HubSpot's separation of timing from predicate evaluation.

**Rejected from HubSpot:**
- **Multi-step workflows with branching.** HubSpot Workflows supports branching logic, loops, and multi-action sequences. CloseLoop's slice 1 is single-action: one rule → one trigger → one action. Multi-step orchestration is not in scope.
- **Enrollment history per contact/deal.** HubSpot tracks which contacts are enrolled in which workflow, with timestamps. This requires a separate `rule_enrollments` junction table. Deferred — CloseLoop's first slice tracks only `last_fired_at` at the rule level.

---

### 2.3 Pipedrive Automation

**Automation model:** Pipedrive's automation product (launched 2022) supports two trigger categories: deal/person/activity events (after-save equivalents: "Deal Added", "Deal Stage Changed") and time-based triggers ("Date reaches" / "Time passes"). These are distinct automation records, not a single polymorphic type.

**Key patterns borrowed:**
- **`conditions_json` + `action_config_json` as the payload columns.** Pipedrive stores conditions and actions as JSON blobs on the automation record. CloseLoop adopts the same shape: `conditions_json` (list of condition dicts) + `action_config_json` (action descriptor). This keeps the DB schema stable while the condition grammar and action types evolve in application code.
- **Entity-type scoping on the rule.** Pipedrive automations are scoped to a specific CRM object (Deal, Person, Organization). CloseLoop stores `entity_type` (`deal` / `contact`) on `AutomationRule` so the scheduler/trigger-wiring can query only rules relevant to the mutated entity.

**Rejected from Pipedrive:**
- **Separate trigger-type tables.** Pipedrive uses separate automation record types for event-triggered vs. time-triggered automations, with different UIs and storage layouts. CloseLoop uses a single `automation_rules` table with `trigger_type` — one rule concept, one schema, two execution paths.

---

### 2.4 Zoho CRM (Workflow Rules — Time-Based Actions)

**Automation model:** Zoho CRM's Workflow Rules support "Immediate Actions" (fire on save) and "Time-Based Actions" (fire N days/hours before or after a date field, or after the rule is triggered). A single Workflow Rule record carries a `trigger_when` discriminator and a list of attached "Action Groups" — one immediate group and zero or more time-based groups, each with an `offset` and `offset_unit`.

**Key patterns borrowed:**
- **`offset_days` as a signed integer.** Zoho allows negative offsets ("3 days before Closing Date") as well as positive ones ("7 days after Close Date"). CloseLoop's `ScheduleConfig.offset_days` is a signed integer for the same reason — negative means "before the anchor date." This is more flexible than two separate `days_before` / `days_after` fields.
- **`anchor_field` as a string field name.** Zoho stores the date field by its API name (e.g., `Closing_Date`). CloseLoop stores `anchor_field` as a plain string (e.g., `"expected_close_date"`) — the scheduler wiring resolves this to the entity attribute at fire time.

**Rejected from Zoho:**
- **Action Groups as child records.** Zoho normalises time-based action groups into separate child rows with FKs back to the workflow rule. CloseLoop serialises the schedule config as `schedule_config_json` on the rule row itself — simpler schema, one fewer join.
- **Offset units other than days.** Zoho supports hours, days, and weeks. CloseLoop's slice 1 uses days only (`interval_days`, `offset_days`). Hour-level granularity adds complexity without a clear use case in the current roadmap.

---

### 2.5 Attio (Sequences / Automation)

**Automation model:** Attio's automation product (2024) uses a "Sequence" concept: a record enters a sequence via a trigger (attribute change, record creation) and progresses through steps with optional delays. Delays are fixed-duration ("wait 3 days") rather than anchor-field relative.

**Key patterns borrowed:**
- **Single `trigger_type` discriminator on the rule record.** Attio stores one "sequence" record with a typed trigger config embedded as JSON. CloseLoop's `trigger_type` column + `schedule_config_json` column mirrors this approach.
- **`is_rule_due()` as a pure predicate.** The timing check (is it time to fire?) is cleanly separable from the execution (what to do). Attio's SDK exposes this as a separate `shouldFire(rule, now)` helper. CloseLoop adopts the same seam: `is_rule_due(cfg, reference_time, ...)` in `app/core/automations.py` is a pure function with no DB access, testable in isolation, and callable by the scheduler-wiring PR without coupling to the data layer.

**Rejected from Attio:**
- **Fixed-duration delays only.** Attio's "wait N days" is interval-mode only — there is no anchor-field relative scheduling. CloseLoop needs both modes (interval + field_offset) to cover the "7 days before close date" use case that is the most common automation request in Salesforce / HubSpot CRM contexts.

---

## 3. Patterns Summary: Borrowed vs. Rejected

| Pattern | Borrowed from | Used in CloseLoop |
|---------|--------------|-------------------|
| Single rule record, `trigger_type` discriminator (`after_save` \| `scheduled`) | Salesforce Flow, Attio | `automation_rules.trigger_type` TEXT column |
| `field_offset` scheduling: *N* days relative to a date field | Salesforce Scheduled Actions, HubSpot Delay Steps, Zoho Time-Based Actions | `ScheduleConfig(mode="field_offset", anchor_field=..., offset_days=...)` |
| `interval` scheduling: every *N* days since last fire | Attio | `ScheduleConfig(mode="interval", interval_days=...)` |
| `offset_days` as signed integer (negative = before anchor) | Zoho | `ScheduleConfig.offset_days` |
| `conditions_json` + `action_config_json` as JSON blobs | Pipedrive | Columns on `AutomationRule` |
| `entity_type` on the rule | Pipedrive | `AutomationRule.entity_type` |
| `is_active` flag (enable/disable without deletion) | HubSpot | `AutomationRule.is_active` |
| `last_fired_at` as interval fence | Salesforce | `AutomationRule.last_fired_at` |
| Pure `is_rule_due()` predicate separable from execution | Attio SDK pattern | `app/core/automations.py::is_rule_due()` |

| Pattern | Source | Rejected and why |
|---------|--------|-----------------|
| Separate tables per trigger type | Pipedrive | Single `automation_rules` table is simpler; trigger_type discriminates at query time |
| Async action queue | Salesforce | No background worker machinery; ADR-0010 prohibits outbound calls |
| Per-record enrollment tracking | HubSpot | Adds a junction table; deferred until multi-step orchestration is in scope |
| Multi-step workflow branching | HubSpot | Out of scope; CloseLoop slice 1 is single-action rules |
| Sub-day offset units (hours) | Zoho | No current use case; days are sufficient for the roadmap |
| Action Groups as child records | Zoho | Unnecessary normalisation; JSON blob is flexible and avoids joins |

---

## 4. Why Both Trigger Types in the Same Table

The temptation is to create a separate `scheduled_rules` table alongside `automation_rules`. This is rejected for the same reason Salesforce, Attio, and (in spirit) HubSpot put both trigger families on the same record:

1. **One rule concept for the user.** A rep thinks "I have a rule that sends a follow-up." Whether it fires on save or on a schedule is a detail of the *when*, not a different thing. A separate table doubles the CRUD surface for no gain.
2. **Shared condition/action schema.** Both trigger types evaluate the same condition grammar and execute the same action types. A single `conditions_json` + `action_config_json` shape serves both.
3. **Single activation surface.** `is_active` turns off a rule whether it's after-save or scheduled. One toggle, one table, one query.
4. **Simpler migrations.** Adding a new trigger type (e.g., `webhook`) is an `ALTER TABLE` to extend the allowed `trigger_type` values, not a new table.

The `schedule_config_json` column is NULL for `after_save` rules — this is the conventional sparse-column pattern used throughout CloseLoop (e.g., `Activity.recurrence_rule`, `Deal.closed_at`). No semantic ambiguity.

---

## 5. Schema Design

```
automation_rules
  id                  INTEGER PK
  name                TEXT NOT NULL
  entity_type         TEXT NOT NULL          -- "deal" / "contact"
  trigger_type        TEXT NOT NULL          -- "after_save" | "scheduled"
  is_active           INTEGER NOT NULL       -- 1=active, 0=inactive (DEFAULT 1)
  conditions_json     TEXT NOT NULL          -- JSON list of condition dicts (DEFAULT '[]')
  action_config_json  TEXT NOT NULL          -- JSON dict describing the action (DEFAULT '{}')
  schedule_config_json TEXT                  -- NULL for after_save; serialised ScheduleConfig for scheduled
  last_fired_at       TEXT                   -- ISO-8601 UTC; NULL = never fired; interval-mode fence
  created_at          TEXT NOT NULL          -- ISO-8601 UTC (injected clock, ADR-0006)
  updated_at          TEXT NOT NULL          -- ISO-8601 UTC (injected clock, ADR-0006)
```

`schedule_config_json` encodes a `ScheduleConfig` dataclass:
```json
// interval mode
{"mode": "interval", "interval_days": 7, "anchor_field": null, "offset_days": null}

// field_offset mode
{"mode": "field_offset", "interval_days": null, "anchor_field": "expected_close_date", "offset_days": -3}
```

---

## 6. Slice Plan

### Slice 1 (this PR): Data model + schedule-config parsing + `is_rule_due()`

**Deliverables:**
- `app/core/automations.py` — pure types: `ScheduleConfig` dataclass, `VALID_TRIGGER_TYPES`, `schedule_config_to_json()`, `schedule_config_from_json()`, `is_rule_due()`
- `AutomationRule` ORM model in `app/models.py` (`automation_rules` table)
- `app/services/automations.py` — thin DB-write service: `create_automation_rule()`
- `.devclaw/research/workflow-automation.md` (this document)

**Explicitly out of scope:**
- After-save trigger wiring in router handlers
- Scheduler daemon / periodic scan function
- Router endpoints (`GET/POST/PATCH/DELETE /automations`)
- Tests (land in the follow-up PR per task spec)
- AGENTS.md / DOMAIN.md updates (land in the follow-up PR per task spec)

---

### Slice 2 (next): After-save trigger wiring + scheduler scan function

**Deliverables:**
- `check_scheduled_rules(db, clk)` scan function in `app/services/automations.py` — queries active scheduled rules, calls `is_rule_due()`, fires due rules, updates `last_fired_at`
- After-save trigger calls in `app/routers/deals.py` + `app/routers/contacts.py`
- Tests in `tests/test_core_automations.py` (pure `is_rule_due()`) + `tests/test_automations.py` (API integration)

---

### Slice 3 (later): Router endpoints + frontend automation builder UI

**Deliverables:**
- `app/routers/automations.py` — CRUD endpoints for automation rules
- Frontend automation builder component
- ADR for automation rule design (citing this research doc)
