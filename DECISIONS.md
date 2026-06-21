# CloseLoop — Decision Log

> Append-only. Maintained by devclaw. One entry per non-obvious architectural or product decision, so future work doesn't re-litigate settled choices. Newest at the bottom.

**Format:**

```
## YYYY-MM-DD — <short title>
- **Decision:** <what was chosen>
- **Why:** <the reasoning>
- **Alternatives considered:** <what was rejected and why>
```

---

## (kickoff) — Foundational constraints (from the PRD)
- **Decision:** Python + FastAPI + SQLite + vanilla JS, single self-contained app, no outbound network at runtime; the comms boundary is an `outbox` table, not a real sender.
- **Why:** Reproducible, auditable, fully testable offline; matches the build environment's hard constraints.
- **Alternatives considered:** A SPA framework / external services / real email — rejected (build step, network, non-self-contained). See PRD §7.

_(devclaw appends new entries below as it makes choices.)_
