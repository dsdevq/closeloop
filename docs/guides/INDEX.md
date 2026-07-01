---
title: Guides — index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [guides, meta]
---

# Guides

Task-oriented how-tos. Each page walks you through a specific, repeatable workflow.

## Getting started

- [development.md](development.md) — install, run, test locally; ARM64 Playwright workaround; the verify gate

## Testing

- [testing.md](testing.md) — pytest fixture patterns, clock override, `StaticPool`, why we never mock the DB ([ADR-0005](../architecture/decisions/0005-static-pool-test-engine.md))
- [e2e.md](e2e.md) — Playwright suite layout, spec-per-feature, current fixme catalog

## Subsystems

- [auth.md](auth.md) — JWT strategy, three roles, seed credentials, `owner_id` migration
- [frontend.md](frontend.md) — React SPA structure: types/, lib/, components/ui/, features/, hooks/

## Operations for developers

- [deploy.md](deploy.md) — Dockerfile shape, singleton container, tailscale-served URL; production runbooks live in [operations/runbooks/](../operations/runbooks/INDEX.md)

## What lives here vs. elsewhere

- **Here:** how to do a specific task. Guides tell you what steps to take.
- **Not here:** reference values (→ [reference/](../reference/INDEX.md)) · design rationale (→ [architecture/](../architecture/INDEX.md)) · production procedures (→ [operations/](../operations/INDEX.md)).
