# E2E — Playwright

Layout of the Playwright suite. Setup (Playwright install, ARM64 quirks) is in [development.md](development.md).

## One spec per feature area

Each spec is self-contained with its own setup/teardown. Add new features here as a new `<feature>.spec.ts`.

| File | Coverage | Test count |
|------|----------|-----------:|
| `auth.spec.ts` | Basic SPA load, login/logout/guard, route coverage | 10 |
| `pipeline.spec.ts` | Pipeline nav, Deals CRUD, drag-and-drop, per-stage Add Deal | 12 |
| `contacts.spec.ts` | Contacts nav, CRUD, Import/Export, saved-view Apply/Clear | 19 |
| `accounts.spec.ts` | Accounts nav, Accounts CRUD | 6 |
| `activities.spec.ts` | Activities CRUD (+ nav after 2026-06-29) | 7 |
| `stats.spec.ts` | Stats nav | 1 |
| `today.spec.ts` | Today nav, reminder Dismiss | 2 |
| `tsconfig.json` | TypeScript config for e2e tests | — |
| `fixtures/contacts.csv` | Sample CSV for import testing | — |

**Total:** 52 passed / 0 failed / 5 fixme-skipped as of 2026-06-29.

## Fixme catalog

`test.fixme` items are skipped defect markers for known UI gaps.

| # | Status | Test | Note |
|---|--------|------|------|
| 1 | `test.fixme` | Contacts CRUD › contact detail/edit UI | In contacts.spec.ts; full CRUD covered by 'contacts - detail' |
| 2 | ✅ Fixed | Deals CRUD › create deal via modal — appears on kanban | `POST /deals` sets `stage_id` to first pipeline stage |
| 3 | `test.fixme` | Deals CRUD › deal detail/edit UI | In pipeline.spec.ts; full CRUD covered by 'deals - detail' |
| 4 | ✅ Done | Accounts CRUD › edit account | AccountEditModal wired into AppModals + App shell (name, notes, address; diff-only PATCH) |
| 5 | `test.fixme` | Activities CRUD › Activities nav tab | ✅ Activities tab added to SPA; activities.spec.ts covers it |
| 6 | `test.fixme` | Import › import UI trigger | ✅ Import CSV button added; contacts.spec.ts covers it |
| 7 | `test.fixme` | Export › export UI trigger | ✅ Export CSV button added; contacts.spec.ts covers it |

## Port + credentials

- Port: `E2E_PORT=8088` (config value). Port 8000 may be occupied by a harness stub in some environments.
- Credentials: `TEST_USER=admin@closeloop.com` / `TEST_PASS=admin123` (defaults).

## Auto-start server

The `webServer` config in `playwright.config.ts` boots FastAPI automatically before the suite runs. Do NOT flip `stdout` / `stderr` to `'pipe'` — see [development.md#arm64-pipe-gotcha](development.md#arm64-pipe-gotcha---do-not-undo).
