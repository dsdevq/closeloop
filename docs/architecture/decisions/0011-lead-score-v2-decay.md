---
id: "0011"
title: Lead-score v2 — exponential decay
status: accepted
date: 2026-03-08
owner: "@dsdevq"
tags: [lead-score, formula, decay]
supersedes: "0008"
superseded-by: null
---

# ADR-0011 — Lead-score v2 uses exponential decay

Supersedes [ADR-0008](0008-lead-score-formula.md).

## Context

Lead-score v1 used a binary 30-day window: activities within 30 days counted, activities beyond didn't. Sharp cliff — an activity 31 days ago is worth zero, an activity 29 days ago is worth full points. Operators wanted a smoother gradient and configurable weights per sales cycle.

## Decision

`compute_lead_score_v2` uses exponential temporal decay:

```
score = base × 2 ^ (-days_ago / half_life)
```

Weights are configurable via a `weights` dict kwarg. Both functions coexist: v1 is preserved unchanged, v2 is opt-in.

- Default `half_life = activity_window_days / 2 = 15` days.
- `use_decay=False` — same as v1 (see below).

## Consequences

- **`compute_lead_score_v2(use_decay=False)` with default weights is bit-identical to v1.** Verified by `test_v2_use_decay_false_matches_v1`. Use this shape for regression comparison when investigating a score change.
- Callers wanting the smoother gradient pass `use_decay=True` (or omit — decay is on by default in v2).
- Operators tuning for their cycle set `weights={...}` at call time; no code change needed.

## Alternatives considered

- **Wider binary window (60d, 90d)** — same cliff problem, just further out.
- **Linear decay** — smoother than v1 but sharper than exponential; less natural fit for "engagement recency".
