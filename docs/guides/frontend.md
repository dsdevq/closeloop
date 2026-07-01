---
title: Frontend guide (React + Vite + Tailwind)
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [frontend, react, vite]
---

# Frontend

React + Vite + TypeScript + Tailwind. Source in `frontend/src/`, build output in `app/static/`.

## Source-of-truth rule

**`frontend/src` is the source of truth**, not the generated files under `app/static/`. Never edit `app/static/*.js` — those are build artifacts.

## Pre-PR checks

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

The build script also copies `app/static/index.html` → `app/static/login.html` so FastAPI serves the same auth-aware SPA at both routes.

## Do / Don't

- **DO** use typed React state and normal JSX escaping.
- **DO** import from `../../types` (types), `../../lib/*` (api / formatters), `../../components/ui/*` (primitives).
- **DON'T** use `dangerouslySetInnerHTML` for user-supplied data.
- **DON'T** define domain types inside components — they live in `frontend/src/types.ts`.
- **DON'T** call `fetch()` bare — always through `apiFetch` (401 handling, auth headers).

## Layout

### `frontend/src/types.ts`

**All shared TypeScript domain types** live here: `User`, `Contact`, `Deal`, `Account`, `Activity`, `SavedView`, `Reminder`, `PipelineStage`, `Tag`. Every feature module imports types from here.

### `frontend/src/lib/`

- `api.ts` — `apiFetch` (auth-aware fetch; 401 → clear tokens → `/login.html`), `getToken`, `storedUser`.
- `formatters.ts` — `money`, `numberText`. No React or DOM dependency; safe to call anywhere.

### `frontend/src/components/ui/`

Shared presentational primitives, one named export per file matching the filename:

- `TextField` — labelled text input
- `ModalShell` — modal overlay + card wrapper
- `ModalActions` — modal footer button row (Cancel / primary)
- `SectionHeader` — page section title bar with optional action button
- `SavedViewsBar` — saved-view chips + apply/clear controls

### `frontend/src/components/`

App-level (not primitives):

- `AppHeader.tsx` — sticky nav bar (tab switcher + user info + logout)
- `AppModals.tsx` — renders all modals; driven by state from `useAppState`

### `frontend/src/features/`

One subdirectory per product area; each file exports one named export matching the filename. Feature modules import only from `../../types`, `../../lib/*`, and `../../components/ui/*`.

| Feature | Files | Notes |
|---------|-------|-------|
| `pipeline/` | `PipelineView`, `DealCard`, `DealDetailView`, `DealModal`, `DealEditModal` | `PipelineView` owns `stagePalette` |
| `contacts/` | `ContactsView`, `ContactDetailView`, `ContactModal`, `ContactEditModal`, `ImportModal` | CSV import + export |
| `accounts/` | `AccountsView`, `AccountDetailView`, `AccountModal`, `AccountEditModal` | v2 add |
| `activities/` | `ActivitiesView`, `ActivityDetailView`, `ActivityFormModal` | `ActivityFormModal` owns `ACTIVITY_TYPES` const |
| `today/` | `TodayView` | reminders queue with dismiss |
| `stats/` | `StatsView` | aggregate metrics |
| `auth/` | `LoginView` | no hardcoded credential defaults |
| `insights/` | `InsightsView`, `TrendsSection`, `ConversionFunnel`, `RepLeaderboard`, `SourceCohorts`, `charts/BarChart`, `charts/LineChart` | four self-contained sections; Insights tab wired into AppHeader |

### Chart primitives (`features/insights/charts/`)

Hand-rolled SVG charts — no external charting library (product invariant). Each takes typed `data: Point[]` props plus optional `height`, `color`, and `formatValue`. Render via `viewBox` + `width="100%"` for fluid scaling.

- `BarChart` — vertical bars; expects `BarChartPoint[]` (`{label, value}`)
- `LineChart` — line with optional area fill; expects `LineChartPoint[]` (`{label, value}`); prop `filled?: boolean` (default `true`)

### `frontend/src/hooks/useAppState.ts`

**The only custom hook.** Owns all `useState`, `useCallback`, `useEffect`, and async CRUD actions.

`App.tsx` calls this hook and then renders the layout tree — App.tsx stays a pure composition; the state lives in the hook. This shape came out of the June 2026 refactor that broke the 1800-LOC App.tsx monolith.

## v2 shape (Accounts + Pipeline Stages)

- Tabs: Pipeline, Contacts, Accounts, Activities, Today, Stats, Insights.
- Kanban loads stages dynamically from `GET /pipeline/stages`; drag-and-drop PATCHes `{ stage_id }` on the deal.
- Contact name is a clickable button → `ContactDetailView`. Same shape for accounts, deals, activities.
- CSV Import/Export buttons on ContactsView section header (Import: FileReader → JSON POST; Export: fetch → blob → `<a download>`).
- Login stores access/refresh tokens + current user in localStorage.

## Insights dashboard

The Insights tab is a 2-column responsive grid (`lg:grid-cols-2`) of four self-contained section components, all rendered by `InsightsView`. It sits alongside the other tabs in the `AppHeader` tab bar; auth scoping is handled server-side.

### Sections and their API endpoints

| Section | Endpoint | Response type |
|---------|----------|---------------|
| `TrendsSection` | `GET /insights/trends?window_days={30\|90\|365}` | `InsightsTrends` (`Record<string, number>`) |
| `ConversionFunnel` | `GET /insights/funnel` | `InsightsFunnel` (`Record<string, InsightsFunnelStage>`) |
| `RepLeaderboard` | `GET /insights/leaderboard` | `InsightsLeaderboardRow[]` |
| `SourceCohorts` | `GET /insights/cohorts` | `InsightsCohorts` (`Record<string, InsightsCohortSource>`) |

All four Insights types live in `frontend/src/types.ts` under the `// Insights` comment block.

### API-fetch / loading / error pattern

All four sections share the same local-state shape — there is no shared hook:

```tsx
const [data, setData] = useState<T | null>(null);
const [loading, setLoading] = useState(true);
const [error, setError] = useState(false);

useEffect(() => {
  setLoading(true);
  setError(false);
  void apiFetch('/insights/…')
    .then((res) => {
      if (!res.ok) { setError(true); return undefined; }
      return res.json() as Promise<T>;
    })
    .then((d) => { if (d !== undefined) setData(d); })
    .finally(() => setLoading(false));
}, [deps]);
```

Three render branches in each section:
- **Loading** — `h-40` centered `text-slate-400` "Loading…"
- **Error** — `h-40` centered `text-slate-400` error message
- **Data** — `BarChart` or `LineChart` plus an optional detail table below

New sections added to the Insights dashboard must follow this same pattern.

### Window switcher (TrendsSection only)

`TrendsSection` offers a 30 / 90 / 365-day window. `WINDOWS = [30, 90, 365] as const` drives the `WindowDays` type and the button group. The active button gets `bg-blue-600 text-white`; inactive buttons get `text-slate-500 hover:bg-slate-100`. The selected value is appended as `?window_days=N` on each fetch; changing the window re-triggers `useEffect`.

### Stage and source ordering

`TrendsSection` and `ConversionFunnel` define a local `STAGE_ORDER = ['lead', 'qualified', 'proposal', 'negotiation', 'won', 'lost']` and sort the API response `Record` by it before mapping to chart points (unknown stages sort last, alphabetically among themselves). `SourceCohorts` uses the same pattern with `SOURCE_ORDER = ['referral', 'inbound', 'outbound', 'event', 'other']`.
