---
id: "0012"
title: Forecast scenarios use fixed built-in probability maps
status: accepted
date: 2026-03-12
owner: "@dsdevq"
tags: [forecast, scenarios]
supersedes: null
superseded-by: null
---

# ADR-0012 — Forecast scenarios use fixed built-in probability maps

## Context

Scenario planning ("best case / expected / worst case") is a standard sales-forecast feature. Building UI configuration for scenario maps adds complexity; testing custom scenarios requires state. A middle path: ship named scenarios with fixed probabilities plus an ad-hoc override for experimentation.

## Decision

`forecast_scenarios` ships three named maps (`best`, `expected`, `worst`) with fixed per-stage probabilities. `POST /forecast/scenarios` additionally accepts an optional `probability_overrides` dict for a "custom" scenario.

## Consequences

- The built-in maps are internal constants (`_SCENARIO_BEST` etc.) exported from `app/core/forecast.py` for direct use in tests.
- Backtesting is pinnable — tests assert exact values against the internal constants.
- If users want to change the built-ins they pass a custom map; the constants aren't editable at runtime.

## Alternatives considered

- **Scenario configuration in a table** — requires migration + UI + tests; overkill for MVP.
- **Only accept custom maps, no defaults** — no zero-config path; every caller has to define their own.
