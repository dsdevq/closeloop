---
id: "0008"
title: Lead score formula (v1)
status: superseded
date: 2026-02-15
owner: "@dsdevq"
tags: [lead-score, formula]
supersedes: null
superseded-by: "0011"
---

# ADR-0008 — Lead score formula (v1)

> **Superseded by [ADR-0011](0011-lead-score-v2-decay.md)** for new callers. v1 is preserved for backward compatibility and remains bit-identical when v2's `use_decay=False` is passed.

## Context

The PRD requires a "hot lead" signal — an automatic score to help prioritize outreach. Needs to reward engagement recency, deal progression, and contact completeness.

## Decision

`compute_lead_score` produces 0.0–100.0 from:

- Number of deals: **+10 each, cap 30**.
- Deal stage bonuses: **qualified +10, proposal +15, negotiation +20**.
- Recent activity in last 30 days: **+5 each, cap 20**.
- Has email: **+5**.
- Has phone: **+5**.

## Consequences

- Max theoretical score = 30 + (∞ stage bonuses — uncapped) + 20 + 5 + 5 = floored at 100 by `min(score, 100)` cap.
- `GET /contacts/{id}/lead-score` recomputes and persists the score each call.
- Simple, deterministic, no configuration.

## Alternatives considered

Not documented at decision time.
