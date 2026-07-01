# Skill — Maintain the docs/ knowledge tree

You are the primary contributor to CloseLoop. The `docs/` tree is your durable memory across sessions — it survives your context reset, it's what future sessions of you will read to get up to speed, and it's what a human reviewer skims to trust your change. Keeping it fresh is not overhead. It's the thing that makes each subsequent session productive.

The whole tree structure, categories, and process rules live in [`docs/README.md`](../../docs/README.md). This skill is the *behavioral* companion — what you actually do while working.

## The two reflexes

### Reflex 1 — when you edit code, ask: does a doc reference this?

Before you finish, grep `docs/` for the module, function, table, route, or env var name you touched.

```bash
grep -rn "<name>" docs/
```

- If a doc references it and your change makes the doc wrong: **update the doc in the same PR**. Do not defer.
- If a doc references it and your change did NOT invalidate the doc: bump the doc's `last_reviewed` to today anyway — you just verified it's still true. That's how the tree stays fresh without a cron job.
- If no doc references it and the change is worth remembering: write the doc (see reflex 2).

### Reflex 2 — when you write or edit a doc, verify three things

1. **The right category.** Match the taxonomy in [`docs/INDEX.md`](../../docs/INDEX.md). Do not invent a seventh category.
2. **The frontmatter contract.** Every page carries it. See below.
3. **Every link you wrote resolves.** Follow it. Broken internal links are the tree lying to the next reader.

## Frontmatter contract

Do not hand-roll frontmatter. Copy from `docs/_templates/` and fill in the values.

**Regular page** (guide, reference, runbook, incident, INDEX):

```yaml
---
title: <short human-readable>
status: stable | draft | superseded | deprecated
owner: "@dsdevq"
last_reviewed: YYYY-MM-DD   # today, when you write or materially edit
tags: [<domain>, <subsystem>]
---
```

**ADR** (immutable once accepted):

```yaml
---
id: "NNNN"                   # zero-padded 4 digits, matches filename
title: <one-line title>
status: proposed | accepted | superseded | deprecated
date: YYYY-MM-DD             # acceptance date, never edited afterwards
owner: "@dsdevq"
tags: [<domain>, <subsystem>]
supersedes: null             # or "0003" if this replaces ADR-0003
superseded-by: null          # filled in later, when a new ADR replaces this
---
```

Owner is a single `@github-handle`. Multiple owners means no owner.

## When to write an ADR

Write one when the PR encodes a design choice that:

- Is **hard to reverse**.
- Prevents a plausible alternative the next engineer might otherwise try.
- Carries a real trade-off, not an obvious answer.

Do NOT write an ADR for coding style, dependency versions, or trivial choices. Full process in [`docs/architecture/decisions/README.md`](../../docs/architecture/decisions/README.md); template in [`docs/_templates/adr.md`](../../docs/_templates/adr.md).

### ADRs are immutable once accepted

To revise a decision, write a NEW ADR that supersedes the old one:

- Set `superseded-by: "NNNN"` on the old ADR's frontmatter + add a "Superseded by ADR-NNNN" note at the top of its body.
- Set `supersedes: "NNNN"` on the new ADR's frontmatter.

Do NOT rewrite the old ADR's body. The audit trail is the point.

### Cross-reference ADRs from code

When your code encodes an ADR's decision, cite it in a comment:

```python
# ADR-0006 — never call datetime.utcnow() directly here
def compute_lead_score(contact, *, clock=datetime.utcnow):
    ...
```

Grep-friendly. When the ADR gets superseded, `grep -rn "ADR-0006"` finds every caller to update.

## Rot check — the reflex, not a cron job

When you open a doc to edit it, look at `last_reviewed` in the frontmatter. If it's older than **90 days** and `status: stable`:

1. Read the doc end-to-end.
2. Decide:
   - **Still accurate** → bump `last_reviewed` to today. That is the whole mechanism.
   - **Partially wrong** → fix, then bump `last_reviewed`.
   - **Obsolete** → mark `status: superseded` or `deprecated`, point at what replaces it.

There is no linter, no cron, no scheduled audit. This reflex — check the date, re-read, decide — is the mechanism. If you skip it, the tree rots.

## Where new content goes

- Design choice with rationale → new ADR under [`docs/architecture/decisions/`](../../docs/architecture/decisions/INDEX.md)
- Design in flight → RFC under [`docs/proposals/`](../../docs/proposals/INDEX.md)
- Operational procedure → runbook under [`docs/operations/runbooks/`](../../docs/operations/runbooks/INDEX.md), copy [`docs/_templates/runbook.md`](../../docs/_templates/runbook.md)
- Post-incident review → [`docs/operations/incidents/`](../../docs/operations/incidents/INDEX.md), copy [`docs/_templates/incident.md`](../../docs/_templates/incident.md)
- New env var, endpoint, config knob → the matching page under [`docs/reference/`](../../docs/reference/INDEX.md)
- Task-oriented how-to → [`docs/guides/`](../../docs/guides/INDEX.md)

Do NOT back-fill [`AGENTS.md`](../../AGENTS.md). It stays lean; the tree grows.

## Anti-patterns

- **Do not write "TBD" pages.** Empty scaffolding rots into noise. Write the page when you know what to say.
- **Do not split a doc across three pages because it "feels tidy".** One topic = one page.
- **Do not fabricate "Alternatives considered" in ADRs.** Write "Not documented at decision time" if you don't know — do not invent history.
- **Do not update a superseded ADR's body.** Write a new one that supersedes it.
- **Do not add narrative to `AGENTS.md`.** Rules and pointers live there; explanations live in `docs/`.
- **Do not use Obsidian wikilinks (`[[foo]]`).** This tree is GitHub-viewable-first — use plain markdown links with relative paths.
