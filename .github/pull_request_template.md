<!-- Fill in the summary + tick the checklist. The docs checks are enforced
     by scripts/docs_lint.py in CI — a PR with docs debt will be red until
     you address it in this same PR. -->

## Summary

<one paragraph — what changes, why>

## Test plan

<how you verified this — commands + expected output>

## Docs impact

Tick the boxes that apply. If you can't tick one, explain why below.

- [ ] I ran `python3 scripts/docs_lint.py` locally and it passed.
- [ ] I updated the affected `docs/` page(s) — bumped `last_reviewed`, or added new content.
- [ ] I added a new ADR under `docs/architecture/decisions/` if this PR encodes a durable design choice.
- [ ] I added a new runbook under `docs/operations/runbooks/` if this PR introduces a new operational procedure.
- [ ] I updated `docs/reference/env-vars.md` if this PR added or removed an env var.
- [ ] AGENTS.md's load-bearing rules still apply. If a rule is now wrong, I removed it in this PR.

If this PR only touches code that isn't referenced by any doc, say so:

> No docs impact — this change is [scope of change] and no docs reference the affected code.
