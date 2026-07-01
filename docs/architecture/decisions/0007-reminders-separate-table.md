---
id: "0007"
title: Reminders as a separate table from activities
status: accepted
date: 2026-02-12
owner: "@dsdevq"
tags: [data-model, reminders, activities]
supersedes: null
superseded-by: null
---

# ADR-0007 — Reminders as a separate table from activities

## Context

The PRD data model uses `activities.due_at` as a simple marker for "this is a reminder". The M3 spec superseded this: multiple reminders per activity are needed, and a first-class Today queue endpoint (`GET /reminders/today`) needs its own filter surface.

## Decision

`reminders` is its own table with `FK → activities`, not a nullable column on `activities`. Schema:

```
reminders(id, activity_id → activities [ON DELETE CASCADE], remind_at, dismissed_at)
```

## Consequences

- `POST /reminders` requires an existing `activity_id`.
- The Today queue is computed on-request (no daemon), filtered by `remind_at <= now` AND `dismissed_at IS NULL`.
- Multiple reminders per activity are natural.
- The `activities.due_at` field is retained but is no longer the reminder trigger.

## Alternatives considered

- **Nullable `due_at` on activities as the reminder** — simpler schema, one reminder per activity max, no independent dismissal state.
