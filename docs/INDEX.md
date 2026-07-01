# docs/ index

Knowledge tree for CloseLoop. Each entry is a hook (~120 chars) — follow the ones your task needs, don't read the whole tree upfront.

## Development

- [development.md](development.md) — install, run, test locally; ARM64 Playwright workaround; the verify gate
- [testing.md](testing.md) — pytest fixture patterns, clock override, `StaticPool`, why we never mock the DB
- [e2e.md](e2e.md) — Playwright suite layout, spec-per-feature convention, current status
- [deploy.md](deploy.md) — Dockerfile shape, singleton container per repo, CI + tailscale-served URL

## Product

- [../PRD.md](../PRD.md) — the product contract; the answer to "what should CloseLoop do"
- [DOMAIN.md](DOMAIN.md) — CRM domain best-practices brief + honest assessment of CloseLoop's roadmap
- [../BACKLOG.md](../BACKLOG.md) — what's next
- [../CHANGELOG.md](../CHANGELOG.md) — what shipped, when

## Architecture + Decisions

- [../ARCHITECTURE.md](../ARCHITECTURE.md) — layer map, data model, request lifecycle, test design
- [../DECISIONS.md](../DECISIONS.md) — 22 D-numbered decisions with rationale; the "why" for every non-obvious call

## Subsystem deep-dives

- [auth.md](auth.md) — JWT strategy, three roles, seed credentials, `owner_id` migration, test fixtures
- [frontend.md](frontend.md) — React SPA structure: types/, lib/, components/ui/, features/, hooks/, the AppModals pattern
