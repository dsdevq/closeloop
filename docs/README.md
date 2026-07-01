---
title: docs — how this tree works
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [meta, process, contributing]
---

# docs — how this tree works

The knowledge base for CloseLoop. Organized to survive scale: clear categories, per-category indexes, per-page ownership, ADR-per-decision, template-driven consistency. Start at [INDEX.md](INDEX.md) if you're browsing; read this file if you're contributing.

## Categories

Structured around the [Diátaxis](https://diataxis.fr) quadrants, adapted for a product codebase:

| Category | What lives here | When to add a page |
|---|---|---|
| [architecture/](architecture/INDEX.md) | Concepts, layer maps, data model, request lifecycle, ADRs | When the design of the system changes or a durable trade-off is made |
| [product/](product/INDEX.md) | PRD, roadmap, domain brief — what the product IS and where it's going | When the product contract, roadmap, or domain thinking shifts |
| [guides/](guides/INDEX.md) | How to do a specific task: develop, test, deploy, work with auth/frontend | When a repeatable workflow needs pinning |
| [reference/](reference/INDEX.md) | Dry, exhaustive lookup: routes, env vars, error codes | When a value/interface deserves an authoritative catalog |
| [operations/](operations/INDEX.md) | Runbooks, incidents, monitoring — how we run the thing in production | When an operational procedure or an incident is worth preserving |
| [proposals/](proposals/INDEX.md) | RFCs — designs in flight, not yet accepted | When you want to propose a change big enough to argue about |

Root-level `AGENTS.md`, `README.md`, `CHANGELOG.md` are the entry-point files GitHub shows front-and-center — they stay at the repo root by convention.

## Frontmatter contract

Every doc page carries YAML frontmatter. Missing or stale frontmatter is a review-blocker.

```yaml
---
title: <short human-readable title>
status: stable | draft | superseded | deprecated
owner: @<github-handle>              # single accountable steward
last_reviewed: YYYY-MM-DD            # bump on any material edit
tags: [<domain>, <subsystem>, ...]   # freeform, help discovery
---
```

- **`status`**: `stable` (safe to trust) / `draft` (in-flight) / `superseded` (see linked replacement) / `deprecated` (kept for history, don't use).
- **`owner`**: one github handle. Multiple stewards means no steward — pick one accountable.
- **`last_reviewed`**: bump when you change anything material. A rot audit greps for dates older than N months.
- **`tags`**: freeform vocabulary. Use existing tags before inventing new ones.

## Templates

Use them. Don't hand-roll new ADR/RFC/runbook shapes.

- [`_templates/adr.md`](_templates/adr.md) — Architecture Decision Record template.
- [`_templates/rfc.md`](_templates/rfc.md) — Request For Comments template (for proposals/).
- [`_templates/runbook.md`](_templates/runbook.md) — Runbook template (for operations/runbooks/).
- [`_templates/incident.md`](_templates/incident.md) — Post-incident review template.

## ADR process (Architecture Decision Records)

Every durable design decision — the "why" that a future engineer will want to know — becomes a **numbered, dated, immutable ADR** under [`architecture/decisions/`](architecture/decisions/INDEX.md).

- **File naming:** `NNNN-kebab-case-title.md` (zero-padded 4 digits).
- **Immutability:** once accepted, an ADR is not edited except to change its `status`. To revise a decision, write a new ADR that supersedes the old one (set `superseded-by:` on the old, `supersedes:` on the new).
- **Cross-reference:** every non-trivial code choice cites the ADR that grounds it (`# see ADR-0006`).
- **Full process:** [`architecture/decisions/README.md`](architecture/decisions/README.md).

## RFC process (Request for Comments)

Big changes get an RFC BEFORE code lands. An RFC is a proposal-then-discussion doc; unlike an ADR (which records a decision), an RFC is the *debate*. Once accepted, an RFC's outcome typically becomes an ADR.

- **When to write one:** cross-cutting refactor, new subsystem, deprecation of a public interface, migration between two hard-to-reverse states.
- **Where:** [`proposals/`](proposals/INDEX.md).
- **Full process:** [`proposals/README.md`](proposals/README.md).

## Rot management — the agent maintains its own memory

Docs rot silently. Discipline alone doesn't prevent it — but a *linter* isn't the right shape either, because the primary contributor to this repo is the agent, not a human trying to remember. The discipline needs to live where the agent will read it every time it works.

### `.agent/skills/knowledge-tree.md` — the load-bearing mechanism

CloseLoop's docs tree is maintained by a **skill file** loaded by devclaw runners on every task (per the PR #135 per-repo skills mechanism). The skill teaches the agent two reflexes:

1. **When you edit code, grep `docs/` for what you touched.** If a doc references it, update the doc in the same PR. If your change didn't invalidate the doc, bump its `last_reviewed` anyway — you just verified it's still true.
2. **When you edit a doc, verify frontmatter is complete, every link resolves, and (if it's a `status: stable` page older than 90 days) re-read it end-to-end before bumping the date.**

That's the whole mechanism. No linter, no cron, no scheduled audit. The reflexes live in front of the contributor at edit time — which is when they matter.

### Why this beats a linter

- **Proactive, not reactive.** A linter catches mistakes after the fact. A skill prevents them by teaching the discipline during the edit.
- **Semantic, not shape-only.** A linter can only verify frontmatter exists and dates aren't old. The skill can reason: "you touched `app/core/security.py` — the auth guide is affected; did you update it?" Shape checks are trivial in comparison.
- **No infrastructure to maintain.** No Python script that drifts from the tree it's checking.
- **Aligned with the model.** Devclaw's premise is that the agent is a senior engineer. Senior engineers don't need a cron job to remind them their docs are stale — they read the doc when they touch the code.

### If a human contributes by hand

Read [`.agent/skills/knowledge-tree.md`](../.agent/skills/knowledge-tree.md) yourself. It's short. The reflexes are the same regardless of who's driving.

### CODEOWNERS — human review routing

`.github/CODEOWNERS` names per-path stewards. When code changes, the doc's owner is auto-added as a reviewer. This is orthogonal to the skill — CODEOWNERS is human-review routing; the skill is agent behavior. Both point at `@dsdevq` today, but the shape scales.

### Empty INDEX entries

A hook without a live page is a stale link in the tree. The skill instructs the agent to check every link it writes; the same reflex catches this. Categories with no live pages carry a stub `INDEX.md` explaining what belongs there (see `docs/proposals/INDEX.md` today) — not an empty file.

## Adding a page — the checklist

1. Pick the right category (this file's table).
2. Copy the matching template from `_templates/`.
3. Fill in the frontmatter — every required field.
4. Link the page from its category's `INDEX.md` with a ~120-char hook.
5. If the page supersedes another, set the frontmatter fields and add a `Superseded by [...]` note to the top of the old page.
6. If the page adds a durable rule, cross-link it from `AGENTS.md` under the load-bearing rules section.

## Cross-linking discipline

- Use plain markdown links, not Obsidian wikilinks — this tree is GitHub-viewable-first.
- Prefer relative paths (`../architecture/overview.md`), not absolute repo URLs.
- If two pages disagree, mark the older `status: superseded` and add a pointer; NEVER let contradictory statements co-exist as "stable".

## Anti-patterns (do NOT do these)

- **Don't put narrative content back into `AGENTS.md`.** It's the entry point, not a warehouse. Rules go there; explanations live in `docs/`.
- **Don't split a doc across three pages because it "feels tidy".** One topic = one page. Cross-link if related, don't fragment.
- **Don't invent new categories without discussion.** The six above cover 95% of what a product codebase needs. If you truly need a seventh, propose it as an RFC.
- **Don't write "TBD" pages.** Empty scaffolding rots into noise. Write it when you know what to say.
- **Don't leave superseded ADRs unlinked.** The chain (`supersedes` / `superseded-by`) is the audit trail.
