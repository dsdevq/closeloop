---
id: "0004"
title: HTML5 drag-and-drop for kanban (no library)
status: superseded
date: 2026-01-25
owner: "@dsdevq"
tags: [frontend, kanban, dependencies]
supersedes: null
superseded-by: null
---

# ADR-0004 — HTML5 drag-and-drop for kanban (no library)

## Context

The original PRD non-goal was "no build step / SPA framework / CDN assets" — the M2 kanban was implemented in vanilla HTML/CSS/JS. A ~50-line block using the browser's `draggable` / `ondragstart` / `ondragover` / `ondrop` API is sufficient for a 6-column board with no network dependency.

## Decision

The kanban board uses the browser's native `draggable` / `ondragstart` / `ondragover` / `ondrop` API with no external drag library.

## Consequences

- The drag UX is functional but not as polished as library solutions (no ghost preview repositioning). Acceptable for an internal tool at this milestone.

## Follow-up

**Note (2026-07-01):** the "no SPA framework" non-goal was reversed when we migrated to React + Vite + Tailwind ([guides/frontend.md](../../guides/frontend.md)). The kanban's drag-and-drop is now inside React components but still uses the native HTML5 DnD API — the *decision to avoid a drag library* still holds. Consider a follow-up ADR if we introduce one.

## Alternatives considered

Not documented at decision time.
