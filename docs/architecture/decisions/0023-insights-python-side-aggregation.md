---
id: "0023"
title: Insights aggregation computed in pure Python, not SQL
status: accepted
date: 2026-07-01
owner: "@dsdevq"
tags: [insights, architecture, core, testing]
supersedes: null
superseded-by: null
---

# ADR-0023 — Insights aggregation computed in pure Python, not SQL

## Context

The Insights feature (PRs #28–#36) adds four analytics views: deal trends by stage over a rolling window, a conversion funnel with average time-in-stage, a rep leaderboard ranked by closed revenue and cycle time, and source cohorts grouping deals by the contact's acquisition channel. Each view requires non-trivial aggregation across `deals`, `contacts`, and `stage_transitions` rows.

Two implementation paths were viable:

1. **SQL push-down** — `GROUP BY`, window functions, and `JOIN`s executed by the database engine, returning pre-aggregated rows to the router.
2. **Python-side aggregation** — router fetches all rows into plain dicts; pure functions in `app/core/` perform the aggregation in Python.

The project's modular-core convention ([ADR-0001](0001-pure-core-module.md)) requires that verifiable business logic live as pure functions in `app/core/` with no I/O and no global state, tested independently of the database.

## Decision

All Insights aggregation logic lives in `app/core/insights.py` as pure Python functions (`trends`, `conversion_funnel`, `rep_leaderboard`, `source_cohorts`). Each function receives lists of plain dicts (not ORM objects, not query results) and returns a dict or list. The router (`app/routers/insights.py`) is responsible only for fetching rows via simple `.all()` queries — projecting ORM objects into plain dicts via `_deal_dicts`, `_contact_dicts`, and `_transition_dicts` — and passing those lists to the core functions.

No aggregation SQL (`GROUP BY`, window functions, subqueries) is used. SQLite executes only unfiltered selects; Python performs every count, average, sort, and rate computation.

## Consequences

- **Core functions are testable without a database fixture.** `test_core_insights.py` calls them directly with synthetic list inputs — no `client` fixture, no `db` session, no SQLAlchemy overhead.
- **The injectable clock ([ADR-0006](0006-injected-clock.md)) works cleanly.** `trends` accepts a `clock` kwarg; deterministic time-dependent tests are trivial to write.
- **SQLite portability ceiling is not a constraint.** The project's single-tenant deployment uses SQLite throughout; SQLite's analytical SQL support is limited. Aggregating in Python avoids building on features that differ across SQLite versions or would require migration if the DB engine changes.
- **Memory usage scales linearly with row count.** All deals and contacts are loaded into memory per request. For a single-tenant CRM at the expected data volume (hundreds to low thousands of deals), this is negligible. If the dataset grows to tens of thousands of rows, query-level filtering or SQL aggregation should be reconsidered.
- **Routers stay thin.** The router's only responsibility is mapping HTTP concerns (auth scoping, query validation, HTTP status) to core function calls — consistent with [ADR-0001](0001-pure-core-module.md).

## Alternatives considered

- **SQL push-down aggregation** — would shift computation to the DB engine and avoid loading all rows. Rejected because it breaks the pure-core convention: aggregation logic embedded in SQL strings is harder to unit-test, harder to read, and tied to the SQLite dialect. At current data volumes the Python overhead is immeasurable.
- **ORM-level aggregation (`func.count`, `func.avg`)** — similar tradeoff to raw SQL push-down; still I/O-coupled and not testable without a live session.
