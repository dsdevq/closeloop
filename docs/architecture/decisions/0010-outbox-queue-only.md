---
id: "0010"
title: Outbox is a queue-only stub boundary
status: accepted
date: 2026-02-25
owner: "@dsdevq"
tags: [outbox, network-boundary, product-invariant]
supersedes: null
superseded-by: null
---

# ADR-0010 — Outbox is a queue-only stub boundary

## Context

The PRD ([§7](../../product/prd.md)) explicitly states: "No real email/SMS send. The comms boundary is the `outbox` table; 'send' = insert a queued row." PRD [§8](../../product/prd.md) requires a test asserting no outbound network connections. Real SMTP would break the zero-outbound-network invariant AND require configuration the product hasn't decided on.

## Decision

`POST /outbox` inserts a row with `status='queued'` and returns immediately. No real email or network call is ever made. The `sent_at` column and `status` transitions (`queued → sent/failed`) are available for a future delivery worker, but none exists in MVP.

## Consequences

- `test_outbox_makes_no_network_call` monkeypatches `socket.create_connection` to assert no socket is opened during a queue operation. This is a **load-bearing invariant** — see [AGENTS.md](../../../AGENTS.md).
- The `outbox` table has FKs to `deals` and `contacts` (both `ON DELETE SET NULL`) so outbox rows survive entity deletion.
- Adding a real delivery worker later is additive: it reads `WHERE status='queued'` and updates the row on send. Existing code stays unchanged.

## Alternatives considered

- **Real SMTP send** — breaks the zero-network invariant; requires deployment-time secrets.
- **No outbox at all** — no audit trail of what was "sent"; hard to add later.
