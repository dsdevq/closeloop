# Reporting & Dashboards — Reference CRM Research & Design Synthesis

**Status:** Research complete — no product code shipped in this task.
**Date:** 2026-07-10
**Scope of this doc:** Reference CRM survey of reporting/dashboard models (Salesforce, HubSpot, Pipedrive, Attio, Zoho), analysis of CloseLoop's existing data model and aggregation architecture, and an explicit borrowed-vs-rejected synthesis recommending the reporting model CloseLoop should adopt — including the live-query vs. materialised-read-model question given the existing ORM/DB layer.

---

## 1. What We're Building and Why

CloseLoop already ships four hard-coded Insights sections (Trends, Funnel, Leaderboard, SourceCohorts) in `frontend/src/features/insights/` backed by `app/core/insights.py` + `app/routers/insights.py`. These cover a fixed analytical lens on pipeline health. The next product layer is a **user-configurable reporting and dashboard surface** — letting reps, managers, and admins compose their own views of deal, contact, and activity data rather than consuming only the four pre-built metrics.

The design questions:

1. **What entities are reportable?** Which of deals, activities, contacts, history entries should be queryable?
2. **What aggregation model?** Sum/count/avg, group-by dimensions, time-bucketing — how do reference CRMs expose this?
3. **What chart types?** Bar, line, funnel, table, KPI tile, pie — what does each CRM offer and what should CloseLoop prioritise?
4. **How do filters and segments compose?** Are filters per-report, dashboard-wide, or both?
5. **Live queries vs. materialised/pre-aggregated read model?** Given the existing ORM/DB layer (SQLite, Python-side aggregation via ADR-0023), which approach fits CloseLoop's constraints?

This document answers all five questions with reference CRM evidence and an explicit recommendation.

---

## 2. Reference CRM Survey

Five reference CRMs were surveyed in depth.

---

### 2.1 Salesforce Reports & Dashboards (Sales Cloud)

#### Reportable entities

Salesforce organises reports around **Report Types** — pre-defined or custom joins of up to four related objects. Standard report types include:

- `Opportunities` (= deals) — the primary analytical object
- `Opportunities with Products` — deal + line-item
- `Cases with Contacts` — support surface (not directly analogous)
- `Activities with Contacts and Leads` — activities joined to person records
- `Contacts & Accounts` — person + company
- Custom report types: admin-defined joins of any two or three related objects

Every report type has a fixed "primary" object; every row in the report is one record of that type.

#### Report shapes

| Shape | What it means | When used |
|-------|-------------|-----------|
| **Tabular** | Flat row-per-record table, no grouping. | Raw list export; leads feed |
| **Summary** | One grouping level (e.g. stage), with subtotals. | Stage-by-stage funnel |
| **Matrix** | Row group × column group, with subtotals on both axes. | Rep × stage cross-tab |
| **Joined** | Two independent report blocks side-by-side in the same view. | Compare pipeline vs. closed |

#### Aggregation model

- **Group-by dimensions:** up to three row group levels (Summary) or one row + one column group (Matrix). Groups can be on any field.
- **Aggregates per metric column:** Sum, Count, Average, Min, Max, Percent of Total.
- **Time-bucketing:** `GROUP BY` on a date field with a "bucket" setting: Day, Week, Month, Quarter, FY Quarter, Year.
- **Bucket fields (custom grouping):** "Bucket column" lets users bin a numeric field into named ranges (e.g. deal value < $10k = Small, $10k–$100k = Medium, >$100k = Large). Applied at report definition time, not at query time.
- **Formulas:** custom `SUMROW` / `PARENTROW` summary formulas on grouped reports (e.g. win rate = WON / TOTAL).

#### Chart types

Line, Bar (horizontal/vertical), Stacked Bar, Donut, Funnel, Scatter, Gauge. Charts are always attached to a single grouping level — they visualise the first group's aggregate.

#### Dashboard model

A Salesforce Dashboard is a grid of up to 20 **components**. Each component is bound to a **source report** and renders one of: metric/KPI tile (single aggregate), bar, line, donut, table, gauge, funnel, map. Dashboards have a **"running user"** setting — the report runs as a fixed user rather than the viewer, enabling shared team views without leaking per-rep filters. Dashboard auto-refresh is available on paid tiers; otherwise a manual "Refresh" button.

#### Filter/segment composition

- **Report-level filters:** each report carries a list of filter rows (`field op value`), AND-conjunctive, saved with the report definition. Users can toggle a "Show me" quick-filter at the top (e.g. "My Opportunities" vs. "All Opportunities").
- **Dashboard filters:** up to 5 dashboard-wide filter controls that push an additional `AND` clause into all component source reports simultaneously. Components can opt-out of a dashboard filter.
- **Historical snapshot:** Salesforce Reporting Snapshots archive report results daily to a custom object for trend-over-time queries that the live data no longer supports.

#### Performance model

Salesforce pushes aggregation to its internal query layer (a proprietary analytic SQL engine, not a standard RDBMS). Reports on large orgs use a background "run report" job with async result polling. Dashboard components cache results for up to 24 h. No materialised views in the user-visible model; the cache is opaque.

---

### 2.2 HubSpot Reporting (Custom Report Builder + Dashboards)

#### Reportable entities

HubSpot's Custom Report Builder (CRB) organises data sources as "data sets" scoped to a **primary object** + optional **associated objects**:

- Contacts (primary), optionally joined to: Deals, Companies, Activities, Form submissions
- Deals (primary), optionally joined to: Contacts, Companies, Activities, Line items
- Activities (primary): calls, meetings, emails, notes
- Companies — analogous to Accounts

#### Report types / shapes

