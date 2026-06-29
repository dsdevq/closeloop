# Frontend structure — state of the repo

`frontend/src/` currently contains exactly three files: `App.tsx`, `main.tsx`, `styles.css`. No `pages/`, no `components/`, no `features/`, no `hooks/`, no `lib/`.

`App.tsx` is **1827 lines** and contains 25+ component functions inline:

- Views: `LoginView`, `PipelineView`, `DealCard`, `DealDetailView`, `ContactsView`, `ContactDetailView`, `AccountsView`, `ActivitiesView`, `ActivityDetailView`, `TodayView`, `StatsView`
- Modals: `ModalShell`, `DealModal`, `DealEditModal`, `ContactModal`, `ContactEditModal`, `AccountModal`, `ActivityModal`, `ImportModal`
- Misc: `SectionHeader`, `SavedViewsBar`, `TextField`, `ModalActions`

This grew organically from PR #11's 1:1 port of a 1357-line static HTML file to a single React component. It is a known monolith.

Similarly, the e2e suite is a single 856-line `e2e/full-coverage.spec.ts` and a 639-line `e2e/smoke.spec.ts` — test files mirror the application file because there's nowhere else for them to go.

A senior engineer touching this codebase would observe this and act accordingly.
