---
id: "0005"
title: StaticPool for in-memory SQLite test engine
status: accepted
date: 2026-01-28
owner: "@dsdevq"
tags: [testing, sqlite, fixtures]
supersedes: null
superseded-by: null
---

# ADR-0005 — `StaticPool` in test engine

## Context

Each new connection to `sqlite:///:memory:` creates a **separate empty database**. Without a pool that keeps a single connection alive, `Base.metadata.create_all` writes the schema to one connection and subsequent session queries hit a *different* connection with an empty schema — causing "no such table" errors.

## Decision

The `conftest.py` test engine uses `sqlalchemy.pool.StaticPool` so that `create_all` and all subsequent sessions share the same in-memory connection.

```python
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
```

## Consequences

- All tests in a function-scoped `client` fixture see the same in-memory DB, which is correct.
- The pool is disposed after each test, discarding the DB with it — no cross-test leakage.
- Tests that need multi-connection semantics (rare) must use an on-disk temp file, not `:memory:`.

## Alternatives considered

- **File-based `sqlite:///tmp/test.db`** — works but adds cleanup complexity and disk I/O; slower than in-memory + StaticPool.
- **Skip the pool workaround, use real Postgres in tests** — heavier setup; overkill for a suite that runs in seconds.