| Type | Notes |
|------|-------|
| **Single object** | One row per primary object record |
| **Cross-object** | Primary + ≥1 associated; rows can fan-out on the associated object |
| **Funnel** | Ordered stage sequence with count/conversion rate at each step |
| **Attribution** | First-touch / last-touch / multi-touch revenue credit across contacts |

#### Aggregation model

- **Group-by:** one primary dimension (often a categorical field or a date bucket). CRB v2 (2025) supports a second group-by (creating a 2D cross-tab).
- **Aggregates:** Count of records, Count distinct, Sum, Average, Min, Max, Median, % of Total.
- **Time-bucketing:** Week, Month, Quarter, Year applied to any date field. Date-range filters on each report ("last 30 days", "this quarter", "custom range").
- **Filters:** up to 20 filter rows per report, AND/OR logic supported via a group-based filter builder. Filters are saved with the report.

#### Chart types

Table (default), Bar (horizontal/vertical), Stacked Bar, Line, Area, Pie, Donut, KPI/metric tile (single number), Combo (bar + line). Funnels rendered as a special stage-conversion view.

#### Dashboard model

- A **Dashboard** is a named grid of report cards. No fixed maximum; practical limit ~20 before performance degrades.
- Each card is an **embedded report** — the report definition is shared between its dashboard embed and its standalone view. Editing the report changes the dashboard card.
- **Goals:** a dashboard card can carry a "goal" line on its chart — a horizontal reference line at a target value. This is set at the dashboard level, not in the report definition.
- **Dashboard filters:** a small set of property filters applied across all cards simultaneously (e.g. "Owner is Me" or "Deal stage is Closed Won").
- **Sharing:** dashboards are owned by one user but can be shared read-only or edit-access to teams. No "running user" concept — the viewer's access level governs what data is returned.

#### Performance model

HubSpot runs its CRB on a separate analytics pipeline (columnar store) that lags the operational database by ~15 min. Reports show a "last refreshed" timestamp. The user does not control refresh granularity. CRB queries are async; the UI polls for results and shows a spinner. Ad-hoc queries in the CRB can take 2–10 s for large portals.

---

### 2.3 Pipedrive Insights (Pipeline + Activity + Conversion Reports)

#### Reportable entities

Pipedrive Insights is deliberately narrower than Salesforce/HubSpot — it exposes three fixed "report types":

| Report type | Primary entity | What it measures |
|-------------|----------------|------------------|
| **Revenue** | Deals | Pipeline value, won/lost revenue |
| **Deals** | Deals | Deal counts, stage distribution, cycle time |
| **Activities** | Activities | Completed/overdue/upcoming counts by type and rep |
| **Conversion** | Stage transitions | Stage-to-stage conversion rates and time-in-stage |

No ad-hoc join to contacts or accounts. The contact/person object is filterable but not a primary entity for reports.

#### Aggregation model

- **Group-by:** one dimension per report, from a fixed menu (owner, stage, pipeline, source, time period).
- **Aggregates:** Count (deals or activities), Sum (deal value), Average (cycle time, deal value).
- **Time-bucketing:** Week, Month, Quarter, Year. Each report has a "period" selector applied to `created_at` or `won_time`.
- **No user-defined group-by combinations** — the allowed dimensions per report type are fixed by Pipedrive.

#### Chart types

Bar (vertical default), Line (for trend-over-time reports), Funnel (for conversion report). Table view always available alongside the chart. No pie/donut, no scatter, no gauge.

#### Dashboard model

- A **Dashboard** is a grid of **report tiles**. Each tile has a fixed shape (chart + title + total number).
- Up to 40 tiles per dashboard. Multiple dashboards per account.
- **Sharing:** dashboards shareable with a public URL or with specific team members.
- **No cross-tile filters** — each tile is an independent report with its own filter set. There is no dashboard-wide filter control.

#### Filter/segment composition

Each report carries filter controls:
- Owner (one or multiple reps)
- Pipeline (if multiple pipelines)
- Deal stage
- Date range
- Deal labels / tags (if configured)

Filters are per-tile; there is no dashboard-level filter that pushes across all tiles simultaneously.

#### Performance model

Pipedrive Insights queries are live against the operational DB with an in-memory aggregation layer. No materialised views or async results — all reports return synchronously within 2–5 s. For very large accounts (tens of thousands of deals), Pipedrive applies query-level limits and recommends CSV export for full-data analysis.

---

### 2.4 Attio Reports

#### Reportable entities

Attio's report model (as of 2025 reporting surface) is the most object-agnostic of the five CRMs. Reports are defined against a **collection** (any configured object type — People, Companies, Deals, custom objects). Any attribute of the collection is filterable and groupable.

| Collection | Approximate equivalent |
|------------|------------------------|
| People | Contacts |
| Companies | Accounts |
| Deals | Deals |
| (custom) | Any user-defined object |
| Activities (notes, tasks, meetings) | Activities |

#### Aggregation model

- **Group-by:** one or two dimensions. Any attribute of the collection (categorical, user, date).
- **Aggregates:** Count, Sum, Average, Min, Max applied to any numeric attribute.
- **Time-bucketing:** Day, Week, Month, Quarter, Year applied to any date attribute.
- **Filters:** per-report filter rows with AND/OR logic. Filter conditions use the same attribute taxonomy as Attio's list views — same operator set (`is`, `is not`, `is any of`, `is not any of`, `is greater than`, `is between`, `is known`, `is not known`).

#### Chart types

Bar (horizontal/vertical), Line, Pie/Donut, KPI tile (single metric), Table. No funnel or gauge built-in.

#### Dashboard model

Attio's dashboard surface is **views-based**: a report is essentially a "view in chart mode" rather than a separate concept from a filtered list. Dashboards are collections of saved report views. No dashboard-level filters; each view carries its own filter set. Reports are collaborative — shared with the workspace, not per-user.

