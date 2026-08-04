# Directory Factory — Dashboard UX & Workflow Decisions

This document fills the gap the master plan flags in Phase 8 ("see the
separate dashboard design doc") — it's that doc. It answers the UI/UX
questions the plan left open, and captures which of those answers are
genuine recommendations vs. which need Shanon's input because they depend
on real day-to-day workflow that only shows up once the pipeline is
running.

**How to read this doc:** each question has a **Recommendation** (what to
build, and why, consistent with the master plan's "simple by default, no
bells and whistles, local-first" direction) and a **Status** — `Decided`
means build it as recommended, `Open — needs Shanon` means don't build
speculative complexity around it yet; build the simple version and revisit
once real usage shows the actual pattern.

---

## Dashboard & Orchestration UI

### 1. Target devices
**Recommendation:** Desktop-first, not a responsive mobile build.
The whole system is local-first and laptop-bound by design (see the
master plan's architecture decisions) — there's no scenario where this
dashboard is reachable from a phone without deliberately exposing it
beyond `localhost`, which cuts against the no-auth decision below anyway.
Build for a normal desktop browser window. No mobile breakpoints, no touch
target sizing, no mobile confirmation flows for v1.
**Status:** Decided.

### 2. Authentication
**Recommendation:** No login system — but bind the server to
`127.0.0.1` explicitly, not `0.0.0.0`. That's what actually resolves the
security concern: instead of adding auth to a dashboard that's exposed to
the network, don't expose it to the network at all. If remote access is
ever wanted later, that's an SSH tunnel or similar — a separate decision,
not a reason to build auth now.
**Status:** Decided.

### 3. Real-time updates
**Recommendation:** Polling, not WebSocket/SSE. `dataset-collector`
already has a working 3-second polling pattern for exactly this kind of
long-running job — reuse it rather than building streaming infrastructure.
It's good enough UX for jobs that run minutes, not milliseconds, and it's
one dependency-free `setInterval` instead of a new subsystem.
**Status:** Decided.

---

## Directory Detail Page (per-project)

### 4. Pipeline visualization — status only, or status + metrics?
**Recommendation:** Both, but keep it to one headline number per stage.
A status pill alone ("Running") doesn't tell you if it's stuck or just
slow. Since `runs.db` already stores a `counts` JSON per run, surfacing
one number per stage ("1,247 collected", "89% enriched") is close to free
and meaningfully more useful. Don't build a full metrics breakdown per
stage — one pill + one number, that's it.
**Status:** Decided.

### 5. Error handling & retry UX
**Recommendation for v1:** Inline error log (see Q8) + a **re-run whole
stage** button. Skip per-item retry UI for now.
Per-item retry needs real UI machinery — a selectable list with per-record
state — and whether it's worth that cost depends entirely on what your
failures actually look like once this is running: a handful of bad
records that succeed on retry (worth building), vs. a systemic bug that
fails everything the same way (whole-stage re-run is what you need
anyway, per-item retry buys nothing). Build the simple version first; this
is one of the things flagged for you below.
**Status:** Open — needs Shanon, see the workflow question at the bottom.

---

## Config Panel

### 6. `site_config` fields
**Recommendation** — include:
- `site_name`, `tagline`, `niche_label`
- `domain`
- `theme_primary_color`, `theme_secondary_color`
- `logo_url`
- `contact_email`, `contact_phone`
- `social_links` (JSON)
- `legal_privacy_copy`, `legal_terms_copy`
- `og_image_url` (social/OG metadata — cheap to add, directly supports
  the SEO goal already built into the enrichment stage)

**Recommend leaving out:**
- **Default search terms** — that's collection-project metadata, already
  lives in the collector (Phase 1), not site branding. Putting it in
  `site_config` duplicates data that's owned elsewhere.
- **Map provider selection** — hardcode Leaflet/OpenStreetMap across every
  site (same as `dataset-collector` and the reference Astro site already
  use). Making this configurable per-directory adds a real branching cost
  in the template for a choice that has no reason to differ site-to-site.
- **Currency/locale** — every directory is AU/English/AUD right now.
  Adding locale fields for a hypothetical future multi-country expansion
  is speculative complexity the plan explicitly says to avoid. Add it if
  and when there's an actual second country.

**Status:** Decided.

### 7. Live preview scope
**Recommendation:** A lightweight mock preview rendered **inside the
dashboard itself** (its own HTML/CSS showing a hero section with the
chosen logo, colors, site name, and tagline) — not a live Astro dev
server. Spinning up a real Astro build/dev server alongside the Python
dashboard to preview config changes is exactly the kind of infrastructure
the plan says to avoid for a preview that's really just "do these colors
and this copy look right together." A raw JSON dump would satisfy the
letter of "preview" but not the actual point of previewing (checking it
looks good) — the in-dashboard mock is the middle ground: real visual
feedback, no second build system.
**Status:** Decided.

---

## Run History / Logs

### 8. Log detail depth
**Recommendation:** Store and show full stdout/stderr, not just the
summary string. This needs one schema change from the master plan:
add `stdout` and `stderr` TEXT columns to `runs.db` (currently only
`summary`/`error` are captured — expand the runner to store the full
captured output, not just the parsed final JSON line). The Detail page
shows the summary by default, with an expandable "view full log" for
debugging failures. There's no real cost to keeping the full text — SQLite
TEXT columns are cheap — and throwing away the trace is exactly what makes
a failed run hard to debug later.
**Status:** Decided — this is a small addition to Phase 3's `runs.db`
schema in the master plan.

### 9. Run history granularity
**Recommendation:** Paginated history (not capped at 5), with filters by
script type, status, and project — reusing the same filter pattern
`dataset-collector`'s places table already has. Default view: most recent
20, paginated.
**Status:** Decided.

---

## Site Deployment

### 10. Provision Site flow
**Recommendation:** A minimal trigger, not an editable settings form.
Domain name as the one input field (everything else — repo, branch, build
command — stays fixed and standardized across every directory, per the
"one shared template" architecture decision, so there's nothing to
configure per-site). Show the Cloudflare API response/build log inline,
reusing the same log-viewer pattern as Q8/Q9 — it's just another script
run through the standardized runner, so it gets the same UI for free.
**Status:** Decided.

---

## Cross-Cutting Concerns

### 11. "New Directory" wizard
**Recommendation:** Yes — and this is close to a direct port of
`dataset-collector`'s existing "create project" modal (name, search terms,
field tier, search step) plus the directory-specific fields from the
master plan's Phase 1 additions (`directory_name`, `domain`). Fields:
name → auto-generated slug (editable), niche label, target metros
(multi-select, defaults to the 15 AU metros already defined), search terms
(tag input), field tier. No need to design this from scratch — the working
pattern already exists.
**Status:** Decided.

### 12. Places table (filter/search) in the new dashboard
**Recommendation:** In scope — port it, don't rebuild it. This already
exists and works in `dataset-collector` (`/api/projects/{id}/places` with
search + completeness-score filtering). It's directly useful for the
Collect panel (checking what actually got collected before moving to
Clean) and costs nothing new to build since it's a straight port.
**Status:** Decided.

---

# Dashboard UI Design Spec

This is the build spec for Phase 8 — page by page, component by component,
consistent with the decisions above. Where a decision above already
answered something, it's restated here in build-ready form rather than
re-argued.

## Information Architecture

Three top-level routes. No client-side routing framework — plain server-
rendered pages (FastAPI + Jinja2 or static HTML per page) with vanilla JS
for in-page interactivity, matching the rest of the tech stack decision.

```
/                          Overview — grid of directories
/directories/{id}          Directory Detail — tabbed: Collect | Clean | Enrich | Upload | Deploy | Live Stats | Config | Runs
/settings                  Global settings — credentials
```

"New Directory" is a **modal**, not a route — triggered from the Overview
page, matching the existing `dataset-collector` create-project modal
pattern (Q11).

## Global Shell

```
┌────────────────────────────────────────────────────────────────┐
│  Directory Factory          [Overview] [Settings]               │  ← top bar, all pages
├────────────────────────────────────────────────────────────────┤
│                                                                   │
│                        PAGE CONTENT                              │
│                                                                   │
└────────────────────────────────────────────────────────────────┘
```

No sidebar — with only two top-level routes (Overview, Settings) and
everything else nested under a directory, a sidebar is unnecessary chrome.
Top bar: logo/name (left), two nav links (right). That's the entire global
nav. Desktop-only per Q1 — fixed content max-width (~1200px), no responsive
breakpoints.

## Status Pill Legend (used everywhere)

| Stage state | Color |
|---|---|
| Not Started | Grey |
| Running | Blue (pulsing) |
| Done | Teal |
| Error | Red |

Directory-level status (Overview cards) uses the same pills, showing the
*current* stage's state: `Idea` / `Collecting` / `Cleaning` / `Enriching` /
`Uploading` / `Deploying` / `Live` / `Error`.

---

## Page: Overview (`/`)

```
┌────────────────────────────────────────────────────────────────┐
│  Directory Factory                         [Overview][Settings] │
├────────────────────────────────────────────────────────────────┤
│                                            [+ New Directory]     │
│                                                                   │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │ Mobile Dog     │  │ Pest Control   │  │ Laundromat     │       │
│  │ Groomers       │  │                │  │                │       │
│  │ ● Enriching    │  │ ● Live         │  │ ● Collecting   │       │
│  │ ●●●○○○ 3/6      │  │ ●●●●●● 6/6      │  │ ●○○○○○ 1/6      │       │
│  │ 387 places      │  │ 2,060 places    │  │ 865 places      │       │
│  │ Updated 30 Jul  │  │ Updated 30 Jul  │  │ Updated 4 Aug   │       │
│  │ [Run Enrichment]│  │ [View Live ↗]  │  │ [View Progress] │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│  ... (grid continues, wraps at content width)                   │
└────────────────────────────────────────────────────────────────┘
```

**Card contents (fixed set, per Q4):**
- Directory name
- Status pill (current stage)
- 6-dot pipeline stepper: Collect·Clean·Enrich·Upload·Deploy·Live — filled
  dots = done, one pulsing = running, empty = not yet reached
- One headline metric (place count)
- Last updated timestamp
- One primary button, label changes by current stage:
  `Start Collection` / `Run Cleaning` / `Run Enrichment` / `Upload to D1` /
  `Deploy` / `View Live ↗`
- No secondary menu/delete on the card itself — deletion lives on the
  Directory Detail page only, to avoid an accidental click on a dense grid

**Empty state:** if there are zero directories, show a single centered
"+ New Directory" call to action instead of an empty grid.

**"+ New Directory" modal fields (Q11):**
- Name (text input)
- Slug (auto-generated from name, editable)
- Niche label (text input)
- Target metros (multi-select checklist, pre-checked with the 15 default
  AU metros)
- Search terms (tag input — type, press Enter to add a tag)
- Field tier (segmented control: Essentials / Pro / Enterprise, defaults
  to Enterprise)
- `[Cancel]` `[Create Directory]` — on success, redirect to
  `/directories/{new_id}`

---

## Page: Directory Detail (`/directories/{id}`)

```
┌────────────────────────────────────────────────────────────────┐
│  Directory Factory                         [Overview][Settings] │
├────────────────────────────────────────────────────────────────┤
│  ← Mobile Dog Groomers                          [Delete...]      │
│                                                                   │
│  [Collect] [Clean] [Enrich] [Upload] [Deploy] [Live Stats]       │
│  [Config] [Runs]                                                 │
│  ───────────────────────────────────────────────────────────    │
│                                                                   │
│                     (active tab's panel, below)                  │
│                                                                   │
└────────────────────────────────────────────────────────────────┘
```

Tabs, not a scrolling single page — clicking a tab swaps the panel below
(plain JS show/hide, no page reload). The active tab is whichever stage
the directory is currently on by default when the page loads; the user can
click any tab regardless of pipeline position (e.g. to check Collect's
places table while Enrich is running).

`[Delete...]` in the header opens a confirm dialog (see "Confirmation &
destructive actions" below) — the only destructive action in the whole UI.

### Tab: Collect

```
┌─────────────────────────────────────────────┐
│  [● Running]           [Pause]  [Retry Failed]│
│  ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░  62% (291/469 jobs)     │
│                                                │
│  Places: 387   Duplicates skipped: 12   Failed: 2 │
│                                                │
│  🗺  [map with pins]                          │
│                                                │
│  Places  [search: ______]  [min completeness ▾]│
│  ┌────────────────────────────────────────┐  │
│  │ Name | Address | Search Term | Score     │  │
│  │ ...  | ...     | ...         | ...       │  │
│  └────────────────────────────────────────┘  │
│  ‹ 1 2 3 ... 8 ›                              │
│                                                │
│  Recent log ▾ (collapsed by default)          │
└─────────────────────────────────────────────┘
```

Ported directly from `dataset-collector`'s existing project detail page
(Q12) — map, places table with search + completeness filter, pagination,
log feed. `[Retry Failed]` re-runs only failed jobs (this already exists in
the collector — not new build).

### Tab: Clean / Enrich / Upload / Deploy — shared panel shape

These four stages share one layout pattern (Q4, Q5, Q8):

```
┌─────────────────────────────────────────────┐
│  [● Done]                        [Re-run]     │
│  387 places cleaned                            │
│                                                │
│  Last run: 30 Jul 2026, 05:30                  │
│  [View full log ▾]  (collapsed — expands to    │
│   show full stdout/stderr from runs.db)        │
└─────────────────────────────────────────────┘
```

- One status pill + one headline metric (Q4) — no per-item table for v1
  (Q5: whole-stage re-run only, no per-item retry UI yet)
- `[Re-run]` — single click, no confirmation dialog (not destructive,
  just reprocesses)
- `[View full log ▾]` expands inline to show the complete stdout/stderr for
  the most recent run (Q8) — plain `<pre>` block, monospace
- While running: pill shows `● Running`, `[Re-run]` is disabled, panel
  polls every 3 seconds (Q3) until status changes

**Clean-specific addition:** below the shared panel, a small **Feature
Taxonomy** section — a simple tag list of this directory's `feature_key`
values (editable: add/remove/rename), since Phase 2's plan calls for a
per-niche taxonomy that's reviewed before extraction logic runs.

**Deploy-specific addition:** one text input for **Domain** (Q10) above
the `[Re-run]`/`[Deploy]` button — everything else about the deploy (repo,
branch, build command) is fixed and not editable here, per the "one shared
template" decision. Once deployed, show `[View Live Site ↗]` linking to
the domain.

### Tab: Live Stats

Only shows meaningful content once Deploy is `Done`; otherwise shows
"Deploy this directory to see live stats."

```
┌─────────────────────────────────────────────┐
│  Requests: 1,204   Visitors: 389   Cache: 94%│
│                                                │
│  [line chart: visits over time] [7d 30d 90d] │
│                                                │
│  Top pages                                    │
│  ┌────────────────────────────────────────┐  │
│  │ /                    412 visits          │  │
│  │ /nsw/sydney           88 visits          │  │
│  └────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

Pulled live from the Cloudflare Analytics API on page load — no local
storage of stats needed, just a pass-through call.

### Tab: Config

```
┌───────────────────────┬───────────────────────┐
│  FORM                  │  PREVIEW               │
│                         │                        │
│  Site name  [________] │  ┌──────────────────┐  │
│  Tagline    [________] │  │  [logo]  Site Name │  │
│  Niche      [________] │  │  Tagline text      │  │
│  Domain     [________] │  │  ─────────────     │  │
│                         │  │  (mini hero mockup │  │
│  Primary   [🎨 #____]  │  │   in dashboard's   │  │
│  Secondary [🎨 #____]  │  │   own CSS, using   │  │
│  Logo URL  [________]  │  │   the live colors/ │  │
│                         │  │   copy as typed)   │  │
│  Contact email [_____] │  └──────────────────┘  │
│  Contact phone [_____] │                        │
│  Social links  [+ Add] │                        │
│                         │                        │
│  Privacy copy  [______]│                        │
│  Terms copy    [______]│                        │
│  OG image URL  [______]│                        │
│                         │                        │
│  [Save]  Last saved: —  │                        │
└───────────────────────┴───────────────────────┘
```

Field list is exactly Q6's decided `site_config` list. Preview is the
in-dashboard mock described in Q7 — plain HTML/CSS in the dashboard itself
re-rendering live as form fields change (JS `input` event listeners
updating the preview DOM directly, no server round-trip needed for the
preview itself). `[Save]` persists to the directory's D1 `site_config`
table.

### Tab: Runs

```
┌─────────────────────────────────────────────┐
│  Script [All ▾]  Status [All ▾]  [Date range]│
│  ┌────────────────────────────────────────┐  │
│  │ Script         Status   Started    ⌄     │  │
│  │ cleaning.clean Done     05:30      ⌄     │  │
│  │ enrichment.enrich Error 05:41      ⌄     │  │
│  │ ...                                       │  │
│  └────────────────────────────────────────┘  │
│  ‹ 1 2 3 ›                       20 per page  │
└─────────────────────────────────────────────┘
```

Filtered to this directory by default (Q9); each row expands (⌄) to the
full stdout/stderr for that run, same pattern as the per-stage panels'
`[View full log]`.

---

## Page: Settings (`/settings`)

```
┌─────────────────────────────────────────────┐
│  Google Places API Key   [•••••••••] [Test]  │
│  Gemini API Key          [•••••••••] [Test]  │
│  Cloudflare API Token    [•••••••••] [Test]  │
│  Cloudflare Account ID   [__________]         │
│  GitHub Token            [•••••••••] [Test]  │
│                                                │
│  Default field tier   [Enterprise ▾]          │
│  Default grid step    [10 km_____]            │
│                                                │
│  [Save]                                       │
└─────────────────────────────────────────────┘
```

Masked credential fields with a `[Test]` button per field (hits a small
backend endpoint that does a trivial authenticated call and returns
✓/✗ — e.g. Cloudflare token: list accounts; Gemini key: list models).
Values read from/written to `NEW_DIRECTORY_FACTORY_PATH/.env`.

---

## Confirmation & destructive actions

Only **one** confirm dialog in the entire UI: deleting a directory
(`[Delete...]` on the Directory Detail page). Everything else — re-running
a stage, triggering a deploy, saving config — is a single click with a
toast notification on completion. Keeping confirmation dialogs rare means
the one that exists is meaningful, rather than training the user to
click through them reflexively.

```
Delete "Mobile Dog Groomers"?
This removes the directory's data from the dashboard. It does not delete
the live Cloudflare Pages site or D1 database — those are removed
separately via Cloudflare directly.
[Cancel]  [Delete]
```

## Toasts

Bottom-right, auto-dismiss after ~4 seconds: success (teal), error (red).
Every stage run, save action, and deploy trigger produces exactly one
toast on completion — this is the only "did that work?" signal beyond the
pill/log, so it should never be skipped.

---

## Backing API (what the frontend actually calls)

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/directories` | Overview grid data |
| `POST` | `/api/directories` | New Directory wizard submit |
| `GET` | `/api/directories/{id}` | Directory Detail header + current stage |
| `DELETE` | `/api/directories/{id}` | Delete (after confirm) |
| `POST` | `/api/directories/{id}/run` | Body: `{script_name, params}` — triggers via `runner/run.py`, returns immediately with a run ID |
| `GET` | `/api/directories/{id}/places?search=&min_completeness=&page=` | Collect tab table |
| `GET` | `/api/runs?project_id=&script_name=&status=&page=` | Runs tab, paginated + filtered |
| `GET` | `/api/runs/{run_id}` | Full stdout/stderr for one run (expand row / "View full log") |
| `GET` | `/api/directories/{id}/config` | Config tab load |
| `PUT` | `/api/directories/{id}/config` | Config tab save |
| `GET` | `/api/directories/{id}/live-stats` | Live Stats tab (pass-through to Cloudflare Analytics API) |
| `GET` / `PUT` | `/api/settings` | Settings page |
| `POST` | `/api/settings/test/{credential}` | Settings page `[Test]` buttons |

Every panel that shows a running/pending status polls
`GET /api/directories/{id}` or `GET /api/runs/{run_id}` every 3 seconds
while status is `running`, and stops polling once it isn't (Q3).

---

## Visual Style

- **Typography:** system font stack (`-apple-system, "Segoe UI", sans-serif`)
  — no font loading, no CDN dependency, consistent with a local-only tool
- **Colors:** white content area, one accent color (blue) for primary
  buttons/links, status pill palette as defined above
- **Layout:** cards and panels with 8px corner radius, subtle border
  instead of heavy shadows (simpler to implement in plain CSS, still reads
  as clean)
- **No icon library dependency** — text labels and a small set of inline
  SVGs (checkmark, pulsing dot, chevron) rather than pulling in an icon
  font/package

---

## Open Question for Shanon

Everything above is buildable as a sensible default. One thing genuinely
isn't a UX decision I can make for you — it's a workflow fact only visible
once the pipeline's actually running:

> **When a stage fails partway (especially enrichment), what does that
> failure usually look like in practice?** A few individual bad records
> that would succeed if retried alone — or something systemic that fails
> the same way across the board, where re-running the whole stage is the
> only thing that actually helps?

This directly decides Q5 (whether per-item retry UI is worth building) and
has a secondary effect on Q9 (how much you'll want to filter run history by
failure type). Cheapest path: ship the "re-run whole stage" version first,
watch what actually happens across the first couple of directories, then
come back and build per-item retry only if the failure pattern actually
calls for it.
