---
title: Runbooks — index
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [runbooks, operations, meta]
---

# Runbooks

Step-by-step procedures. Each runbook is designed to be followed by a tired operator at 3am — every step is imperative, includes the exact command, and includes the expected output.

## Available

- [manual-redeploy.md](manual-redeploy.md) — rebuild + swap the closeloop singleton container on `lifekit-vps` from a fresh git pull

## Wanted (not yet written)

- `rotate-jwt-secret.md` — safely rotate `JWT_SECRET_KEY` without invalidating live sessions
- `restore-from-backup.md` — restore closeloop.db from the most recent backup
- `enable-github-actions.md` — recover from the `BuildFailed workflow_id` state closeloop's Actions is stuck in (2026-07-01)

## Template

Use [`../../_templates/runbook.md`](../../_templates/runbook.md). Don't hand-roll.