#### Performance model

Attio's query model is synchronous against a PostgreSQL backend with appropriate indexes. No materialised views at the user-visible level; the engine handles query optimisation internally. Response times are typically < 1 s for standard aggregations on datasets up to ~10k records per collection.

---

### 2.5 Zoho Analytics / CRM Analytics

#### Reportable entities

Zoho CRM has two distinct layers:

1. **Built-in CRM reports** — a set of ~50 pre-built reports across Leads, Contacts, Accounts, Deals (Potentials in Zoho terminology), Activities, Emails, Campaigns. Each report has a fixed layout.
2. **Zoho Analytics integration** — a separate BI product that can sync CRM data hourly/daily and offers full ad-hoc reporting with cross-module joins.

The built-in CRM reports are the analogous surface to CloseLoop's current Insights feature (pre-built views) and a modest user-customisable extension. The Zoho Analytics integration is the full BI layer (out of scope for CloseLoop at this product stage).

#### Built-in CRM report types

| Category | Example reports |
|----------|----------------|
| **Activity Reports** | Activities by type, overdue, completed, upcoming |
| **Pipeline Reports** | Deals by stage, deals by rep, deal conversion rate |
| **Revenue Reports** | Won revenue by month/quarter/year, revenue forecast |
| **Contact Reports** | Contacts by source, contacts by owner, lead-to-contact conversion |

#### Aggregation model

- **Group-by:** one dimension, fixed per report (not user-configurable in built-in reports).
- **Aggregates:** Count, Sum, Average applied to a single metric column.
- **Time-bucketing:** fixed per report (Month, Quarter, Year) with a date-range filter at the top.
- **Custom Reports (Zoho CRM):** user-configurable. Supports: tabular (flat list), summary (one group level), matrix (row × col). Up to 3 columns, 2 group levels. Filter rows with AND logic. A maximum of 5 custom charts per dashboard.

#### Chart types

Bar, Column, Line, Pie, Donut, Area, Funnel, KPI tile. Charts are attached to the report's first group-by dimension.

#### Dashboard model

- **Dashboards** in Zoho CRM are a named grid of up to 20 report components.
- Each component is bound to a saved report and renders the report's chart plus a key metric.
- **Home dashboard** is shared and visible to all users with the Dashboard permission; individual users can also have private dashboards.
- **Threshold alerts:** Zoho CRM supports "KPI widget alert" — a threshold configured on a KPI tile that sends an email notification when the metric crosses the threshold. This integrates with Zoho's workflow rule engine (not the in-app notification bell) — the alert fires via the outbox.

#### Performance model

Zoho built-in CRM reports are synchronous live queries. Zoho Analytics (the separate BI product) uses nightly/hourly ETL sync to a columnar store — a materialised read model. For CloseLoop's scope (built-in CRM reports, not the full BI product), live queries are the appropriate analogy.

---

## 3. Cross-CRM Synthesis: Reportable Entities

| Entity | Salesforce | HubSpot | Pipedrive | Attio | Zoho CRM |
|--------|-----------|---------|-----------|-------|----------|
| Deals / Opportunities | ✅ Primary | ✅ Primary | ✅ Primary | ✅ Primary | ✅ Primary |
| Contacts / Leads | ✅ Primary | ✅ Primary | Filter only | ✅ Primary | ✅ Primary |
| Activities | ✅ Primary | ✅ Primary | ✅ Primary | ✅ Primary | ✅ Primary |
| Accounts / Companies | ✅ Primary | ✅ (Companies) | N/A | ✅ Primary | ✅ Primary |
| Stage transitions / History | Via Snapshot | Via Funnel type | Conversion report | Attribute history | Pipeline report |
| History entries (audit log) | Via SOQL query (not report builder) | Not exposed | Not exposed | Not exposed | Not exposed |
| Custom objects | ✅ | ✅ (Enterprise) | ❌ | ✅ | ✅ |

**Key observation:** Every CRM makes **Deals + Activities** the primary reportable entities; Contacts are primary in all except Pipedrive. Stage transitions / history are exposed through specialised report types (funnel, conversion), not as a free-standing queryable entity. The audit log (`history_entries` in CloseLoop) is never exposed directly in any CRM's report builder — it is internal.

---

## 4. Cross-CRM Synthesis: Aggregation Model

| Dimension | Salesforce | HubSpot | Pipedrive | Attio | Zoho CRM |
|-----------|-----------|---------|-----------|-------|----------|
| Group-by levels | 1–3 (Summary) / 1×1 (Matrix) | 1–2 | 1, fixed menu | 1–2 | 1–2 |
| Aggregate functions | Count, Sum, Avg, Min, Max | Count, Count distinct, Sum, Avg, Min, Max, Median | Count, Sum, Avg | Count, Sum, Avg, Min, Max | Count, Sum, Avg |
| Time-bucketing | Day/Week/Month/Quarter/Year | Week/Month/Quarter/Year | Week/Month/Quarter/Year | Day/Week/Month/Quarter/Year | Month/Quarter/Year |
| AND/OR filter logic | AND only (report filters) | AND/OR supported | AND only | AND/OR supported | AND only |
| User-defined group-by | ✅ | ✅ | ❌ Fixed dimensions | ✅ | ✅ (custom report) |

**Key observations:**
1. Sum, Count, Average are the "minimum viable" aggregate set — every CRM supports them. Median and Count distinct are secondary.
2. One group-by dimension per report is the universal baseline; two dimensions (cross-tab) is the advanced case available in 4 of 5 CRMs.
3. Month/Quarter/Year time-bucketing is universal. Day-level bucketing is less common; only Salesforce and Attio support it in the report builder.
4. AND-only conjunctive filters are the baseline; AND/OR logic appears in HubSpot and Attio's more advanced builders. Pipedrive offers only the fewest filter options (fixed dimensions).

