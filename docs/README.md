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

## Adding a page — the checklist

1. Pick the right category (this file's table).
2. Copy the matching template from `_templates/`.
3. Fill in the frontmatter — DO NOT skip `owner` or `last_reviewed`.
4. Link the page from its category's `INDEX.md` with a ~120-char hook (not a summary — a hook that tells the reader what they'll find inside).
5. If the page supersedes another page, set the frontmatter fields and add a `Superseded by [...]` note to the top of the old page.
6. If the page adds a durable rule, cross-link it from `AGENTS.md` under the load-bearing rules section.

## Rot management — mechanized, not aspirational

Docs rot silently. Discipline alone doesn't prevent it. CloseLoop's docs tree is protected by a **linter that runs on every PR and a scheduled audit that runs weekly**.

### 1. `scripts/docs_lint.py` — the PR gate

Runs three checks against every markdown file under `docs/`:

- **Frontmatter contract** — every page must carry `title`, `status`, `owner`, `last_reviewed` (or `date` on immutable ADRs), and `tags`. Missing or malformed → **PR fails**.
- **Link integrity** — every internal markdown link resolves. Dead links (e.g., after a page moves) → **PR fails**.
- **ADR cross-refs** — every `ADR-NNNN` reference in code or docs points at a file that exists. Dangling refs → **PR fails**.

Plus one advisory:

- **Rot age** — every `status: stable` page whose `last_reviewed` is older than 90 days gets a **warning** on the PR. Doesn't fail the PR (that would block unrelated work) but it's visible.

The lint runs:
- Locally as step 0 of `bash scripts/verify.sh`.
- In CI as the `docs` job (`.github/workflows/ci.yml`), which the `test` job depends on — no green CI without green docs.

### 2. Weekly rot audit — `.github/workflows/docs-rot-audit.yml`

A separate scheduled workflow runs the linter with `--strict`, which promotes rot warnings to errors. Runs every Monday at 06:00 UTC. Failure = a red badge on `main` that someone must resolve: bump the date after re-reading, mark the page superseded, or delete it.

The two-layer split (PR-gate advisory + weekly strict audit) is deliberate — the PR gate stays fast and non-blocking on rot; the audit forces someone to look at the whole tree periodically.

### 3. CODEOWNERS — drift alerts

`.github/CODEOWNERS` names per-path stewards, so a PR that changes `app/core/` (where [ADR-0001](architecture/decisions/0001-pure-core-module.md) lives) auto-requests review from the ADR's owner. Frontmatter `owner:` is fine-grained; CODEOWNERS is coarse; both point at the same person for now, but this scales when the team does.

### 4. Pull request template — docs impact checkbox

`.github/pull_request_template.md` forces every PR author to tick "I updated the affected docs" or explicitly state "no docs impact". A silent "I forgot" becomes a visible "I decided".

### Ownership rotation

If the `owner` leaves the team or stops touching this code, the current maintainer picks it up on the next PR that touches it — the PR template's docs checkbox surfaces the ownership question naturally.

### Empty INDEX entries

A hook without a live page is a dead link → **PR fails** via the linter. Categories with zero live pages carry a stub `INDEX.md` explaining what belongs there (see `docs/proposals/INDEX.md` today).

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
