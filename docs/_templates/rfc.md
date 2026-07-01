---
title: <one-line proposal title>
status: draft                         # draft | under-review | accepted | rejected | withdrawn
author: "@<github-handle>"
date: YYYY-MM-DD                      # date the RFC opened for discussion
tags: [<domain>, <subsystem>]
resolved-as-adr: null                 # if accepted, the ADR that codifies the outcome
---

# RFC — <title>

## Summary

What is being proposed, in one paragraph. Reader must understand the whole shape from this section alone.

## Motivation

Why is this worth changing? What breaks or hurts today? What does success look like? Quantify where you can.

## Detailed design

The actual proposal. Concrete: file paths, function signatures, HTTP endpoints, schema migrations. If the design has phases, list them.

## Alternatives considered

- **Alternative A** — trade-offs vs. this proposal.
- **Alternative B** — trade-offs vs. this proposal.
- **Do nothing** — what happens if we ship no change? (Always include this option.)

## Rollout / migration

How does this get from proposed to done? What backfill, feature flags, migration steps, or coordination is required? What's the fallback if it goes wrong?

## Risks + unknowns

What could go wrong? What don't we know that could invalidate the proposal? Where do we need feedback?

## Resolution

Filled in when the RFC closes. Options:

- **Accepted** — link the resulting ADR under `resolved-as-adr:`; note who accepted it and when.
- **Rejected** — say why; leave the file in place so the reasoning survives.
- **Withdrawn** — author changed their mind or superseded the RFC with another.
