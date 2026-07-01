---
title: Reference — index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [reference, meta]
---

# Reference

Dry, exhaustive lookup material. Reference is authoritative — if a reference page and a guide disagree, the reference page is right.

- [env-vars.md](env-vars.md) — every environment variable the app reads, with default and effect

## Placeholder — add as needed

The following reference pages are worth writing when the corresponding surface grows:

- `routes.md` — a catalog of every HTTP route with its request/response shape (auto-generated from FastAPI's OpenAPI would be ideal)
- `error-codes.md` — every non-obvious HTTP status the API returns and when
- `configuration.md` — non-env-var runtime config (e.g., `pipeline_stages` seeded defaults)

## What lives here vs. elsewhere

- **Here:** exhaustive, factual lookup material a reader consults, not reads through.
- **Not here:** narrative (→ [guides/](../guides/INDEX.md)) · design (→ [architecture/](../architecture/INDEX.md)).
