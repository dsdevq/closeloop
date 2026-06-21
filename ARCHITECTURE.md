# CloseLoop — Architecture

> Maintained by devclaw. This file describes the **real structure of the system as built** — keep it current as part of every task's definition of done. A future change should be able to read this and know where things live without re-reading all the code.

Describe, as they come into existence:

- **Module layout** — the package/file structure and what each module is responsible for.
- **The core logic module(s)** — where the pure, testable functions from PRD §5 live (state machine, forecast, lead score, overdue computation, filter AST, velocity). These stay free of DB/clock globals (time is injected).
- **Data layer** — how SQLite is accessed, schema/migrations, FK enforcement, the session/connection pattern.
- **Request & logging middleware** — structured JSON logging, request-id, `/health`, `event_log` writes, `/stats`.
- **Frontend** — how the vanilla JS talks to the API; page/asset layout.
- **Run & test** — the exact commands (kept in sync with the README + the verify gate).

_(To be filled starting M1. Empty until the skeleton exists.)_
