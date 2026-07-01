---
title: <one-line runbook title>
status: stable
owner: "@<github-handle>"
last_reviewed: YYYY-MM-DD
tags: [operations, runbook, <subsystem>]
runs-in: <lifekit-vps | local | ci>
estimated-duration: <e.g. 5 minutes>
---

# Runbook — <title>

## When to run this

The trigger. What symptom or scheduled task calls for this procedure? If it's on-call material, name the alert.

## Prerequisites

- Access needed (ssh, sudo, gh token, ...)
- Tools required (docker, tailscale, gh CLI, ...)
- Any state that must be true (e.g., "goal is in `blocked` phase")

## Steps

1. Numbered, imperative. Each step is a single action a tired operator at 3am can perform without thinking.
2. Include the exact command. Not "restart the service" — `sudo systemctl restart X`.
3. Include the expected output. Not "should succeed" — `Active: active (running)`.
4. Any step that can silently fail: add a verification sub-step.

```bash
# Real commands go here, in a runnable code block.
```

## Verification

How do you know it worked? What do you check? What logs, endpoints, or metrics confirm the state is recovered?

## Rollback

If step N fails partway through, how do you get back to a safe state? If a rollback is impossible (rare — flag it upfront), what does escalation look like?

## Follow-up

- Log the incident (link `operations/incidents/` if applicable).
- Bump this runbook's `last_reviewed` if you found anything stale.
- Consider whether the underlying issue deserves a fix, not just a runbook (root-cause fix > procedural handling).