---

## 5. Cross-CRM Synthesis: Chart Types

| Chart type | Salesforce | HubSpot | Pipedrive | Attio | Zoho CRM | Priority for CloseLoop |
|------------|-----------|---------|-----------|-------|----------|----------------------|
| Bar (vertical) | ✅ | ✅ | ✅ | ✅ | ✅ | **P0 — already exists (`BarChart.tsx`)** |
| Line | ✅ | ✅ | ✅ | ✅ | ✅ | **P0 — already exists (`LineChart.tsx`)** |
| KPI / metric tile | ✅ | ✅ | ✅ | ✅ | ✅ | **P0 — simple, high value** |
| Table | ✅ | ✅ | ✅ | ✅ | ✅ | **P0 — already exists (RepLeaderboard uses table rows)** |
| Funnel | ✅ | ✅ | ✅ | ❌ | ✅ | P1 — already exists in ConversionFunnel |
| Stacked Bar | ✅ | ✅ | ❌ | ✅ | ✅ | P1 |
| Pie / Donut | ✅ | ✅ | ❌ | ✅ | ✅ | P2 |
| Area | ❌ | ✅ | ❌ | ❌ | ✅ | P2 |
| Gauge | ✅ | ❌ | ❌ | ❌ | ✅ | P3 — complex, low CRM utility |
| Scatter | ✅ | ❌ | ❌ | ❌ | ❌ | P3 — rare in CRM context |

CloseLoop already has `BarChart.tsx` and `LineChart.tsx` as hand-rolled SVG primitives (ADR-0024). A KPI tile is trivially a styled `<div>` with a large number — no chart primitive needed.

---

## 6. Cross-CRM Synthesis: Filter/Segment Composition

| Pattern | Salesforce | HubSpot | Pipedrive | Attio | Zoho |
|---------|-----------|---------|-----------|-------|------|
| Per-report filter rows | ✅ (saved) | ✅ (saved) | ✅ (per tile, unsaved) | ✅ (saved) | ✅ (saved) |
| Dashboard-level cross-tile filter | ✅ (up to 5) | ✅ | ❌ | ❌ | ❌ |
| "Running user" / viewer isolation | ✅ | ❌ | ❌ | ❌ | ❌ |
| Quick-filter UI (single click) | ✅ ("My / All") | ✅ (date range picker) | ✅ (period selector) | ✅ | ✅ (date range) |
| AND/OR filter logic | AND only | AND/OR | AND only | AND/OR | AND only |

**Key observation:** Per-report saved filters are universal. Dashboard-level cross-tile filters are a Salesforce/HubSpot-only premium feature. Pipedrive's simplest model (per-tile, transient, no cross-tile filter) is the most appropriate starting point for CloseLoop's current complexity.

---

## 7. CloseLoop's Existing Data Model — Reporting Sources

All five reportable entity types from the reference CRM survey map cleanly to CloseLoop's existing ORM models.

### Primary reportable entities (current models)

| Report data source | ORM model / table | Key fields available |
|-------------------|-------------------|---------------------|
| **Deals** | `Deal` / `deals` | `stage`, `stage_id`, `value`, `probability`, `owner_id`, `contact_id`, `created_at`, `closed_at`, `expected_close_date` |
| **Activities** | `Activity` / `activities` | `type` (call/email/meeting/note), `due_at`, `completed_at`, `owner_id`, `deal_id`, `contact_id`, `created_at` |
| **Contacts** | `Contact` / `contacts` | `source`, `owner_id`, `account_id`, `lead_score`, `created_at` |
| **Accounts** | `Account` / `accounts` | `industry`, `owner_id`, `created_at` |
| **Stage transitions** | `StageTransition` / `stage_transitions` | `deal_id`, `from_stage`, `to_stage`, `occurred_at` |

### Secondary / derived sources

| Source | ORM model / table | Usage in reports |
|--------|-------------------|-----------------|
| **History entries** | `HistoryEntry` / `history_entries` | Audit log — should NOT be exposed in a user-configurable report builder; too low-level and entity-specific |
| **Notifications** | `Notification` / `notifications` | Internal inbox — not a reporting entity |
| **Automation rules** | `AutomationRule` / `automation_rules` | Config entity — not a reporting entity |
| **Event log** | `EventLog` / `event_log` | Legacy audit surface — not a reporting entity |

### Existing aggregation architecture (ADR-0023)

The current `app/core/insights.py` pattern is:
1. Router fetches raw rows via simple `.all()` queries → plain dicts.
2. Pure functions in `app/core/` perform all aggregation in Python.
3. No SQL `GROUP BY`, window functions, or subqueries.

This is explicitly documented in ADR-0023 and the test strategy relies on it (pure functions are testable without a DB fixture). Any reporting engine CloseLoop ships must respect or deliberately supersede this architectural decision.

### Activity data as the primary report data source

The activity-timeline event model (`history_entries`) was surveyed for report data source potential. It is a poor fit for the primary report data source for four reasons:
1. It is an audit log, not a query interface. `entity_id` has no FK, so joining to the entity fields (e.g., `Deal.stage`) requires an application-level join — there is no foreign key the DB engine can use.
2. It records mutations, not entity states. A report of "how many deals are in 'negotiation' right now" is answered by `Deal.stage`, not by the history entries.
3. The kind set is closed and append-only — it was designed for entity-timeline rendering, not for ad-hoc group-by queries.
4. Stage transitions are already modelled more cleanly in `StageTransition` for query purposes (joined to `Deal` via FK).

The **notifications engine** (`notifications` table) is similarly unsuitable — it is a per-user inbox, not a CRM metric source. Its `kind` and `entity_type`/`entity_id` fields could theoretically answer "how many automation events fired last month," but that is a meta-metric about the automation engine, not a CRM business metric.

