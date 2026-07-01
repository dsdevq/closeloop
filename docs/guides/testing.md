---
title: Testing guide
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [testing, pytest, fixtures]
---

# Testing

Conventions for the pytest suite. E2E specifics live in [e2e.md](e2e.md).

## The load-bearing rules

- **Never mock the database.** Always use the in-memory SQLite via the `client` fixture. Mocked DBs mask migration bugs and schema drift.
- **Never call `datetime.utcnow()` directly** in production code (except the default value of a `clock` kwarg). Tests depend on being able to override the clock; direct calls make code untestable. See [ADR-0006](../architecture/decisions/0006-injected-clock.md).
- **Never leave a `dependency_overrides` mutation in place across tests.** Wrap every override in `try / finally: del app.dependency_overrides[dep]`. Silent leakage between tests is the fastest way to produce a flaky suite.

## Fixture pattern (conftest.py)

- `client` — per-function `TestClient`, backed by a fresh `sqlite:///:memory:` engine using `sqlalchemy.pool.StaticPool` (required so `create_all` and session queries share the same in-memory database; see [ADR-0005](../architecture/decisions/0005-static-pool-test-engine.md)).
- The default `client` fixture seeds an admin user and passes `Authorization: Bearer <token>` as default headers. All pre-auth-layer tests kept working unchanged.
- For isolated auth-flow testing, `tests/test_auth.py` defines its own `fresh_setup` / `admin_setup` fixtures (no seed, no default token).

## Pure-core tests

Files matching `test_core_*.py` test pure functions in `app/core/`. They import and call — **no fixtures needed**. This is the pin the PRD's ≥90% coverage requirement targets. See [ADR-0001](../architecture/decisions/0001-pure-core-module.md).

## Clock override in API tests

Time-dependent code takes an injected clock. To pin the clock in an API test:

```python
def test_something_at_a_specific_time(client):
    fixed = datetime(2026, 6, 30, 12, 0, 0, tzinfo=timezone.utc)
    app.dependency_overrides[get_clock] = lambda: FixedClock(fixed)
    try:
        r = client.get("/some/route")
        assert r.status_code == 200
    finally:
        del app.dependency_overrides[get_clock]
```

For pure-core tests, pass a lambda directly: `compute_lead_score(contact, clock=lambda: fixed)`.

**Gotcha:** `compute_lead_score` (and other clock-aware core functions) call `clock()` internally. Callers must pass `clk.now` (the *bound method*), NOT `clk.now()` (a datetime value). Same shape in every router.

## Gotchas that repeatedly bite

- **StaticPool is required** for the in-memory test engine — without it, `create_all` writes the schema to one connection and queries hit a different (empty) database.
- **String timestamps compare lexicographically.** SQLite stores ISO-8601 UTC strings; comparisons only work as long as everything uses the same timezone format (`+00:00`). Verified in `GET /reminders/today`.
- **`compute_lead_score_v2(use_decay=False)` is bit-identical to v1.** Verified by `test_v2_use_decay_false_matches_v1`. Use this for regression comparison.
- **`test_forecast_empty_pipeline` has an intentional `pass` body** — the endpoint is exercised implicitly by other tests. An isolated empty-pipeline call would need a standalone client fixture.
