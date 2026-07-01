---
title: ADR process
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [architecture, adr, process]
---

# ADR process

Every durable design decision — the "why" that a future engineer needs to know to work in this code confidently — becomes an **Architecture Decision Record**: a numbered, dated, immutable page under this directory.

## When to write one

Write an ADR when:

- A choice is **hard to reverse** and affects code shape (schema design, module boundary, framework choice).
- A choice **prevents a plausible alternative** the next engineer might otherwise try (e.g., "why don't we use a background worker for X?").
- A choice **encodes a trade-off** rather than an obvious answer.
- A **PR-level discussion** produces a rationale worth preserving.

Don't write one for:

- Coding style ("we use `snake_case`") — put those in a linter config or [guides/](../../guides/INDEX.md).
- Trivial constants — put those in the code with an explanatory comment.
- Vendor version pins — those live in `requirements.txt` / `package.json`.

## Numbering + naming

- **Filename:** `NNNN-kebab-case-title.md`, zero-padded 4 digits, sequential across the whole repo.
- The number is assigned when the ADR is accepted. In-flight proposals (before acceptance) live under [`../../proposals/`](../../proposals/INDEX.md) as RFCs.

## Lifecycle

1. **Proposed** (`status: proposed`) — an idea that has been discussed but not committed. Rare; most work goes through RFC first.
2. **Accepted** (`status: accepted`) — the current answer. Referenced from code, cross-linked from AGENTS.md rules.
3. **Superseded** (`status: superseded`) — replaced by a later ADR. Update the frontmatter's `superseded-by:` field and add a superseded-by note at the top of the body.
4. **Deprecated** (`status: deprecated`) — the decision no longer applies because the code it governed was removed. Rare.

## Immutability rule

Once an ADR is `accepted`, the body is not edited except:

- Typos or broken links.
- The `status` field, when superseded/deprecated.
- Adding a "Superseded by ADR-NNNN" note at the very top of the body (link to the actual replacement file).

To revise a decision, write a NEW ADR that supersedes the old one. This creates an audit trail — the next engineer sees the history, not just the current state.

## Template

Copy [`../../_templates/adr.md`](../../_templates/adr.md). Do not hand-roll.

## Cross-referencing from code

When a code block encodes an ADR's decision, cite it in a comment:

```python
# see ADR-0006: injected clock — never call datetime.utcnow() directly here
def compute_lead_score(contact, *, clock=datetime.utcnow):
    ...
```

Grep-friendly. When the ADR gets superseded, `grep ADR-0006` finds every caller to update.