**Conclusion:** the primary report data sources for a CloseLoop reporting feature are `deals`, `activities`, `contacts`, `accounts`, and `stage_transitions` — the same five entity tables already queried by `app/core/insights.py`. History entries and notifications are not reporting entities.

---

## 8. Borrowed vs. Rejected: Recommended Model for CloseLoop

### 8.1 What to Borrow

#### From Pipedrive: fixed report types as the starting point

Pipedrive's model — a small set of named report types with fixed primary entities and a curated menu of group-by dimensions — is the right starting point for CloseLoop's scale and complexity. The current Insights feature already implements this pattern (four fixed views). The next step is to make those report types more flexible (user-adjustable filters, group-by dimension selector) rather than jumping to a full ad-hoc report builder.

**Recommended initial report types:**

| Report type | Primary entity | Key metric |
|-------------|----------------|------------|
| Deal Trends | Deals | Count / value by stage over time |
| Conversion Funnel | Stage transitions + Deals | Conversion rate and avg time per stage |
| Activity Summary | Activities | Count by type, by rep, by period |
| Rep Performance | Deals | Revenue, deal count, avg cycle time per rep |
| Source Cohort | Contacts + Deals | Win rate and avg value by contact source |
| Contact Growth | Contacts | New contacts per period by source/owner |

The first two are already shipped. The remaining four add new slices over existing query patterns.

#### From HubSpot: per-report saved filters with AND logic

Every report should carry a saved set of filter rows (field, op, value), evaluated AND-conjunctively, persisted with the report definition. This mirrors both HubSpot's report filter model and the existing automation-rule condition model (`conditions_json` / `evaluate_conditions`). Reusing the same `{field, op, value}` triple shape and the `eq`, `neq`, `in` operator set avoids inventing a new filter language.

**Operators needed at launch:** `eq`, `neq`, `in`, `gt`, `lt`, `between` (for numeric ranges and date ranges). The automation engine's `evaluate_conditions` already handles `eq`, `neq`, `in` — `gt`, `lt`, `between` extend the existing evaluator pattern without a structural change.

#### From Pipedrive: date-range filter as a first-class quick-control

Every report should have a date-range picker (last 30/90/365 days, or custom range) as a top-level filter control, consistent with what `GET /insights/trends` already does via the `window_days` query param. This is the single highest-value filter control across all five CRMs.

#### From HubSpot + Attio: one or two group-by dimensions

Support one group-by dimension per report (Phase 1) with the option to add a second dimension (Phase 2 / cross-tab). The allowed group-by dimensions for each report type should be a curated list (Pipedrive model), not a fully free-form field picker (Salesforce/HubSpot model). Curated menus prevent nonsensical combinations (e.g., grouping deals by note body) and keep the aggregation logic tractable.

**Recommended group-by dimension menus per report type:**

| Report type | Allowed group-by dimensions |
|-------------|----------------------------|
| Deal Trends | Stage, Owner, Source (via contact join), Pipeline stage, Time period |
| Activity Summary | Activity type, Owner, Deal stage, Time period |
| Rep Performance | (inherently grouped by rep — no user group-by needed) |
| Source Cohort | (inherently grouped by source — no user group-by needed) |
| Contact Growth | Source, Owner, Time period |

#### From HubSpot: KPI tile as a first-class chart type

A single-number KPI tile (current metric with optional vs.-previous-period delta) is the highest-value chart type relative to implementation cost. It requires no SVG chart primitive — it's a styled `<div>`. Every CRM exposes it. The existing `GET /stats` response already computes `total_deals`, `pipeline_value`, and similar single-number metrics; KPI tiles can display these directly.

#### From Zoho: threshold alerts as a notification-engine integration point

Zoho's KPI widget alert — a threshold that fires a notification when a metric crosses a value — is the natural integration point between a future reporting feature and the existing notifications engine (`create_notification()` in `app/services/notifications.py`). This is deferred (Phase 3), but the architecture should be designed so that a saved report definition can carry an optional `alert_threshold_json` field that the scheduled-automation poller evaluates. The `"scheduled"` trigger type in `AutomationRule` is the mechanism — a scheduled rule could run a report query and call `create_notification()` when the result crosses a threshold. No new notification pipeline is needed.

#### From Salesforce + HubSpot: structured dashboard with named saved reports

A **Dashboard** is a named collection of **saved Report** definitions, each rendered as a card at a specific grid position. The data model should be:

```
reports
  id              INTEGER PK
  name            TEXT NOT NULL
  report_type     TEXT NOT NULL        -- "deal_trends" | "activity_summary" | etc.
  config_json     TEXT NOT NULL        -- group_by, aggregates, filters, date_range, chart_type
  created_by      INTEGER → users(id)
  created_at      TEXT NOT NULL

dashboards
  id              INTEGER PK
  name            TEXT NOT NULL
  created_by      INTEGER → users(id)
  created_at      TEXT NOT NULL

dashboard_cards
  id              INTEGER PK
  dashboard_id    INTEGER → dashboards(id) ON DELETE CASCADE
  report_id       INTEGER → reports(id) ON DELETE CASCADE
  position        INTEGER NOT NULL     -- card order; 0-indexed
  width           TEXT NOT NULL        -- "half" | "full"; maps to CSS grid-cols-1 / grid-cols-2
```

This gives reports their own identity (usable standalone, outside a dashboard) and allows dashboards to be composed of saved reports — the same pattern HubSpot uses. Salesforce's more complex "running user" and component-to-report binding are over-engineered for CloseLoop's single-tenant, role-based access model.

---

### 8.2 What to Reject

#### Reject: ad-hoc cross-object join report builder (Salesforce Report Types)

