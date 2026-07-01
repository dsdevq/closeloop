---
title: Incident process
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [incidents, process]
---

# Incident process

## Severity

- **sev-1** — production outage: users cannot use CloseLoop; data at risk.
- **sev-2** — degraded but working: a feature is broken; workaround exists.
- **sev-3** — cosmetic or narrow-impact defect; no urgency.

## During an incident

1. **Restore service first.** Debugging happens in the post-mortem.
2. Log actions taken to a scratch buffer (Slack thread, terminal history). This becomes the timeline.
3. Communicate: notify affected users if applicable.

## After resolution — the write-up

Write it within **5 business days** of resolution while memory is fresh.

- File: `NNNN-YYYY-MM-DD-short-slug.md` under [`incidents/`](INDEX.md).
- Numbering: sequential.
- Template: [`../../_templates/incident.md`](../../_templates/incident.md).

## Blameless-review rules

- **Attack the situation, not the human.** "We didn't have monitoring on X" is useful; "@person forgot to add monitoring" is not.
- **Action items must have owners and dates.** An unowned action item is a note, not a fix.
- **Follow up on action items.** If they slip, that's a separate incident of process.
