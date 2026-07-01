---
id: "0021"
title: Manager role can create/update/delete pipeline stages
status: accepted
date: 2026-05-06
owner: "@dsdevq"
tags: [v2, auth, roles]
supersedes: null
superseded-by: null
---

# ADR-0021 — Manager role can create/update/delete pipeline stages (same as admin)

## Context

Pipeline stage configuration was originally admin-only. Sales managers need to tune stages for their cycle without waiting on an admin. This is an operations concern, not just superadmin territory.

## Decision

The `manager` role has the same authority as `admin` for pipeline stage mutations:

- `POST /pipeline/stages`
- `PATCH /pipeline/stages/{id}`
- `DELETE /pipeline/stages/{id}`

`rep` role remains unable to mutate stages.

## Consequences

- Managers can iterate on stage configuration without an admin bottleneck.
- The `admin`-vs-`manager` distinction narrows to user management ([guides/auth.md](../../guides/auth.md)).

## Alternatives considered

- **Admin-only** — creates an operational bottleneck; managers are the intended stewards of the sales process.
- **A separate `pipeline_admin` role** — role proliferation for no benefit.