Salesforce allows users to define custom report types by joining up to four objects. Building a general-purpose join builder for CloseLoop (deals join activities join contacts join accounts with configurable join direction) is out of scope for the product's current complexity and team size. The curated report types cover 95% of the analytical value with a fraction of the implementation cost.

#### Reject: async/background query execution (HubSpot CRB model)

HubSpot's Custom Report Builder runs queries asynchronously (results polled via a job ID) because it operates against a columnar store with multi-second query times. CloseLoop's Python-side aggregation model (ADR-0023) on a single-tenant SQLite with hundreds-to-low-thousands of records completes in < 100 ms synchronously. Adding async job infrastructure would be unnecessary complexity.

#### Reject: dashboard-level cross-tile filters (Salesforce + HubSpot premium feature)

Cross-tile dashboard filters require either (a) the dashboard to push a filter state into each card's query, or (b) each card to accept a parent-injected filter prop. Both are non-trivial to implement and are a premium UX feature not available in Pipedrive or Attio. CloseLoop should start with per-report filters only; cross-tile dashboard filters are P3.

#### Reject: "running user" concept (Salesforce)

Salesforce's running user allows a manager's dashboard to be viewed by reps, but all data runs through the manager's access level. CloseLoop's access control is row-level: reps see only their own deals (enforced in the `rep_leaderboard` scoping pattern already in `app/routers/insights.py`). Viewer-based access is the correct model; a "running user" concept is not needed.

#### Reject: separate BI product / ETL materialisation (Zoho Analytics)

Zoho Analytics is a separate columnar BI store synced from the CRM database on a schedule. For CloseLoop's data volumes (hundreds to low thousands of records), a separate ETL pipeline is engineering overhead with no performance benefit. All reports should query the operational SQLite database directly.

#### Reject: formula columns / summary formulas (Salesforce)

Salesforce allows custom `SUMROW`/`PARENTROW` formula columns on grouped reports (e.g., win rate calculated from a ratio of group subtotals). These require a formula evaluator and a two-pass aggregation algorithm. The highest-value derived metrics (win rate, conversion rate, avg cycle time) should be computed as first-class outputs of the report type's aggregation function, not as user-defined formulas. Formula columns are deferred indefinitely.

#### Reject: per-report "owned" sharing model (Salesforce admin-managed)

Salesforce reports are owned by a user and explicitly shared with folders/groups via the Metadata API. CloseLoop should adopt HubSpot's simpler model: dashboards and reports are workspace-wide by default, visible to all authenticated users, and editable by admin/manager only (same role gate as `automation_rules.py`). No sharing permissions layer needed.

---

## 9. Live Query vs. Materialised/Pre-Aggregated Read Model

This is the most technically consequential architectural question for the reporting feature.

### Current architecture (ADR-0023)

CloseLoop already made a deliberate decision in ADR-0023: all Insights aggregation is computed in pure Python over full table scans fetched via `.all()` queries. This works because:
- Single-tenant deployment — one SQLite database per installation
- Expected data volumes: hundreds to low thousands of deals/contacts
- Python-side aggregation is testable without a DB fixture (critical for the test strategy)
- SQLite analytical SQL support (window functions, CTEs) is limited on older releases

### The case for staying live

For a single-tenant CRM at CloseLoop's scale, full table scan → Python aggregation is fast. The current `GET /insights/trends` endpoint fetches all deals and aggregates in Python; the response time is < 50 ms locally with a thousand deals. Adding new report types with the same pattern will stay under 200 ms for datasets up to ~5,000 deals (the practical single-tenant ceiling before a CRM user would migrate to Salesforce).

**Arguments for live queries:**
- Zero data freshness lag — reports always reflect the current state of the operational DB
- No ETL pipeline or materialisation job to maintain
- Consistent with the existing ADR-0023 decision and the test strategy
- Adding a materialised read model to SQLite is complex (triggers or periodic batch jobs); neither fits CloseLoop's no-background-worker constraint

**Arguments against (and why they don't apply at CloseLoop's scale):**
- Performance degrades at > 10k rows → not a concern for a single-tenant installation of CloseLoop; at that scale the team would have graduated to a hosted CRM
- Query lock contention on SQLite → SQLite's WAL mode (not explicitly configured in CloseLoop but the default for most SQLite deployments) handles concurrent reads well; a reporting query (read-only) does not block write transactions

### The case against materialisation

A materialised pre-aggregated read model (e.g., a `report_cache` table written by a background job or a SQLite trigger) would require:
1. A background job (CloseLoop has one: the `_scheduled_automations_loop()` asyncio task in `app/main.py` polling every 60 s). A reporting cache refresh could piggyback on this, but cache invalidation becomes complex.
2. Stale data risk — the cache is always some seconds/minutes behind the operational data.
3. Schema complexity — a generic cache store is either too narrow (stores pre-formatted JSON, hard to re-aggregate) or too wide (stores intermediate aggregates, requires a query planner to combine them).
4. Test isolation problems — ADR-0005 requires in-memory SQLite for tests; a materialisation job that writes to a cache table complicates the test fixture setup.

Given ADR-0023, ADR-0005, and CloseLoop's no-background-worker principle, **materialisation should be explicitly rejected for Phase 1 and Phase 2 of reporting**.

### Recommended approach: live Python-side aggregation, same as existing Insights

Each report type's backend should be a pure function in `app/core/reports.py` (analogous to `app/core/insights.py`) that:
- Accepts raw row lists (plain dicts, not ORM objects)
- Applies group-by, aggregate, date-range filter, and field-value filters in Python
- Returns a structured result dict

The router (`app/routers/reports.py`) fetches raw rows via simple unfiltered `.all()` queries, projects to dicts, and calls the core function — the same pattern as `app/routers/insights.py`.

