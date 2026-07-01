---
id: "0024"
title: Insights charts are hand-rolled SVG primitives, no charting library
status: accepted
date: 2026-07-01
owner: "@dsdevq"
tags: [insights, frontend, charts, dependencies]
supersedes: null
superseded-by: null
---

# ADR-0024 — Insights charts are hand-rolled SVG primitives, no charting library

## Context

The Insights dashboard (PR #30) requires two chart shapes: a line chart (deal trends over time) and a bar chart (conversion funnel stage percentages). These are read-only data displays with no interactive requirements — no tooltips, no zoom, no click events. The frontend already has zero runtime charting dependencies.

## Decision

`frontend/src/features/insights/charts/` contains two hand-written SVG components — `LineChart.tsx` and `BarChart.tsx` — with no third-party charting library (no Recharts, Chart.js, D3, Nivo, or Victory).

Both components share a deliberate set of constraints:

- **Common point type.** `{ label: string; value: number }` — callers are responsible for shaping data before passing it in.
- **Fixed 480px logical viewport.** Both use `viewBox="0 0 480 <height>"` with `width="100%"`, so they scale fluidly via CSS without JavaScript resize logic.
- **Identical padding constants** (`PAD = { top: 16, right: 8, bottom: 36, left: 48 }`), so axis positioning is consistent across chart types.
- **Five y-axis ticks** at 0/25/50/75/100% of the data maximum, rendered as horizontal grid lines with text labels via a `formatValue` callback prop.
- **Auto-thinning x-labels.** `LineChart` renders an x-label only every `Math.ceil(data.length / 8)` points (always including the last), preventing label collision on dense data.
- **Inline empty-state.** Both return a centered "No data" paragraph when `data.length === 0`, keeping callers free of null guards.
- **`BarChart` props:** `data`, optional `height` (default 180), `color` (default `#2563eb`), `formatValue`.
- **`LineChart` props:** same plus optional `filled` (boolean, default `true`) to toggle the translucent area fill under the line.
- **Accessibility:** both carry `role="img"` and `aria-label` on the `<svg>` element.

No tooltip, hover, animation, or interactive state is implemented.

## Consequences

- **Zero added bundle weight.** No charting library appears in `package.json`; the two files total ~190 lines of TSX and add nothing to the production bundle beyond what TypeScript compiles them to.
- **Fully typed.** Props are narrow and explicit; TypeScript catches shape mismatches at compile time rather than at runtime inside a library's internals.
- **No tooltip or animation support.** Adding either would require extending the primitives or reconsidering this decision. A library like Recharts would provide both out of the box.
- **Callers shape their own data.** The `{ label, value }` contract keeps the primitives reusable but pushes sorting, filtering, and unit conversion to the caller (e.g., `TrendsSection.tsx` and `ConversionFunnel.tsx` each define their own `*toPoints` adapters). This is intentional — chart primitives should not know about CRM domain concepts.
- **Extending to new chart types requires a new file.** There is no shared chart base class or composable axis primitive; each chart is self-contained. This is fine for two chart shapes; it becomes friction if many more types are added.

## Alternatives considered

- **Recharts** — most popular React charting library; would have added ~180 KB gzipped and a D3 transitive dependency. Rejected: the feature needs only two static chart shapes; the library's API surface would go 95% unused.
- **D3** — maximum flexibility but high complexity for static displays, and a large bundle. Rejected for the same reason.
- **Nivo / Victory** — similar bundle and dependency concerns. None of them reduce scope enough to justify the cost at two chart types.
