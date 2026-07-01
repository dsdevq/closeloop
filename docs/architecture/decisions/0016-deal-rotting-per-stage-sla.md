---
id: "0016"
title: Deal-rotting — per-stage SLA thresholds from velocity core
status: accepted
date: 2026-04-02
owner: "@dsdevq"
tags: [deals, velocity, rotting]
supersedes: null
superseded-by: null
---

# ADR-0016 — Deal-rotting uses per-stage SLA thresholds derived from velocity core

## Context

The PRD [§5.6](../../product/prd.md) requires surfacing "deals rotting in stage" — open deals that have been in the same stage past a reasonable follow-up window. Different stages have different natural durations (a lead should move fast; a proposal can sit longer). Terminal stages don't rot by definition.

## Decision

`GET /deals/rotting` flags open deals whose `time_in_stage_hours > sla_days * 24`.

Default SLAs: **lead = 7d, qualified = 14d, proposal = 21d, negotiation = 30d.** Terminal stages (`won`, `lost`) never flagged.

Logic lives in `app/core/velocity.py` (`time_in_stage_hours`, `is_deal_rotting`, `stage_sla_days`) — pure, independently testable ([ADR-0001](0001-pure-core-module.md)).

## Consequences

- The endpoint uses an injected clock ([ADR-0006](0006-injected-clock.md)) — testable.
- A fresh deal always has `is_rotting=False` since 0h < any SLA.
- SLA constants are exported via `stage_sla_days()` to allow future override without touching the default.

## Alternatives considered

Not documented at decision time.