This means:
- All report aggregation logic is testable without a DB fixture (`tests/test_core_reports.py` with synthetic dicts)
- The injectable clock (ADR-0006) is available for any time-relative filter
- Performance is bounded by Python's iteration speed over the row list, which is adequate at the expected data volumes
- No new infrastructure, no materialisation, no caching layer

### If data volume grows (> 5k deals): deferred paths

If a future deployment accumulates > 5k deals and report latency becomes measurable, the right migration paths are:
1. **SQLite indexes** — composite indexes on `(stage, created_at)`, `(owner_id, created_at)` for deals. Already partially present (see `models.py`).
2. **SQL-level pre-filtering** — filter by date range in the query (`WHERE created_at >= ?`) before fetching into Python. This narrows the full-scan cardinality without changing the aggregation model.
3. **SQLite window functions** — SQLite 3.25.0+ supports `ROW_NUMBER()`, `SUM() OVER`, etc. At that point SQL aggregation could be reconsidered, but only under a new ADR that supersedes ADR-0023.
4. **Materialised `report_cache` table** — only viable once CloseLoop has a reliable background job infrastructure beyond the 60 s automation poller. Not recommended before then.

---

## 10. Patterns Summary: Borrowed vs. Rejected

### Borrowed

| Pattern | Source | How CloseLoop should adopt it |
|---------|--------|-------------------------------|
| Fixed report types with named primary entities | Pipedrive | Start with 6 named report types (Deal Trends, Conversion Funnel, Activity Summary, Rep Performance, Source Cohort, Contact Growth); avoid free-form cross-object joins |
| Curated group-by dimension menus per report type | Pipedrive | Each report type exposes a specific list of allowed group-by dimensions, not a generic field picker |
| Per-report saved filters (field/op/value rows, AND-conjunctive) | HubSpot, Attio | Persist as `config_json` on the `reports` table; reuse the `{field, op, value}` shape from `conditions_json` in automation rules |
| Date-range filter as first-class quick-control | All 5 CRMs | Per-report date-range selector (30/90/365 days or custom range) stored in `config_json` |
| Sum, Count, Average as the baseline aggregate set | All 5 CRMs | Core aggregate functions in `app/core/reports.py` |
| Month/Quarter/Year time-bucketing | All 5 CRMs | Applied in Python to ISO-8601 string timestamps (consistent with `trends()` in `app/core/insights.py`) |
| KPI tile as a chart type | All 5 CRMs | Single-number display, no chart primitive needed |
| Structured dashboard: named dashboard → cards → saved reports | Salesforce, HubSpot | `dashboards` + `dashboard_cards` + `reports` three-table model |
| Reports standalone (usable outside a dashboard) | HubSpot | `reports` table is independent; `dashboard_cards` links them to dashboards |
| Admin/manager-only write access to reports and dashboards | HubSpot, Salesforce | Same `_require_admin_or_manager` role gate as `automation_rules.py` and `pipeline.py` |
| Workspace-wide visibility (all users can view) | HubSpot, Attio | No per-user sharing permissions layer; role gate on writes only |
| KPI threshold alerts via scheduled automation + notifications | Zoho | Deferred (Phase 3): scheduled `AutomationRule` evaluates a report query and calls `create_notification()` when a threshold is crossed |
| Live synchronous queries, no ETL | Pipedrive, Attio | Live Python-side aggregation following ADR-0023; no materialised cache |
| Pure Python aggregation in `app/core/` | ADR-0023 | `app/core/reports.py` — pure functions, no I/O, testable without DB fixture |

### Rejected

| Pattern | Source | Why rejected |
|---------|--------|-------------|
| Ad-hoc cross-object join report builder | Salesforce Report Types | Out of scope; curated report types cover 95% of the value with a fraction of the complexity |
| Async/background query execution (job polling) | HubSpot CRB | Unnecessary at CloseLoop's data volumes; live sync query is < 200 ms |
| Dashboard-level cross-tile filters | Salesforce, HubSpot | Premium feature; per-report filters are sufficient at launch |
| "Running user" concept | Salesforce | Viewer-based access (row-level rep scoping already in `insights.py`) is the correct model |
| Separate BI product / ETL materialisation | Zoho Analytics | Engineering overhead with no benefit at CloseLoop's data volumes |
| Formula columns / SUMROW expressions | Salesforce | Derived metrics (win rate, conversion rate) computed as first-class report type outputs, not user-defined formulas |
| Per-report sharing/folder permissions | Salesforce | Workspace-wide visibility + role-gated writes is simpler and sufficient |
| Materialised pre-aggregated read model | — | Incompatible with ADR-0023, ADR-0005 test fixture model, and the no-background-worker principle |
| SQL GROUP BY push-down for aggregation | — | Supersedes ADR-0023; not worth the tradeoff at current data volumes; deferred to a future ADR if row count forces it |
| Gauge chart type | Salesforce, Zoho | Complex to render, low analytical value in CRM context |
| Pie/Donut as P0 chart type | HubSpot, Attio | Deceptive for proportional data in CRM context; bars are clearer; P2 |

---

## 11. Recommended Architecture (Phase 1)

### New files

| File | Purpose |
|------|---------|
| `app/core/reports.py` | Pure aggregation functions per report type. No I/O. Follows `app/core/insights.py` pattern. |
| `app/routers/reports.py` | REST API: `GET /reports`, `POST /reports`, `GET /reports/{id}`, `PATCH /reports/{id}`, `DELETE /reports/{id}`, `GET /reports/{id}/run`. |
| `app/routers/dashboards.py` | REST API: `GET /dashboards`, `POST /dashboards`, `GET /dashboards/{id}`, `PATCH /dashboards/{id}`, `DELETE /dashboards/{id}`. Cards managed via `POST /dashboards/{id}/cards`, `DELETE /dashboards/{id}/cards/{card_id}`. |
| `tests/test_core_reports.py` | Pure unit tests for aggregation functions (no DB fixture, synthetic dicts). |
| `tests/test_reports.py` | API integration tests using the `client` fixture. |
| `tests/test_dashboards.py` | API integration tests for dashboard CRUD and card management. |
| `frontend/src/features/reports/` | React components: `ReportsView.tsx`, `ReportCard.tsx`, `ReportRunView.tsx`, `DashboardView.tsx`. |

