---
id: "0014"
title: RRULE-lite — daily/weekly/monthly, eager validation
status: accepted
date: 2026-03-22
owner: "@dsdevq"
tags: [recurrence, activities]
supersedes: null
superseded-by: null
---

# ADR-0014 — RRULE-lite covers daily/weekly/monthly only; validates eagerly

## Context

Recurring activities are a standard CRM feature. Full RFC 5545 RRULE requires either a dependency (python-dateutil) or hundreds of lines of code. For CRM follow-up cadences, daily/weekly/monthly with an interval covers 95% of real-world needs.

## Decision

`expand_rrule` supports `freq ∈ {daily, weekly, monthly}` with an integer `interval`. No `UNTIL`, `BYDAY`, `BYMONTHDAY`, or other RRULE modifiers.

Validation (unknown freq, non-positive interval) **always runs eagerly** — even when `count=0`.

## Consequences

- `Activity.recurrence_rule` stores a JSON subset: `{"freq": "daily"|"weekly"|"monthly", "interval": N}`.
- Validation runs in both `POST /activities` and `POST /activities/{id}/expand` — invalid rules fail fast at creation time, not only at expand time.
- No `python-dateutil` dependency.

## Alternatives considered

- **Full RRULE via `dateutil`** — dependency; power we don't need for CRM follow-ups.
- **No recurrence** — every follow-up would need to be manually re-created; kills the "reduce forgotten follow-ups" value prop.
