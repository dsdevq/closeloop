---
title: docs — top-level index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [meta, navigation]
---

# CloseLoop docs

Navigate by category. Each category has its own `INDEX.md` — this file is the map to the map. If you're contributing, read [README.md](README.md) first.

## Architecture — how it's built

- [architecture/overview.md](architecture/overview.md) — layer map, data model, request lifecycle, test design
- [architecture/decisions/](architecture/decisions/INDEX.md) — 22 immutable ADRs recording every non-trivial design call
- [architecture/decisions/README.md](architecture/decisions/README.md) — the ADR process itself

## Product — what it does + where it's going

- [product/prd.md](product/prd.md) — the product contract, authored at kickoff, judged against
- [product/roadmap.md](product/roadmap.md) — milestone status, what's next
- [product/domain-brief.md](product/domain-brief.md) — CRM domain knowledge + honest v1–v6 roadmap thinking

## Guides — how to do specific things

- [guides/development.md](guides/development.md) — install, run, test, verify gate, ARM64 Playwright workaround
- [guides/testing.md](guides/testing.md) — pytest fixture patterns, clock override, `StaticPool`, why we don't mock the DB
- [guides/e2e.md](guides/e2e.md) — Playwright suite layout, spec-per-feature, fixme catalog
- [guides/auth.md](guides/auth.md) — JWT strategy, roles, seed credentials, migrations
- [guides/frontend.md](guides/frontend.md) — React SPA structure: types/, lib/, features/, hooks/
- [guides/deploy.md](guides/deploy.md) — Dockerfile shape, singleton container, tailscale-served URL

## Reference — dry, exhaustive lookup

- [reference/env-vars.md](reference/env-vars.md) — every environment variable the app reads

## Operations — how we run this in production

- [operations/runbooks/](operations/runbooks/INDEX.md) — step-by-step procedures for common operational tasks
- [operations/incidents/](operations/incidents/INDEX.md) — post-incident reviews (empty until we have one to write)

## Proposals — RFCs, in flight

- [proposals/](proposals/INDEX.md) — designs under discussion; not accepted, not law
- [proposals/README.md](proposals/README.md) — the RFC process

## Meta

- [README.md](README.md) — how this tree works: categories, frontmatter, templates, ADR/RFC process, rot management
- [_templates/](_templates/) — ADR, RFC, runbook, incident templates