### New ORM models (in `app/models.py`)

```python
class Report(Base):
    __tablename__ = "reports"
    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    report_type = Column(String, nullable=False)  # "deal_trends" | "activity_summary" | etc.
    config_json = Column(Text, nullable=False, default="{}")
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at  = Column(String, nullable=False)

class Dashboard(Base):
    __tablename__ = "dashboards"
    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    created_by  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at  = Column(String, nullable=False)

class DashboardCard(Base):
    __tablename__ = "dashboard_cards"
    id           = Column(Integer, primary_key=True)
    dashboard_id = Column(Integer, ForeignKey("dashboards.id", ondelete="CASCADE"), nullable=False)
    report_id    = Column(Integer, ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    position     = Column(Integer, nullable=False, default=0)
    width        = Column(String, nullable=False, default="half")  # "half" | "full"
```

### `config_json` shape

```json
{
  "group_by": "stage",
  "aggregate": "count",
  "date_field": "created_at",
  "date_range_days": 90,
  "chart_type": "bar",
  "filters": [
    {"field": "owner_id", "op": "eq", "value": 42}
  ]
}
```

The `filters` array reuses the `{field, op, value}` shape from `conditions_json` in automation rules. The same `evaluate_conditions()` function from `app/services/automations.py` can be called against each row dict during aggregation — or its pattern can be replicated in `app/core/reports.py` without importing from `services` (to preserve the pure-core boundary; `app/core/` must not import from `app/services/`).

### `GET /reports/{id}/run` endpoint

The execution endpoint that actually aggregates data. Pattern identical to `app/routers/insights.py`:
1. Fetch raw rows via `.all()` → project to dicts.
2. Call the appropriate pure function from `app/core/reports.py` with the report's `config_json` parameters.
3. Return the aggregated result.

No caching, no job queue, no async result polling.

### Access control

- **Read** (GET all reports, GET dashboard, GET /run): all authenticated users.
- **Write** (POST/PATCH/DELETE reports and dashboards): admin/manager only — same `_require_admin_or_manager` pattern as `app/routers/automation_rules.py`.

### Chart types (Phase 1)

Extend the existing two SVG primitives (`BarChart.tsx`, `LineChart.tsx`) to handle:
- **KPI tile** — no SVG needed, a `<div>` with a large number and label.
- **Table** — reuse the table pattern from `RepLeaderboard.tsx`.
- `BarChart.tsx` and `LineChart.tsx` accept a `{ label, value }[]` data prop; the report runner returns this shape directly from the core function.

New chart types (Stacked Bar, Pie/Donut) are deferred to Phase 2. No charting library should be added — the ADR-0024 decision to avoid third-party charting libraries remains valid. A Stacked Bar can be implemented as an extension of `BarChart.tsx` with a `segments` prop; a Donut would be a new ~90-line SVG primitive in `charts/`.

---

## 12. Open Questions for the Build Phase

1. **`report_type` vocabulary vs. flexible config:** Should `report_type` be a strict closed enum (like `trigger_event` in automation rules) with the aggregation function selected at execution time? Or should the config be fully declarative (group-by + aggregate + entity, with no fixed type)? The closed enum is safer and more testable; fully declarative is more flexible. Recommend closed enum for Phase 1, revisit in Phase 2.

2. **Activity `type` filter vs. deal `stage` filter in `config_json`:** The `filters` array uses generic `{field, op, value}` triples — the same shape as automation conditions. But some report types need filters against joined tables (e.g., deal stage when running an Activity Summary). Does the filter operate on the pre-join dict or the final row? Recommend filtering against the pre-projection dict (same as automation rule conditions) and requiring the router's projection function to include all filterable fields in the dict.

3. **Time-bucketing implementation:** ISO-8601 strings in SQLite (the current timestamp format) need to be truncated to month/quarter/year in Python. `datetime.fromisoformat(ts).strftime("%Y-%m")` is sufficient for monthly bucketing. The injected clock (ADR-0006) is not needed here (time-bucketing is applied to historical data, not to "now"), but the `clock` kwarg on `trends()` sets the pattern for how "now" is injected if needed for relative date ranges.

4. **Notification threshold alerts (Phase 3):** The `"scheduled"` trigger type in `AutomationRule` is the natural hook. A scheduled rule with `action_type = "report_threshold"` (a new action type) would: (a) call the report's execution function, (b) compare the result to a threshold value, (c) call `create_notification()` if the threshold is crossed. This requires extending `_KNOWN_ACTION_TYPES` and adding `_execute_report_threshold_action` in `app/services/automations.py`. No new notification pipeline is needed. Guard against double-firing if the metric stays above threshold across multiple polling cycles (one-shot vs. edge-triggered semantics — an open design question for that phase).

5. **`rep` role vs. `admin`/`manager` for report creation:** The current recommendation is admin/manager-only write access. But reps may want personal saved filters (e.g., "show only my deals"). If rep-created reports are allowed, the read scoping in the execution function must enforce that reps can only see their own data regardless of the config_json filter. This is the same scoping pattern as `rep_leaderboard(scope=current_user.id)` in `app/routers/insights.py`. Recommend deferring rep-created reports to Phase 2 and starting with admin/manager-only creation, all-users read.
