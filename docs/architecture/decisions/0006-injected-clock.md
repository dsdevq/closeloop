---
id: "0006"
title: Injected clock for time-dependent logic
status: accepted
date: 2026-02-05
owner: "@dsdevq"
tags: [testing, core, dependency-injection]
supersedes: null
superseded-by: null
---

# ADR-0006 — Injected clock pattern for time-dependent logic

## Context

The PRD ([§8](../../product/prd.md)) requires "all time-dependent logic accepts an injected `now`; no test depends on wall-clock". The Today queue, lead-score recency windows, reminders, and outbox digests all read the current time — testing them with `datetime.utcnow()` calls scattered through the code would be either flaky or require freezegun/time-machine.

## Decision

All time-dependent core functions accept a `clock` keyword argument (default: `datetime.utcnow`) rather than calling `datetime.utcnow()` directly. Router handlers pass `clk.now` (a bound method of the injected `Clock` dependency) as the callable.

```python
def compute_lead_score(contact, *, clock=datetime.utcnow):
    now = clock()
    ...

# Router:
def get_lead_score(contact_id: int, clk: Clock = Depends(get_clock)):
    return compute_lead_score(contact, clock=clk.now)  # bound method, NOT clk.now()
```

## Consequences

- Tests that need a fixed "now" override `get_clock` on `app.dependency_overrides` before making requests (cleaned up in `finally:` — see [guides/testing.md](../../guides/testing.md)).
- Pure core tests pass a lambda directly: `compute_lead_score(contact, clock=lambda: fixed_dt)`.
- **Callers must pass `clk.now` (the bound method), not `clk.now()` (a datetime value).** Common bug — the function calls `clock()` internally.
- Clock-aware core functions strip timezone info from stored timestamps for comparison; stored strings may include `+00:00` from `Clock.now().isoformat()`.

## Alternatives considered

- **freezegun / time-machine** — external dependency, monkey-patches datetime globally; harder to reason about in concurrent tests.
- **A module-level `now()` we can monkeypatch** — implicit; every test that needs it has to remember to patch.
