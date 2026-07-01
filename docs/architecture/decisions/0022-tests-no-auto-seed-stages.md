---
id: "0022"
title: Tests do not auto-seed pipeline stages
status: accepted
date: 2026-05-06
owner: "@dsdevq"
tags: [v2, testing, fixtures]
supersedes: null
superseded-by: null
---

# ADR-0022 — In tests, pipeline stages are NOT auto-seeded

## Context

Production startup runs `_seed_pipeline_stages()` inside the lifespan, which seeds 6 default stages if the table is empty. Tests use the `client` fixture with an in-memory DB ([ADR-0005](0005-static-pool-test-engine.md)) and **do not run the lifespan** — they'd otherwise seed state that some tests want empty and other tests want customized.

## Decision

The test `client` fixture does NOT call the FastAPI lifespan and therefore does NOT seed pipeline stages. Tests that need stages must create them via `POST /pipeline/stages` or insert `PipelineStage` rows directly.

## Consequences

- Tests are explicit about the stage state they depend on — no hidden fixture-state that varies with `TestClient` internals.
- Adding a new test with pipeline dependency requires one extra setup step (seed the stages you need). Fine; explicit is better than implicit.
- Production behavior is unchanged — the lifespan still seeds defaults on real startup.

## Alternatives considered

- **Run the lifespan in tests** — seeds unwanted state; fights the isolation the in-memory-per-test design gives us.
- **Auto-seed inside the test fixture** — same problem in a different place.
