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

### `frontend/src/hooks/useAppState.ts`

**The only custom hook.** Owns all `useState`, `useCallback`, `useEffect`, and async CRUD actions.

`App.tsx` calls this hook and then renders the layout tree — App.tsx stays a pure composition; the state lives in the hook. This shape came out of the June 2026 refactor that broke the 1800-LOC App.tsx monolith.

## v2 shape (Accounts + Pipeline Stages)

- Tabs: Pipeline, Contacts, Accounts, Activities, Today, Stats.
- Kanban loads stages dynamically from `GET /pipeline/stages`; drag-and-drop PATCHes `{ stage_id }` on the deal.
- Contact name is a clickable button → `ContactDetailView`. Same shape for accounts, deals, activities.
- CSV Import/Export buttons on ContactsView section header (Import: FileReader → JSON POST; Export: fetch → blob → `<a download>`).
- Login stores access/refresh tokens + current user in localStorage.
