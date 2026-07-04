---
title: Domain Model Glossary
status: living
owner: "@dsdevq"
last_reviewed: 2026-07-04
tags: [domain, glossary, automations]
---

# CloseLoop — Domain Model Glossary

Terms that appear in code, ADRs, and design docs but are not fully defined by
the schema alone.  Add new concepts here; do NOT replace or reorder existing
entries.

---

## ScheduledTrigger

**What it is.** A `trigger_type` value on `AutomationRule` (the alternative to
`"after_save"`).  A scheduled rule is not fired by an entity mutation; instead
it is evaluated periodically by the background poller in `app/main.py` and fires
when its `schedule_config_json` says it is due.

**Why it exists.** Event-based (after_save) triggers cover mutations a user
performs.  Scheduled triggers cover time-based automation — e.g. "create a
follow-up task every 60 minutes" or "fire once on a specific date" — where
there is no entity save to hook into.

**Research lineage.** The Salesforce "Scheduled Paths" model (run this action N
days after a deal's close date) and the HubSpot "Delay until date" / "Delay for
X days" Workflow action were the primary references.  Both were initially
rejected in `.devclaw/research/workflow-automation.md §2.1–2.2` because
CloseLoop had no background worker.  The implementation here introduces the
minimal background worker (an asyncio task in the FastAPI lifespan) needed to
make time-based triggers viable without violating ADR-0010 (no outbound network
calls) or ADR-0001 (pure core module).  The full Salesforce "Scheduled Paths"
pattern (trigger N days after a *field* value) is deferred to a future slice
that would scan entities and build a context dict per row.

**How it works.**

```
trigger_type = "scheduled"
schedule_config_json = '{"interval_minutes": 60}'
                     | '{"run_once_at": "2026-07-10T09:00:00+00:00"}'
last_triggered_at = NULL (never) | ISO-8601 UTC string (last fire)
```

1. `is_due(schedule_config, last_triggered_at, reference_time) -> bool` — pure
   function in `app/services/automations.py`.  No I/O.
2. `_parse_schedule_config(config_json) -> dict` — fail-closed parser; raises
   `ScheduleConfigParseError` on missing, blank, or structurally invalid config.
   Same contract as `_parse_conditions` / `ConditionsParseError` (PR #53).
3. `run_scheduled_automations(db, *, clk) -> int` — polls all active scheduled
   rules, calls `is_due`, calls `_execute_action` for due rules (the same action
   dispatcher used by after_save rules — no second pipeline), updates
   `last_triggered_at`, and commits.  Called by the poller every 60 s.

**Fail-closed invariants.**

| Bad state | Behaviour |
|-----------|-----------|
| `schedule_config_json` is NULL or blank | `ScheduleConfigParseError` → rule skipped |
| `schedule_config_json` is invalid JSON | `ScheduleConfigParseError` → rule skipped |
| `schedule_config_json` has neither `interval_minutes` nor `run_once_at` | `ScheduleConfigParseError` → rule skipped |
| `interval_minutes` ≤ 0 or not an integer | `ScheduleConfigParseError` → rule skipped |
| `run_once_at` is not a valid ISO-8601 datetime | `ScheduleConfigParseError` → rule skipped |
| `run_once_at` rule with `last_triggered_at` set (already fired) | `is_due` returns False → rule skipped (expired) |

**Background poller registration.** `_scheduled_automations_loop()` in
`app/main.py` is started as an asyncio task in the FastAPI lifespan:
```python
poller_task = asyncio.create_task(_scheduled_automations_loop())
```
It is cancelled on shutdown.  The poller uses `SessionLocal` (the production
session factory) — it does NOT share sessions with HTTP request handlers.

**Testing with fast-forwarded time.** Tests never depend on wall-clock time.
Instead they pass a `FixedClock` instance to `run_scheduled_automations`:
```python
class FixedClock:
    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed
    def now(self) -> datetime:
        return self._fixed

fired = run_scheduled_automations(db_session, clk=FixedClock(some_time))
```
See `tests/test_automation_triggers.py` for the full test suite.
