---
id: NNNN                              # zero-padded 4 digits — must match filename
title: <one-line human-readable title>
status: proposed                      # proposed | accepted | superseded | deprecated
date: YYYY-MM-DD                      # date the decision was accepted
owner: "@<github-handle>"             # accountable steward
tags: [<domain>, <subsystem>]
supersedes: null                      # e.g. "0003" if this replaces ADR-0003
superseded-by: null                   # filled in when a later ADR replaces this one
---

# ADR-NNNN — <title>

## Context

What forces are at play? What problem are we solving? Which constraints matter? Cite specific PRD sections, code paths, or prior ADRs when relevant. Keep this paragraph to what a reader must know to understand the decision — not the full history of the codebase.

## Decision

What are we deciding, in one paragraph? State it in the form the code will follow, not as a proposal. Concrete: function signatures, table names, HTTP status codes, invariants.

## Consequences

What becomes true, easier, or harder as a result of this decision? Include second-order effects: what tests must exist, what callers must adopt, what future decisions this makes easier or harder.

## Alternatives considered

- **<Alternative A>** — why not.
- **<Alternative B>** — why not.

If no alternatives were seriously weighed, write: "Not documented at decision time." Don't fabricate.
