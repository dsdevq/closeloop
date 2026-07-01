---
title: <one-line incident title, e.g. "e2e suite 100% flakiness on ARM64">
status: post-mortem                   # active | mitigated | post-mortem
severity: sev-1 | sev-2 | sev-3       # sev-1 = production outage; sev-3 = degraded but working
started_at: YYYY-MM-DDTHH:MM:SSZ
resolved_at: YYYY-MM-DDTHH:MM:SSZ
owner: "@<github-handle>"             # who leads the write-up
tags: [<subsystem>, incident]
---

# Incident — <title>

## Summary (30 seconds)

What broke, when, for how long, for whom, and how it got fixed. One paragraph. This is the version someone should be able to skim without reading the rest.

## Timeline

Use UTC. One line per event, most-recent-first is fine.

- `YYYY-MM-DDTHH:MM:SSZ` — event.
- `YYYY-MM-DDTHH:MM:SSZ` — event.

## Impact

- Users affected: ...
- Data lost: ... (or "none")
- Services degraded: ...
- Blast radius: ...

## Root cause

The actual technical cause. Not "database was slow" — "the accounts.get_owner query missed the (owner_id, deleted_at) composite index, forcing a full scan at 40k rows". Go one step deeper than feels comfortable.

## Contributing factors

Things that made the incident worse or slower to detect: missing alerts, unclear ownership, misleading dashboard, out-of-date runbook, insufficient logging.

## What went well

Not a formality — genuinely name the things that helped: fast detection, clear handoff, good rollback path. Reinforces the practices worth keeping.

## Action items

Numbered, each with an owner and a due date. These are the durable output of the incident — the write-up itself is history, the action items are the fix.

1. [ ] `<action>` — owner: @X, due: YYYY-MM-DD.
2. [ ] `<action>` — owner: @Y, due: YYYY-MM-DD.

## Lessons

What generalizes beyond this specific incident? Which runbook, ADR, or reference doc gets updated as a result?
