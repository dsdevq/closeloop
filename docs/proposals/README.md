---
title: RFC process
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [rfc, process]
---

# RFC process

## When to write an RFC (Request for Comments)

- **Cross-cutting refactor** (touches multiple subsystems).
- **New subsystem** (new module folder, new service boundary).
- **Deprecation of a public interface** (route, env var, config format).
- **Migration between two hard-to-reverse states** (schema, storage, hosting).
- **A choice worth arguing about** — anything where two competent engineers might disagree.

Do NOT write an RFC for:

- Small refactors — just open the PR.
- Bug fixes — just open the PR.
- Something already covered by an existing ADR — just cite it in the PR.

## Lifecycle

1. **Draft** — author opens a file under `proposals/` using [`../_templates/rfc.md`](../_templates/rfc.md). Filename: `YYYY-MM-DD-short-slug.md`.
2. **Under review** — status flipped, discussion happens in the PR comments (or issue), not in the file body.
3. **Accepted** — outcome typically becomes a numbered ADR. Set `resolved-as-adr:` in the RFC frontmatter to the ADR number.
4. **Rejected** — write WHY in the "Resolution" section. Leave the file in place; the reasoning has archaeological value.
5. **Withdrawn** — author changed their mind or superseded by another RFC.

## Anti-patterns

- **Don't write an RFC after landing the code.** RFCs are for debate BEFORE. If the change already shipped, write an ADR describing what was decided.
- **Don't leave a "draft" RFC open indefinitely.** After 30 days of inactivity, transition to `under-review` (force a decision) or `withdrawn`.
- **Don't skip "Alternatives considered".** An RFC with no alternatives is a fait accompli, not a proposal.
