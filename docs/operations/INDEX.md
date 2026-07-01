---
title: Operations — index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [operations, meta]
---

# Operations

How we run CloseLoop in production. Everything on-call, deploy-day, and incident-response material.

- [runbooks/](runbooks/INDEX.md) — step-by-step procedures. When a symptom appears, find the runbook and follow it.
- [incidents/](incidents/INDEX.md) — post-incident reviews. Written after resolution, not during.

## Where things go

- **A procedure someone might follow at 3am** → [runbooks/](runbooks/INDEX.md), using [`_templates/runbook.md`](../_templates/runbook.md).
- **A specific failure that happened and how we fixed it** → [incidents/](incidents/INDEX.md), using [`_templates/incident.md`](../_templates/incident.md).
- **How to develop / test locally** → [guides/development.md](../guides/development.md). Guides are for engineers building the thing; operations is for engineers running the thing.
- **Monitoring dashboards + alerting** → not yet written. Belongs here as `monitoring.md`.
