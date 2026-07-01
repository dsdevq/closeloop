---
id: "0020"
title: Stage DELETE returns 409 when deals exist
status: accepted
date: 2026-05-06
owner: "@dsdevq"
tags: [v2, pipeline-stages, api]
supersedes: null
superseded-by: null
---

# ADR-0020 — Stage DELETE returns 409 (not 422) when deals reference the stage

## Context

Deleting a pipeline stage that still has deals would orphan those deals. The API must reject the operation with a clear status code. FastAPI convention uses 422 for semantic validation failures ([ADR-0002](0002-stage-state-machine.md)), but 422 isn't quite right here — the request itself is well-formed; the *state* of the system prevents it.

## Decision

`DELETE /pipeline/stages/{id}` returns **HTTP 409 Conflict** when deals reference that stage. The response body includes the count of blocking deals in the detail message.

## Consequences

- 409 is the correct HTTP semantics for "resource state conflict" — matches PostgreSQL FK constraint violation semantics.
- Clients can distinguish "your request is malformed" (422) from "the current state blocks this" (409) — different UX responses.

## Alternatives considered

- **422** — inconsistent with the "state conflict" meaning.
- **204 with silent unlink** — hides destructive behavior; bad UX.
