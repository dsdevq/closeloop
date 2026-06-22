# CloseLoop — Decision Log

## D1 — Pure core module (`app/core/`)

**Decision:** All verifiable business logic (stage machine, forecast, lead score, etc.) lives in `app/core/` as pure functions with no I/O and no global state.

**Why:** PRD §5 requires the core to be pinned by a pytest suite with ≥90% coverage. Pure functions have no hidden dependencies and are trivially testable in isolation.

**Consequences:** Routers are thin: they translate HTTP → call core function → persist → return JSON.

---

## D2 — Stage state machine design

**Decision:** `validate_transition(from_stage, to_stage) -> bool` returns `True`/`False` for valid/invalid transitions; raises `ValueError` on unknown stage strings. Terminal stages (`won`, `lost`) block all outgoing transitions. Any open stage can move to `won` or `lost` or any other open stage (forward or backward).

**Why:** The PRD requires `won`/`lost` to be terminal with no resurrection. Raising on unknown strings gives clear errors instead of silent `False` for typos. Backward moves among open stages are permitted per M2 spec to allow data-entry correction.

**Consequences:** The PATCH `/deals/{id}/stage` endpoint returns HTTP 422 with `{"detail": "invalid stage transition: X → Y"}` on rejected transitions. A 422 (rather than 400) aligns with FastAPI's convention for semantic validation failures.

---

## D3 — `stage_probability` auto-set on transition

**Decision:** When a deal moves to a new stage via the stage endpoint, `deal.probability` is always overwritten by `stage_probability(new_stage)`. Manual probability overrides are not supported in M2.

**Why:** Keeps the weighted forecast deterministic and auditable without per-deal calibration UI. PRD §5 allows probability overrides as a post-MVP feature (iteration item 2).

**Consequences:** `PATCH /deals/{id}` cannot change `stage` (that belongs to `/stage`). This enforces the audit trail — every stage change goes through `validate_transition` and writes a `stage_transitions` row.

---

## D4 — HTML5 drag-and-drop for kanban (no library)

**Decision:** The kanban board uses the browser's native `draggable` / `ondragstart` / `ondragover` / `ondrop` API with no external drag library.

**Why:** PRD non-goal: "No build step / SPA framework / CDN assets." A single `<script>` block with ~50 lines of drag logic is sufficient for the 6-column board and avoids any network dependency.

**Consequences:** The drag UX is functional but not as polished as library solutions (no ghost preview repositioning). Acceptable for an internal tool at this milestone.

---

## D5 — `StaticPool` in test engine

**Decision:** The `conftest.py` test engine uses `sqlalchemy.pool.StaticPool` so that `Base.metadata.create_all` and subsequent sessions all share the same SQLite in-memory connection.

**Why:** Each new connection to `sqlite:///:memory:` creates a separate empty database. Without `StaticPool`, `create_all` writes the schema to one connection and the session queries hit a different (empty) database, causing "no such table" errors.

**Consequences:** All tests in a function-scoped `client` fixture see the same in-memory DB, which is correct. The pool is disposed after each test.

---

## D6 — Injected clock pattern for time-dependent logic

**Decision:** All time-dependent core functions accept a `clock` keyword argument (default: `datetime.utcnow`) rather than calling `datetime.utcnow()` directly. Router handlers pass `clk.now` (a bound method of the injected `Clock` dependency) as the callable.

**Why:** PRD §8 requires "all time-dependent logic accepts an injected `now`; no test depends on wall-clock." This makes the Today queue and lead-score recency window fully deterministic in tests.

**Consequences:** Tests that need a fixed "now" override `get_clock` on `app.dependency_overrides` before making requests (cleaned up in `finally:`). Core unit tests pass a lambda directly. Clock-aware core functions strip timezone info from stored timestamps for comparison (stored strings may include `+00:00` from `Clock.now().isoformat()`).

---

## D7 — Reminders as a separate table from activities

**Decision:** `reminders` is its own table (FK → activities) rather than treating `activities.due_at` as the reminder trigger.

**Why:** The M3 spec explicitly calls for a `reminders` table, enabling multiple reminders per activity and a first-class Today queue endpoint (`GET /reminders/today`). The PRD data model uses `due_at` on activities as a simpler marker, but M3 spec supersedes this for the reminders feature.

**Consequences:** `POST /reminders` requires an existing `activity_id`. The Today queue is computed on-request (no daemon), filtered by `remind_at <= now` and `dismissed_at IS NULL`.

---

## D9 — Filter AST grammar design

**Decision:** The filter expression is a recursive dict with an `op` key. Leaf nodes (`eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `contains`, `starts_with`) have `field` and `value` keys. Composite nodes (`and`, `or`) have a `children` list; `not` has a `child` key. The AST is serialised as JSON in `saved_views.filter_expr`.

**Why:** A dict-native grammar requires no custom parser and is trivially serialisable to/from JSON. The small fixed op-set covers all CRM query needs (equality, range, substring) without a full query language. Pure `parse_filter` + `evaluate_filter` functions live in `app/core/filter_ast.py` and are tested independently of any DB.

**Consequences:** Saved views store the raw JSON; `POST /saved-views/{id}/apply` deserialises and evaluates in Python against rows fetched from SQLite. This is suitable for small datasets (tens–hundreds of records); a future SQL-push-down optimisation could be added if needed.

---

## D10 — Outbox is a queue-only stub boundary

**Decision:** `POST /outbox` inserts a row with `status='queued'` and returns immediately. No real email or network call is ever made. The `sent_at` column and `status` transitions (`queued→sent/failed`) are available for a future delivery worker, but none exists in MVP.

**Why:** PRD §7 explicitly states "No real email/SMS send. The comms boundary is the `outbox` table; 'send' = insert a queued row." PRD §8 requires a test asserting no outbound network connections. Keeping the outbox as a queue stub enforces this contract without any SMTP configuration.

**Consequences:** A test (`test_outbox_makes_no_network_call`) monkeypatches `socket.create_connection` to assert no socket is opened during a queue operation. The `outbox` table has FKs to `deals` and `contacts` (both ON DELETE SET NULL) so outbox rows survive entity deletion.

---

## D8 — Lead score formula

**Decision:** `compute_lead_score` produces 0.0–100.0 from: number of deals (+10 each, cap 30), deal stage bonuses (qualified+10, proposal+15, negotiation+20), recent activity in last 30 days (+5 each, cap 20), has email (+5), has phone (+5).

**Why:** Simple, deterministic formula that rewards engagement recency, deal progression, and contact completeness. Caps prevent any single factor from dominating.

**Consequences:** Max theoretical score = 30 + (∞ stage bonuses — uncapped) + 20 + 5 + 5 = floored at 100 by the `min(score, 100)` cap. The `GET /contacts/{id}/lead-score` endpoint recomputes and persists the score each call.
