---
id: "0013"
title: Bulk import — JSON body {csv} not multipart
status: accepted
date: 2026-03-18
owner: "@dsdevq"
tags: [bulk-import, api]
supersedes: null
superseded-by: null
---

# ADR-0013 — Bulk import accepts JSON body `{csv: "..."}` not multipart

## Context

CSV import needs a request shape. Multipart file upload is the "obvious" web-form choice but requires `python-multipart` in requirements and diverges from the rest of the API (which is JSON everywhere). The use case is "paste a spreadsheet export" — a JSON string body is sufficient.

## Decision

`POST /contacts/import` and `POST /deals/import` accept a JSON body `{"csv": "<csv text>"}` rather than multipart file upload.

## Consequences

- The router implementation stays simple (standard Pydantic body parsing).
- The API stays JSON-only — no `python-multipart` dependency.
- CSV size is limited to what fits in a request body. For CloseLoop's use case (spreadsheet paste) this is fine.
- **Row-level validation errors are returned in the response body** (`errors` list), not as HTTP 4xx. This lets partial imports succeed: 8 of 10 rows land, 2 rows come back with errors.

## Alternatives considered

- **Multipart file upload** — requires `python-multipart`; asymmetric with the rest of the JSON API; better UX for very large files.
