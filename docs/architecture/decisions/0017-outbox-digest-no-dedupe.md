---
id: "0017"
title: Outbox digest — single queued row per call, no dedup
status: accepted
date: 2026-04-08
owner: "@dsdevq"
tags: [outbox, digest]
supersedes: null
superseded-by: null
---

# ADR-0017 — Outbox digest is a single queued row per call; no deduplication

## Context

The PRD requires a "daily 'overdue + due-today' digest composed into the outbox table". Simplest possible implementation: every call inserts one queued row. Deduplication (only-one-digest-per-day) would require storing the last-digested-at timestamp and adding complexity with no clear benefit for the single-user use case.

## Decision

`POST /outbox/digest` always inserts one new outbox row (regardless of whether a digest was already created today). It fetches undismissed, past-due reminders from the reminders table and composes a plain-text body.

## Consequences

- Calling the endpoint multiple times creates multiple queued rows — **idempotency is the caller's responsibility.**
- The outbox row uses a fixed `to_address` of `digest@closeloop.local` — a sentinel that makes it easy to identify digest rows vs manual outbox entries.
- Adding dedup later is additive (query the outbox for today's digest before inserting).

## Alternatives considered

- **Dedup by last-digested-at column on user** — extra state; no clear benefit for MVP.
