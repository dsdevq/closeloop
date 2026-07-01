---
title: CRM domain brief + v1-v6 thinking
status: stable
owner: "@dsdevq"
last_reviewed: 2026-07-01
tags: [product, domain, crm]
---

# CloseLoop — CRM Domain Reference & Roadmap

> **Audience:** Denys (product owner) and AI agents working on CloseLoop.
> **Purpose:** (A) A domain best-practices brief for CRM software. (B) An honest assessment of CloseLoop's current state and a proposed versioned roadmap.
>
> *This is a PROPOSAL. Denys should veto or steer any version's scope before implementation begins.*

---

## Table of Contents

1. [Part A — CRM Domain Best Practices](#part-a--crm-domain-best-practices)
   - [Standard Data Model](#1-standard-data-model)
   - [Pipeline & Customizable Stages](#2-pipeline--customizable-stages)
   - [User Roles & Permissions](#3-user-roles--permissions)
   - [Activity Timeline](#4-activity-timeline)
   - [Tasks & Reminders](#5-tasks--reminders)
   - [Email & Calendar Integration](#6-email--calendar-integration)
   - [Reporting, Dashboards & Forecasting](#7-reporting-dashboards--forecasting)
   - [Automations & Workflows](#8-automations--workflows)
   - [Import & Export](#9-import--export)
   - [Search & Advanced Filtering](#10-search--advanced-filtering)
   - [Audit Log](#11-audit-log)
   - [Notifications](#12-notifications)
   - [Table-Stakes vs Differentiators](#13-table-stakes-vs-differentiators)
   - [Survey of Real CRMs](#14-survey-of-real-crms)
2. [Part B — CloseLoop Assessment & Roadmap](#part-b--closeloop-assessment--roadmap)
   - [Honest MVP Assessment](#1-honest-mvp-assessment)
   - [Gap Analysis](#2-gap-analysis)
   - [Proposed Versioned Roadmap](#3-proposed-versioned-roadmap)

---

# Part A — CRM Domain Best Practices

## 1. Standard Data Model

A well-designed CRM centers around these core entities and their relationships:

### Leads
A pre-qualified prospect — someone who has expressed interest but hasn't been vetted yet. In some CRMs (Salesforce, Zoho), leads are a distinct entity that gets "converted" into a contact + account + deal. In others (HubSpot, Pipedrive), there is no lead/contact distinction — contacts just have a lifecycle stage. The distinction matters most in B2B teams where SDRs qualify leads before handing off to AEs.

**Key fields:** name, email, phone, company (plain text), source, assigned rep, status (new/working/qualified/unqualified), created date.

### Contacts
A qualified individual. The anchor entity most activity attaches to. In B2B, a contact belongs to an account (company).

**Key fields:** name, email, phone, title, company/account (FK), source, owner/assignee, tags, created/updated timestamps, last-activity date.

### Accounts / Companies
The organization — critical for B2B. An account has many contacts. Deals are associated with accounts (and optionally a specific contact within the account). This layer enables "relationship view" across everyone at a company.

**Key fields:** company name, domain, industry, size, address, website, owner, ARR/tier, tags.

### Deals / Opportunities
A revenue opportunity with a lifecycle (pipeline stage). Each deal has a value, expected close date, probability, and owner. A contact (or account) can have many open deals simultaneously.

**Key fields:** title, value/amount, currency, stage, probability, expected close date, owner, contact_id / account_id, source, created/closed timestamps, tags.

### Activities
Historical log of interactions — calls made, emails sent, meetings held. Activities record *what happened*.

**Key fields:** type (call/email/meeting/demo/note), subject, body/notes, duration, outcome, linked contact/deal/account, created by, timestamp.

### Notes
Freeform text attached to any entity — often a subtype of activities but sometimes kept separate for rich-text, @mentions, and pinning.

### Tasks
Future actions assigned to a rep with a due date and priority. Tasks record *what needs to happen*. Unlike activities, tasks have a completion state and are the engine of the daily follow-up workflow.

**Key fields:** title, description, type, due date, priority (high/medium/low), assignee, linked entity, completed_at.

---

## 2. Pipeline & Customizable Stages

### What best-in-class looks like

**Customizable stages per pipeline.** Reps should be able to rename, add, remove, and reorder stages. Default probability per stage is editable. Enterprise users need multiple independent pipelines (e.g., New Business vs. Renewal vs. Partner).

**Visual kanban + list toggle.** Kanban for deal progression overview; list view for bulk operations and sorting.

**Stage-level SLA thresholds.** Each stage has a configurable SLA. Deals exceeding it are flagged as "rotting." This is deal-specific, not global.

**Stage entry/exit requirements.** Best-in-class CRMs allow requiring specific fields to be filled before a deal can advance (e.g., company must be set before moving to Proposal). Prevents dirty data from creeping forward.

**Probability auto-set from stage, overridable per deal.** The stage sets a default probability, but reps can override it for deals they have special knowledge about.

**Won/Lost as terminal stages.** Won and Lost exit the active pipeline and feed the win-rate and revenue analytics. Lost reason is a required field on closing.

**Automation triggers on stage change.** Moving a deal from Proposal to Negotiation can auto-create a task ("Send revised pricing"), send an email, or notify a manager.

---

## 3. User Roles & Permissions

### Standard three-tier model

| Role | Typical access |
|------|---------------|
| **Admin** | Everything: user management, global settings, all records, all reports, billing |
| **Manager** | View and edit all records within their team, team reports, cannot manage other users |
| **Sales Rep** | Create and manage their own records; limited or no visibility into other reps' deals |

### Common permission patterns

- **Ownership-based visibility:** Reps see only the records where they are the owner. Managers see their direct reports' records. Admins see everything.
- **Team-based visibility:** Records belong to a team; all team members can see team records.
- **Shared records:** Any record can be explicitly shared to another user or team.
- **Field-level permissions:** Sensitive fields (e.g., deal value, commission info) hidden from reps but visible to managers.

### Multi-user teams
- **Round-robin assignment:** New inbound leads auto-assigned in rotation across a team.
- **Territory rules:** Assignment by geography, industry, or deal size.
- **Manager hierarchy:** Manager can reassign deals from their reports; admins can reassign anything.

---

## 4. Activity Timeline

The activity timeline is the "relationship memory" — a unified, reverse-chronological stream of every interaction with a contact or deal.

**What it shows:** Activities (calls/emails/meetings), notes, task completions, stage changes, and (with integration) automatically pulled email threads and calendar meetings.

**Filtering:** By type (email, call, meeting, note), by date range, by author.

**Pinned notes:** Important context (e.g., "Champion left company") pinned to the top so it's never buried.

**@mentions in notes:** Tag a teammate to notify them and link them to the record.

**Auto-logged items (with integrations):** Inbound/outbound emails auto-appear in the timeline via email sync. Scheduled/completed calendar meetings appear automatically.

**Stage transitions:** Each pipeline stage move appears in the timeline as an event with timestamp, actor, and optional note.

The timeline transforms a CRM from a database into a conversation history — it answers "what happened last time?" in one scroll.

---

## 5. Tasks & Reminders

### Daily follow-up workflow

The task/reminder system is what separates a CRM from a spreadsheet. Best-in-class systems give every rep a clean "My day" view: tasks due today, overdue items, and upcoming deadlines in one ordered queue.

**Task features:**
- Create tasks linked to a contact, deal, or account
- Assign to self or a teammate
- Due date + time, priority (high/medium/low)
- Task types (call, email, follow-up, send document, etc.)
- Mark complete (optionally capturing an outcome or next task)
- Reschedule / snooze
- Bulk complete/reassign
- Recurring tasks (daily/weekly/monthly)

**Reminder features:**
- Standalone reminders (not attached to a task/activity)
- Browser push notifications + email digest
- Overdue escalation (notify manager when rep has 5+ overdue tasks)

**"Today" queue design pattern:**
A dedicated view showing:
1. Overdue tasks (sorted by oldest first)
2. Tasks due today (sorted by priority)
3. Upcoming tasks (next 7 days, collapsed)

Reps who live in this view consistently outperform those who don't — it's the daily compass.

---

## 6. Email & Calendar Integration

### Email integration patterns

| Pattern | Description | Complexity |
|---------|-------------|------------|
| **BCC address** | Rep BCCs a unique address to log email in CRM | Low — no OAuth |
| **Chrome extension** | Sidebar in Gmail/Outlook shows CRM context | Medium |
| **OAuth two-way sync** | Full inbox sync — emails auto-matched to contacts by address | High |
| **Sequences / cadences** | Automated multi-step email outreach with reply detection | High |

Best-in-class: two-way OAuth sync (Gmail/Outlook). Emails auto-associate to contacts via From/To matching. Compose from within the CRM. Track opens, clicks, and replies.

### Calendar integration patterns

- **Sync meeting events:** Google Calendar / Outlook Calendar meetings appear as activities on the deal.
- **Scheduling link:** Share a booking page (Calendly-style) that auto-logs the meeting when booked.
- **Meeting outcome capture:** After a synced meeting, CRM prompts for notes and next task.

### CloseLoop's current approach

CloseLoop's `outbox` table is a deliberate stub — "send" means insert a queued row, never open a socket. This is the right boundary for a self-hosted MVP. Real integration would require OAuth, a sync worker, and credentials management — genuine scope creep until the product has real users.

---

## 7. Reporting, Dashboards & Forecasting

### Pipeline funnel
A visual funnel (or bar chart) showing deals count and total value at each stage. The key metric: *where do deals drop off?* A funnel where 80% of deals die at Proposal signals a pricing or timing problem.

### Conversion rates
Stage-to-stage conversion percentages. Lead → Qualified: 40%. Qualified → Proposal: 60%. Proposal → Won: 35%. Trended over time to spot coaching opportunities.

### Revenue forecast
**Weighted pipeline:** `Σ(open deal value × stage probability)`. This is CloseLoop's current implementation — correct for small teams.

**Scenario modeling:** Best/expected/worst case probability maps applied to the same pipeline. Lets managers give a range rather than a point estimate to execs.

**Commit/Upside:** Advanced pattern (Salesforce, Close.com) where reps flag individual deals as "committed to close" vs "upside" — enables manager rollup forecasting.

### Activity leaderboard
Who's making calls, sending emails, completing tasks — ranked per rep. The key coaching tool: low activity usually predicts low attainment before the quarter ends. Shows: calls this week, emails sent, meetings held, tasks completed.

### Win/loss analytics
- Win rate by rep, by source, by deal size bucket, by industry
- Average days-to-close by stage and won/lost
- Lost reason breakdown (price, timing, competition, no decision)
- Deals created vs closed by period (cohort view)

### Deal velocity dashboard
Average time-per-stage across won deals. Highlights bottlenecks: if deals average 5 days in Proposal but 28 days in Negotiation, that's where to focus.

---

## 8. Automations & Workflows

The automation engine is a major differentiator. The basic model is **Trigger → Condition → Action**.

### Triggers
- Record created (new contact, new deal)
- Field changes (stage changed, owner changed, value increased above $X)
- Time-based (deal in stage for N days, task overdue by N days)
- Activity completed (call logged, email sent)

### Actions
- Create a task (assigned to rep, manager, or round-robin)
- Send an email (from a template)
- Update a field (set a tag, change owner, update status)
- Send a notification (in-app, email, Slack)
- Create a deal (e.g., "won deal → create renewal deal 11 months later")
- Move to next stage

### Common workflow examples
- "New inbound lead → assign to next rep in rotation → create task 'Call within 2 hours'"
- "Deal in Proposal for > 7 days → notify manager + create task 'Check in with prospect'"
- "Deal marked Won → send congratulations email + create task 'Send onboarding doc'"
- "Task overdue by 3 days → @mention manager"

Automations convert a CRM from a logging tool into a coaching and enforcement engine.

---

## 9. Import & Export

### Import (CSV/Excel)
**Field mapping UI:** User uploads a file, then maps each source column to a CRM field. This is table-stakes — without it, CSV upload is painful.

**Duplicate detection:** Before insert, match incoming rows against existing contacts by email or name. Options: skip duplicate, update existing, or create anyway.

**Row-level error reporting:** Don't reject the whole file for one bad row. Report which rows failed and why; import the rest.

**Required field validation:** Fail fast on missing required fields per row.

### Export
- Export the current view/filter as CSV (not just all records)
- Include related data in one row (e.g., deal export includes contact name, email, company)
- Export history/activities for a contact
- Full database export for backup

### API for programmatic access
For teams with engineering resources: REST API endpoints for all entities enable Zapier/Make.com integrations and custom ETL pipelines without CSV overhead.

---

## 10. Search & Advanced Filtering

### Global full-text search
Table-stakes: type a name, company, or deal title and get results across all entities instantly. Without this, reps are stuck navigating to a list and scrolling.

### Quick filters
One-click filters from the list view: by owner, by stage, by tag, by date range. Essential for "show me all my deals in Proposal" without building a filter expression.

### Advanced filter builder
A UI that maps to the filter AST — AND/OR groups with field/operator/value leaves. Allows complex queries like:
> `(stage = Proposal OR stage = Negotiation) AND value > $50,000 AND last_activity_date < 14 days ago AND owner = me`

### Saved views
Named, persisted filter + sort combinations. Can be private (mine) or shared (team). Essential for manager dashboards ("Stale deals > $50k") and rep daily workflows ("My Proposals").

### Filter by activity recency
A critical CRM-specific filter: "contacts with no activity in the last 30 days." This is harder than it looks — requires joining through activities and doing a NOT EXISTS or MAX(activity date) < threshold query.

---

## 11. Audit Log

### What to capture
- Every create, update, delete on every record
- Field-level changes: `{field: "stage", old: "proposal", new: "negotiation", actor: "alex@co.com", ts: "..."}`
- Stage transition history (dedicated table — CloseLoop already has `stage_transitions`)
- User authentication events (login, logout, failed login) — *requires auth first*
- Configuration changes (stage renamed, user role changed)

### How it's used
- Compliance ("who deleted that contact?")
- Debugging ("why did this deal's value change?")
- Dispute resolution between reps and managers
- Reconstruction after accidental deletions

### Table-stakes minimum
Field-level change log accessible per-record ("History" tab on deal/contact page). Full export for admins.

---

## 12. Notifications

### In-app notification center
A bell icon with unread count. Notifications include:
- Task overdue (yours)
- @mention in a note (you were mentioned)
- Stage change on a deal you own or watch
- New deal assigned to you

### Email notifications
- Daily digest: overdue tasks + tasks due today
- Immediate alert for high-priority events (@mention, deal assigned)
- Weekly summary: pipeline snapshot, activity count, tasks completed

### Push notifications (web/mobile)
- Browser push for overdue tasks
- Mobile push for urgent alerts (manager configurable)

### Notification preferences
Users should be able to configure: which events trigger what channel (in-app / email / push). The default should be conservative — too many notifications trains users to ignore them.

---

## 13. Table-Stakes vs Differentiators

### Table-stakes (must-have; users will not choose a CRM without these)

| Feature | Why it's table-stakes |
|---------|----------------------|
| Contacts + Deals CRUD | The minimal CRM definition |
| Pipeline kanban view | Visual deal management |
| Activity logging | Relationship memory |
| CSV import | Onboarding from spreadsheets |
| CSV export | Data portability / no lock-in |
| Global search | Can't work without it |
| Basic reporting (pipeline value, deals by stage) | Weekly review |
| User roles (admin / rep) | Any team use requires access control |
| Overdue task queue | Daily workflow driver |
| Mobile-readable UI | Reps work on phones |
| API / OpenAPI docs | Technical buyers require it |

### Differentiators (where CRMs compete and win)

| Feature | Who it matters to |
|---------|------------------|
| Email + calendar two-way sync | Teams where email IS the CRM workflow |
| Automation / workflow engine | Operations-heavy teams; removes manual work |
| AI features (next-best-action, email drafts, lead scoring) | Teams wanting to scale without headcount |
| Customizable objects and fields | Complex sales processes that don't fit the standard model |
| Forecasting sophistication (commit/upside, weighted, scenarios) | Sales leaders presenting to executives |
| Territory and round-robin assignment | Growing teams with routing needs |
| Inline calling (VOIP dialer built in) | Inside sales / SDR teams |
| LinkedIn / enrichment integration | Account-based sales and recruiting |
| UX simplicity | Adoption — the CRM reps actually use |
| Price-per-seat | SMBs deciding between tools |
| Self-hostability / data residency | Privacy-conscious buyers |

---

## 14. Survey of Real CRMs

> *Note: Feature claims below are based on knowledge through August 2025. Verify specific pricing, feature gating, and recent launches directly on each vendor's site before using in competitive positioning.*

### Salesforce Sales Cloud
**Best at:** Enterprise customization. Custom objects, custom fields, custom validation rules, custom UI via Lightning components. Largest third-party app marketplace (AppExchange). Einstein AI (lead scoring, opportunity forecasting, email generation). Deep compliance tooling.

**Where it struggles:** Complexity. A fresh Salesforce instance requires a certified admin to configure. Price is prohibitive for small teams. UX is dense.

**Best for:** Mid-market to enterprise teams with a dedicated RevOps function.

---

### HubSpot CRM
**Best at:** Marketing + CRM integration. If you run email marketing, landing pages, and content marketing alongside sales, HubSpot is the only platform where these are natively unified. Generous free tier — contacts/deals/activities are free; power features are gated. Sequences and workflows are best-in-class for SMB.

**Where it struggles:** Pricing escalates sharply once you need pro/enterprise features. Contact-based pricing model penalizes list growth.

**Best for:** SMB to mid-market teams that generate leads through inbound marketing. Agencies and SaaS companies.

---

### Pipedrive
**Best at:** Pipeline UX. The kanban board is the best-designed in the industry — fast, clean, drag-and-drop at scale. Deliberately simple: the tool does one thing (manage a sales pipeline) and does it well. Fast to set up and onboard.

**Where it struggles:** Limited reporting depth. Marketing features are bolt-ons. No built-in calling.

**Best for:** Small sales teams (2–20 reps) who want a clean pipeline tool without the overhead of HubSpot or Salesforce.

---

### Close.com
**Best at:** Inside sales velocity. Built-in VOIP calling with a power dialer, built-in SMS, email sequences, and two-way email sync — all in one screen. Activity metrics and leaderboards are the best in class for SDR/BDR teams. Very fast.

**Where it struggles:** No marketing layer. Less customizable than Salesforce. Priced for teams, not individuals.

**Best for:** Inside sales teams (SDR/BDR/AE) whose primary outreach channel is phone and email. Series A–C SaaS companies with dedicated sales headcount.

---

### Attio
**Best at:** Flexible data model and modern UX. Attio lets you define custom objects and relationships rather than forcing everything into Contacts/Companies/Deals. Strong collaboration and team presence features (see who's viewing a record). Beautiful, fast UI. Strong API.

**Where it struggles:** Newer product — fewer native integrations than HubSpot or Salesforce. Less mature workflow engine. Smaller community.

**Best for:** Technical teams and startups who want to build a custom CRM-like system on top of a flexible platform, or teams who hate rigid traditional CRM schemas.

---

### Zoho CRM
**Best at:** Feature breadth at a lower price point. Zoho has a full-stack (CRM + email + desk + books + projects) that integrates within the Zoho ecosystem. Zia (AI assistant) provides anomaly detection, sentiment analysis, and next-best-time suggestions. Strong workflow automation.

**Where it struggles:** UX is inconsistent across modules. Can feel overwhelming. Quality of Zoho-to-non-Zoho integrations is variable.

**Best for:** SMBs who want a full business suite and are cost-sensitive. Companies already in the Zoho ecosystem.

---

### Folk
**Best at:** Relationship-first CRM for networkers, investors, and recruiters. LinkedIn integration for auto-populating contact data. Magic Fields (AI-generated enrichment). Team collaboration on shared contact lists. Lightweight and fast to set up.

**Where it struggles:** Not designed for a linear sales pipeline. No deal/opportunity model. No forecasting. Better for relationship management than deal tracking.

**Best for:** VCs, investors, recruiters, founders doing partnership or community development. Not for traditional B2B sales pipelines.

---

# Part B — CloseLoop Assessment & Roadmap

## 1. Honest MVP Assessment

CloseLoop has completed M1–M5 (all five milestones + all 8 post-MVP features from the PRD). The engineering foundation is solid, but the product is pre-market by any real CRM standard. Here's an honest inventory:

### What exists and works well

| Component | State |
|-----------|-------|
| Backend API (FastAPI + SQLite) | Solid. Clean router structure, well-tested core logic. |
| Data model: contacts, deals, activities, reminders | Functional. |
| Stage state machine | Well-implemented. Terminal stage enforcement, transition audit log. |
| Weighted pipeline forecast (weighted + scenarios) | Good. Best/expected/worst scenarios. Custom overrides. |
| Lead score (v1 + v2 with decay) | Sophisticated for an MVP. Configurable weights, temporal decay. |
| Filter AST + saved views | Functionally correct. Applied in-process (not SQL push-down). |
| Tags (many-to-many) | Implemented. |
| Activity recurrence (RRULE-lite) | Implemented for daily/weekly/monthly. |
| Deal-rotting alerts (per-stage SLAs) | Implemented. |
| Outbox (stub email queue) | Queue-only — correct boundary for MVP. |
| CSV import/export (contacts + deals) | Row-level error reporting. |
| Stats dashboard | Pipeline value, deals by stage, activity counts. |
| Test suite | Strong on core logic (pure functions). API tests exist. |

### What is missing or underdeveloped

| Gap | Severity |
|-----|----------|
| **No authentication** | Critical — the app cannot be used by a team |
| **No user roles or ownership** | Critical — no access control, no per-rep reporting |
| **No Accounts/Companies entity** | High — B2B contacts without a company hierarchy is painful |
| **Fixed pipeline stages** (no user customization) | High — first thing real users ask for |
| **No global full-text search** | High — table-stakes |
| **No unified activity timeline per record** | High — activities exist but aren't surfaced as a timeline on contact/deal pages |
| **Single-file HTML UI** | Medium — functional but brittle; UX quality is low |
| **No @mentions, no notification center** | Medium — collaboration requires identity first |
| **Audit log is basic** (event_log) | Medium — exists but no field-level change tracking |
| **Import has no field-mapping UI** | Low — JSON body import is developer-friendly but user-hostile |
| **No mobile-responsive UI** | Low for self-hosted; blocks any external deployment |
| **No automation/workflow engine** | Low — genuinely post-MVP feature |
| **No email/calendar sync** | Out of scope for self-hosted MVP (intentionally) |

---

## 2. Gap Analysis

Mapping CloseLoop's current state against Part A's best-practices:

| Domain area | Part A standard | CloseLoop current | Gap |
|-------------|-----------------|-------------------|-----|
| Data model — Leads | Leads as distinct entity or lifecycle stage | No leads concept; contacts cover both | Leads → contacts conversion flow missing |
| Data model — Accounts | Companies as first-class entity with N contacts | Company is a plain text field on Contact | No Account entity; no account-level deal view |
| Data model — Deals | Deal → Account → Contact hierarchy | Deal → Contact only | Missing account layer |
| Pipeline | Configurable stages per pipeline | 6 hardcoded stages | No customization |
| Multiple pipelines | Separate pipelines per product/team | Single pipeline | Not supported |
| User roles | Admin / Manager / Rep with ownership | No auth, no roles, single user | Entire layer missing |
| Activity timeline | Unified per-record stream | Activities list exists; no timeline view in UI | UI-level gap |
| Tasks | First-class tasks with priority/assignee | Activities with `due_at` and a Today queue | Functional but no priority, no assignee |
| Email integration | Two-way OAuth sync | Stub outbox only | Intentionally out of scope |
| Global search | Full-text across all entities | Filter AST on list views only | No cross-entity search |
| Reporting — conversion rates | Stage-to-stage conversion % | Not implemented | Gap |
| Reporting — activity leaderboard | Per-rep activity counts | Aggregate counts only; no per-user breakdown | Gap (requires auth) |
| Reporting — win rates | By rep, source, size | Not implemented | Gap |
| Automations | Trigger → Condition → Action engine | None | Intentionally post-MVP |
| Import — field mapping | UI-driven column → field mapping | JSON body with fixed column names | UX gap |
| Import — deduplication | Match by email, skip/merge | No dedup | Gap |
| Audit log — field-level changes | Old value → new value per field | `event_log` has verbs but not field diffs | Gap |
| Notifications | In-app center, email digest, @mentions | Basic outbox digest; no notification center | Gap |
| Mobile UI | Responsive design | Single-file HTML, not mobile-optimized | Gap |

---

## 3. Proposed Versioned Roadmap

> **PROPOSAL for Denys to veto or steer.** Version order reflects value-per-effort and dependency chains. No version should begin until Denys approves its scope.

---

### v1 — Auth + User Roles

**What it delivers:**
- Username/password login with session tokens (JWT or cookie-based)
- Three roles: Admin, Manager, Sales Rep
- Record ownership: every contact/deal/activity has an `owner_id` FK to a users table
- Access control: reps see their own records; managers see their team's; admins see all
- Basic user management UI for admins (create/invite/deactivate users, assign roles)
- `actor` in `event_log` populated from authenticated user (not a static string)

**Why at this priority:**
Auth is the foundation everything else depends on. Without it: no per-rep reporting (v5), no notification recipients (v6), no meaningful audit log, no team use at all. Building ownership into the data model now avoids a painful retrofit later.

**What it unblocks:**
Every subsequent version. Especially: v2 (ownership-filtered records), v5 (per-rep dashboards), v6 (notification recipients, meaningful audit actor).

**Scope boundary:**
No OAuth, no SSO, no MFA in v1. Local username/password only. Keep it simple — complexity compounds here fast.

---

### v2 — Accounts Layer + Global Search

**What it delivers:**
- `accounts` table as a first-class entity (company name, domain, industry, website, owner)
- Contacts linked to accounts (FK, nullable for B2C contacts)
- Deals linked to accounts (FK, nullable)
- Account detail page: contact list + deal list + activity timeline for the company
- Global full-text search across contacts, accounts, deals (search bar in header)
- Improved filtering: quick-filter by owner, tag, date range from list views

**Why at this priority:**
B2B use is impossible without an Accounts entity — "company" as a free-text field on contacts breaks as soon as you have two contacts at the same company. Global search is table-stakes; users should be able to type a name and find a record without knowing which entity type it is. Both of these are high-value, pre-revenue-impact gaps.

**What it unblocks:**
v3 (deals attach to accounts, not just contacts), v5 (account-level revenue rollup reporting), v6 (account-level import dedup).

---

### v3 — Customizable Pipeline + Kanban UX Quality Pass

**What it delivers:**
- `pipeline_stages` table replacing the hardcoded enum — users can add/rename/reorder/delete stages
- Default probability per stage (editable)
- Stage-entry requirements: optional required-field list per stage (e.g., "amount must be set before Proposal")
- Improved kanban UI: stage header shows count + total value; deal cards show owner avatar, close date, lead score
- Lost reason field (required on Won/Lost)
- Basic "multiple pipelines" support (optional — scope with Denys)

**Why at this priority:**
The hardcoded 6-stage pipeline is the feature most likely to cause a real user to stop using the app. Every sales team has a slightly different vocabulary and process. Stage customization is the minimum to support a second customer. Building this on top of auth (v1) and accounts (v2) means stages can be scoped per-team if needed later.

**What it unblocks:**
v5 (per-pipeline funnel report). The UX pass here is intentionally bundled — stage customization requires a UI for managing stages anyway, and that's the natural moment to raise the bar on the overall pipeline view.

---

### v4 — Activity Timeline + Tasks (First-Class)

**What it delivers:**
- **Unified activity timeline** per contact, deal, and account: all activities, notes, stage changes, and task completions shown in reverse-chronological order with type icons
- **Tasks as first-class objects** (separate from activities): title, due date, priority (high/medium/low), assignee (FK to users, v1 required), linked entity, completed_at, notes
- Improved Today queue: tasks by priority + due time, not just reminders
- @mention support in notes (tags a user, links to notification in v6)
- Task reassignment and bulk operations (complete/reschedule selected tasks)
- Recurring tasks (daily/weekly/monthly — reuse existing `recurrence.py`)

**Why at this priority:**
The activity timeline is the "relationship memory" that justifies using a CRM over a spreadsheet. Without a good timeline, reps don't have context when a prospect calls back. Tasks-as-first-class objects (vs. activities-with-due_at) are necessary for the priority/assignee workflow that managers need. This also sets up v6's notification system: @mentions and overdue tasks need a recipient model first.

**What it unblocks:**
v6 (notification triggers: @mentions, overdue tasks, stage-change watches). Also dramatically improves daily usability before we invest in reporting.

---

### v5 — Dashboards + Reporting

**What it delivers:**
- **Pipeline funnel:** Visual funnel chart — deal count and value at each stage; stage-to-stage conversion rates
- **Revenue forecast:** Weighted pipeline (existing), scenario view (existing), plus commit/upside flags per deal
- **Activity leaderboard:** Per-rep table — calls logged, emails sent, tasks completed this week/month (requires v1 auth)
- **Win/loss analytics:** Win rate by rep, by source, by deal size bucket; lost reason breakdown (requires v3 lost reasons)
- **Deal velocity dashboard:** Average time-per-stage across won deals; highlight the bottleneck stage
- **Account-level reporting:** Total pipeline value per account; number of open deals per account (requires v2 accounts)
- Custom date ranges on all reports

**Why at this priority:**
Reporting is high-value but highly dependent on prior versions — it requires: authenticated users (v1) for per-rep breakdowns, accounts (v2) for account-level rollup, and customizable stages (v3) for per-pipeline funnel. Implementing it here means every report is immediately useful with real data.

**What it unblocks:**
Executive/manager adoption. The activity leaderboard is also the primary coaching tool — managers need it to justify the CRM to their teams.

---

### v6 — Import/Export Polish + Notifications + Audit Log

**What it delivers:**

**Import/Export:**
- CSV import with a field-mapping UI (map source column → CRM field, preview first 5 rows)
- Duplicate detection on import (match by email; options: skip / update / create anyway)
- Export any filtered view as CSV (not just all records)
- Export with related fields in one row (deal export includes contact name, email, account name)

**Notifications:**
- In-app notification center (bell icon + unread count)
- Notification types: @mention, task overdue, new deal assigned, stage change on watched deal
- Email digest: daily overdue + due-today summary (upgrade from current outbox stub)
- User-configurable notification preferences (in-app / email / push per event type)

**Audit Log:**
- Field-level change tracking on all entity updates (old_value → new_value per field)
- Per-record "History" tab in the UI
- Admin-accessible full audit log with export
- Authentication events (login, logout, failed attempts) — requires v1

**Why at this priority:**
These are polish and trust features. Import/export is critical for onboarding and migration (and currently works but is developer-hostile). Notifications make the CRM "alive" — the app reaches out to users rather than waiting for them to come back. The audit log is a compliance and trust feature that enterprise buyers require. All three depend on auth (v1) for meaningful actor attribution. They don't unblock further product development but do unlock enterprise sales conversations.

---

### Dependency map

```
v1 (Auth)
 └─ v2 (Accounts + Search)
     └─ v3 (Pipeline customization)
         └─ v4 (Timeline + Tasks)
             └─ v5 (Reporting)
                 └─ v6 (Import polish + Notifications + Audit)
```

Each version is shippable as a standalone release. The stack is deliberately linear — parallelizing would create merge complexity and data model conflicts between versions.

---

### UX quality pass

The current single-file `index.html` approach will not survive past v3 without becoming unmaintainable. A dedicated UX pass is recommended **before or during v3** to:
- Split the frontend into modular files (still vanilla JS, no build step required)
- Establish a consistent design system (spacing, color tokens, component patterns)
- Make the UI mobile-responsive
- Improve error states, loading states, and empty states throughout

This is not a separate version but a constraint on v3's implementation scope.

---

*Document written 2026-06-23. Propose to review and update after v1 ships.*
