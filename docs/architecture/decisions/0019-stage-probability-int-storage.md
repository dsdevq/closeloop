---
id: "0019"
title: Pipeline stage probability stored as 0-100 int
status: accepted
date: 2026-05-06
owner: "@dsdevq"
tags: [v2, pipeline-stages, probability]
supersedes: null
superseded-by: null
---

# ADR-0019 — Pipeline stage `probability` stored as 0–100 integer

## Context

v2 added user-editable pipeline stages, each with a probability. Existing forecast code reads `deal.probability` as a **0.0–1.0 float**. Storing stage probability as a float creates rounding and display quirks (0.999999 vs 1.0); storing as int is human-friendly (say "80%", not "0.8").

## Decision

`PipelineStage.probability` is stored as a **0–100 integer**. Converted to `0.0–1.0` float before writing to `deal.probability` so existing probability-based code is unaffected.

## Consequences

- Stage-editing UI shows and accepts integer percentages — natural for users.
- Existing forecast + probability-based code is unchanged.
- The int → float conversion happens at exactly one place (the PATCH handler that inherits stage probability onto the deal).

## Alternatives considered

- **Float storage 0.0–1.0** — matches `deal.probability` but user-hostile to edit.
