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
**Recommendation (revised):** Mobile-first, not desktop-first — reversed
from the original recommendation. Primary usage is confirmed to be a phone
browser over Tailscale, not the laptop directly. Base styles should target
a narrow viewport (~360-430px) by default; wider layouts are an enhancement
layered on top via a single breakpoint, not the other way around. One
breakpoint at `768px` — below it, mobile layout rules (see "Mobile Layout"
under Global Shell); at or above it, the wider desktop layout already
built. Touch target sizing matters now (44px minimum), and any element
that doesn't reflow at narrow widths (fixed-width cards, non-wrapping flex
rows) is a bug, not a style choice.
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
## Information Architecture — reconciled with the actual build

Hermes built a sidebar (Overview, Directories, Pipeline, Deploy, Live
Stats, Config, Settings) rather than the two-link top bar originally
recommended here. That's fine — not worth a rebuild over — but two things
need scoping down so it stays "simple, useful" rather than turning into
seven separately-built feature areas:

- **Drop the separate "Directories" nav item.** It would show the same
  grid as Overview (a list of directories) — Overview already has the
  grid/list view toggle for exactly this. Keeping both means either two
  pages showing the same thing, or building a second thing that isn't
  needed. Overview *is* the directories list.
- **"Pipeline" and "Deploy" are filtered views of the Overview grid, not
  new pages.** "Pipeline" = the same directory cards, sorted/grouped by
  current stage instead of last-updated. "Deploy" = the same cards,
  filtered to directories at Upload-complete-or-later. Don't build
  separate data-fetching or card components for these — reuse the
  Overview grid with a different default filter applied.

Routes:
```
/                          Overview — grid of directories (also serves as "Directories")
/?view=pipeline            Same grid, grouped by stage (the "Pipeline" nav item)
/?view=deploy              Same grid, filtered to Upload-done-or-later (the "Deploy" nav item)
/directories/{id}          Directory Detail — tabbed: Pipeline | Config | Logs | Stats (Pipeline contains the Collect/Clean/Enrich/Upload/Deploy stage cards)
/settings                  Global settings — credentials
```

"New Directory" is a **modal**, not a route — triggered from the Overview
page, matching the existing `dataset-collector` create-project modal
pattern (Q11).

## Global Shell

Top nav bar (not a sidebar — correcting the earlier description here to
match what was actually built): logo mark + wordmark on the left, inline
links on the right. Rename the **"Pipeline"** nav link to **"In Progress"**
— it collides with the Directory Detail page's own "Pipeline" tab, and
having two different things both labeled "Pipeline" visible on screen at
once (the nav menu and the tab bar) is confusing regardless of styling.
The four links become: Overview, In Progress, Deploy, Settings.

**Mobile Layout — below the 768px breakpoint:**
- Hamburger icon: a proper 3-line menu icon (Lucide `menu`), not a custom
  2-line shape — 44x44px tap target, right side of the top bar, vertically
  centered with the logo mark. Swaps to an `x` (close) icon while the menu
  is open.
- The logo mark (hexagon icon) must still be visible next to the
  wordmark — don't drop it even if the wordmark itself has to shrink or
  hide at the narrowest widths.
- Opening the menu: a **full-width dropdown panel directly below the top
  bar** (not a narrow floating box offset to one side, which is what's
  currently overlapping page content awkwardly) — spans the full
  viewport width, white background, subtle shadow, rounded bottom
  corners. Behind it, dim the rest of the page with a semi-transparent
  dark overlay (~45% black) — this is what makes it read as a proper menu
  layer rather than a stray box sitting on top of content. Tapping the
  overlay or selecting a link closes the menu.
- Each link is a full-width row, minimum 44px tall, generous padding
  (~16px vertical), with a thin divider between rows. Highlight whichever
  link matches the current page (background tint or a left accent border
  in the teal accent color) so it's clear where you are.
- No slide-in animation needed — a simple show/hide is fine, the visual
  polish comes from the backdrop dim, spacing, and active-state
  highlighting, not from motion.
- Nothing in the top bar should ever cause the page to scroll
  horizontally.

At or above 768px, the current inline-links layout is unchanged.

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

**Card contents (fixed set, per Q4 — finalized against the confirmed mockup):**
- Small rounded-square icon badge (~48x48px, ~10px radius, light tinted
  background matching the teal accent), top-left, inline with the title —
  a **niche icon**, not a status icon. Status is already fully conveyed by
  the pill and the stepper; a niche icon adds information neither of those
  do (what kind of business this directory is), which matters when
  scanning a grid of 11+ structurally-identical cards. See the icon
  mapping table below.
- Directory name, next to the icon (~12-16px gap between icon and title)
- Status pill on the **same row** as the icon/title, right-aligned —
  sentence case ("Deployed", "Collecting"), not all-caps. If a directory
  name is long enough to risk colliding with the pill, truncate the name
  with an ellipsis or let it wrap to a second line — don't push the pill
  onto its own row to solve that, keep pill and title on one row.
- **No category/niche-label subtitle line under the title** — deliberately
  excluded even though a reference mockup shows one.
- 7-dot pipeline stepper, **with labels under each dot**: Idea · Collect ·
  Clean · Enrich · Upload · Deploy · Live. Dot states: **done** = filled
  teal circle with a white checkmark; **current/running** = filled blue
  circle with a white inner ring (pulsing); **not-yet-reached** = empty
  outlined grey circle, nothing inside it — no fill, no icon, no inner
  dot. No connecting line between dots — dropped after repeated
  implementation issues; the dots and labels alone are sufficient. Each
  label must be horizontally centered directly under its own dot, evenly
  spaced across the full card width regardless of label length.
- Place count and last-updated on one row, space-between layout (count +
  pin icon on the left, "Updated ..." + calendar icon on the right) — no
  divider character between them.
- One button, **always labeled "View Project"**, always the same teal
  accent color regardless of status — not dynamic per stage, and not the
  blue shown in some reference mockups.
- No secondary/kebab menu on the card itself — deletion lives on the
  Directory Detail page only, to avoid an accidental click on a dense grid.
- Generous internal padding throughout (~24px card padding; ~20-24px
  between the header row and the stepper; ~16-20px between the stepper and
  the divider below it; ~16px between the divider and the places row;
  ~16-20px before the button) — err toward more whitespace, not less.

**Niche icon mapping** — Lucide icon per directory, keyed by niche label.
Verify each name actually exists in the installed Lucide set before using
it (some guesses below may not match exactly); fall back to a generic icon
(e.g. `store` or `building-2`) for any niche not in this table, since more
directories will be added later:

| Niche | Suggested Lucide icon |
|---|---|
| Baby Sleep Consultant | `baby` |
| Mobile Auto Electricians | `zap` |
| Laundromat | `shirt` |
| Pest Control | `bug` |
| Mobile Vet | `paw-print` |
| Caravan Repairs | `wrench` |
| Mobile Locksmiths | `key` |
| Mobile Windscreen Repair | `car` |
| Car Detailers | `sparkles` |
| Mobile Dog Groomers | `dog` |
| Mobile Mechanics | `wrench` |

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

Synthesized from two reference mockups — consolidated from the original
8-tab breakdown down to 4, with a persistent header/banner/stat area that
stays visible regardless of which tab is active. Nothing from the original
8-tab version is lost — Collect's map+table and the Clean/Enrich/Upload/
Deploy shared panel shape still exist, they're just nested as expandable
cards inside the Pipeline tab instead of being separate tabs.

**This entire header/banner/stat area is single-column below 768px** — the
current build has a stat tile positioned beside the header instead of
below it, and it doesn't reflow, which is the mobile bug to fix. Layout
order, one column, full width, top to bottom:

```
← Back to Overview
[icon] Directory Name
  ● Status pill                    (wraps below the name if it
                                     doesn't fit on the same line —
                                     never causes horizontal scroll)
Pet Services • mobilegroomers.com.au

┌─ Current Stage banner (full width, only when running) ─┐
│  Enriching — AI is generating descriptions...           │
│  ▓▓▓▓▓▓▓▓░░░░░░  62%   7,714 / 12,418 records            │
│  [Cancel]                                                │
└──────────────────────────────────────────────────────┘

┌──────────────┐ ┌──────────────┐
│   Places     │ │  Enriched    │   ← 2x2 grid, not a 4-wide row.
│   12,842     │ │   7,714      │      Confirm all 4 tiles actually
├──────────────┤ ├──────────────┤      exist in the DOM — only 1 of 4
│ Avg Quality  │ │   Monthly    │      is visible in the current build,
│     85       │ │   Visits     │      which may mean the other 3 are
│              │ │   8,431      │      overflowing off-screen rather
└──────────────┘ └──────────────┘      than a pure styling issue.

🚀 View Live Site — mobilegroomers.com.au    ›

[ Pipeline ] [ Config ] [ Logs ] [ Stats ]
──────────────────────────────────────────
(active tab's content, below)
```

At or above 768px, this becomes the wider layout already built — icon/
title/pill on one row, 4 stat tiles in a single row, as originally speced:

```
┌────────────────────────────────────────────────────────────────┐
│  Directory Factory                         [Overview][Settings] │
├────────────────────────────────────────────────────────────────┤
│  ← [icon] Mobile Dog Groomers          ● Live            [⋮]     │
│    Pet Services • mobilegroomers.com.au                          │
│                                                                   │
│  ┌─ Current Stage banner (only visible while something's        │
│  │  actively running — hidden entirely when idle) ─────────┐     │
│  │  Enriching — AI is generating descriptions, services,   │     │
│  │  and SEO content for your listings.                     │     │
│  │  ▓▓▓▓▓▓▓▓░░░░░░  62%   7,714 / 12,418 records            │     │
│  │  [Cancel]                                                │     │
│  └───────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Places  │ │ Enriched │ │Avg Quality│ │ Monthly  │            │
│  │  12,842  │ │  7,714   │ │   85      │ │  Visits  │            │
│  │          │ │ 60% of   │ │           │ │   8,431  │            │
│  │          │ │  total   │ │           │ │          │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                   │
│  🚀 View Live Site — mobilegroomers.com.au              ›       │
│  (only shown once Deploy is Done)                                │
│                                                                   │
│  [ Pipeline ] [ Config ] [ Logs ] [ Stats ]                      │
│  ───────────────────────────────────────────────────────────    │
│                     (active tab's content, below)                │
└────────────────────────────────────────────────────────────────┘
```

`[⋮]` opens exactly one option: **Delete Directory** — the only
destructive action anywhere in the UI, unchanged from before, still
requires the confirm dialog under "Confirmation & destructive actions".

**Stat tiles** — four, always real data, no invented metrics:
- Places Collected
- Enriched Records (count + % of total collected)
- Avg Quality Score (average of the `quality_score` column across this
  directory's businesses)
- Monthly Visits — em-dash placeholder if not yet deployed, never `0`
  (a real `0` and "not applicable yet" should never look the same)

**Current Stage banner** — only rendered when a script is actively
`running` for this directory; absent entirely when idle, so it doesn't
take up space on directories with nothing in progress. The action button
is **Cancel**, not Pause — there's no real pause/resume for anything
except Collection (which already has it, ported from `dataset-collector`).
Cancel just stops the subprocess; since Clean/Enrich/Upload should already
skip already-processed records on re-run, a cancel-and-rerun is a fine
substitute for true pause/resume without new engineering.

### Tab: Pipeline (default)

```
┌─────────────────────────────────────────────┐
│  Pipeline Progress          6 of 7 · 86%      │
│  ●──●──●──●──●──●──○  (7-dot stepper —        │
│  Idea Collect Clean Enrich Upload Deploy Live │
│  same component as the Overview card, no      │
│  connecting line, per the earlier decision)   │
├─────────────────────────────────────────────┤
│  📍 Collect          ✓ Complete    100%       │
│  Google Places API collection                 │
│  12,842 / 12,842        ▓▓▓▓▓▓▓▓▓▓▓▓▓▓        │
│  Completed 30 Jul 2026, 05:14          [⌄]    │
├─────────────────────────────────────────────┤
│  ✨ Clean            ✓ Complete    99%        │
│  Data normalization & structure                │
│  12,671 / 12,842        ▓▓▓▓▓▓▓▓▓▓▓▓▓░        │
│  Completed 30 Jul 2026, 05:18          [⌄]    │
├─────────────────────────────────────────────┤
│  🪄 Enrich           ● Running     62%        │
│  AI content generation                         │
│  7,714 / 12,418         ▓▓▓▓▓▓▓░░░░░░░        │
│  Started 30 Jul 2026, 05:26            [⌄]    │
├─────────────────────────────────────────────┤
│  ☁ Upload            ○ Not started             │
├─────────────────────────────────────────────┤
│  🚀 Deploy            ○ Not started             │
│  Domain: [________________]                    │
└─────────────────────────────────────────────┘

  Recent Activity                    View all →
  ┌─────────────────────────────────────────┐
  │ 05:26  Enrichment started                │
  │ 05:18  Cleaning completed    12,671 rows │
  │ 05:14  Collection completed  12,842 rows │
  │ 05:02  Collection started                │
  └─────────────────────────────────────────┘
  (CLI-log styled — dark background, monospace,
   small colored status dot per line)
```

Five stacked stage cards — **Collect, Clean, Enrich, Upload, Deploy** —
each with: icon, name, status pill, one-line description of what that
stage does, record progress (`X / Y` + a progress bar), a
started/completed timestamp, and an expand control `[⌄]`.

- Expanding **Collect** reveals the map + places table + search/
  completeness filter (Q12, ported from `dataset-collector`) — this
  content is unchanged from the original Collect tab, just nested here.
- Expanding **Clean / Enrich / Upload** reveals the full stdout/stderr log
  for the most recent run (Q8) — unchanged from the original shared panel
  shape, just nested here. Clean's expanded view also shows the **Feature
  Taxonomy** editor (Q2.4).
- Expanding **Deploy** reveals the same content as before: the Domain
  input field, and once deployed, this is where `[View Live Site ↗]`
  originates (also surfaced as the persistent row above the tabs).
- Each collapsed card still shows a `[Re-run]` (or `[Start]` if not yet
  run) button without needing to expand — one click from the collapsed
  state for the common case, expand only when something needs
  investigating.
- No separate "Quick Actions" shortcut row — every action already has a
  button on its own stage card here; a duplicate shortcut bar would just
  be two ways to trigger the same five things.

**Recent Activity** — a condensed feed (last ~5 events) styled like a
CLI log (dark background, monospace, small colored status dot per line),
with a "View all →" link to the Logs tab. This is deliberately the same
visual language as the Logs tab itself, just truncated — consistency
between the preview and the full view.

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

Unchanged from before — field list is exactly Q6's decided `site_config`
list, preview is the in-dashboard mock described in Q7.

### Tab: Logs

Renamed from "Runs" — same underlying data. **Full dark terminal styling
throughout**, reversing the earlier "light rows" instruction — that was
the wrong call for a tool built for one technical user; a real terminal
look is exactly right here. Collapsed-by-default is still the core
requirement (unchanged from before): the current build renders every
entry's full raw output inline with no collapse, which is the main reason
it's unusable, separate from color.

The whole log list lives in **one continuous dark panel** (`#0d1117`),
not a stack of individually-bordered white cards. Filter controls
(Script/Status dropdowns) stay as normal light page UI *above* the panel —
they're page chrome, not log content, so they don't need to be dark too.

**Exact structure — use this HTML/CSS directly, don't reinterpret it.**
The current build's floating dot/chevron/text-on-separate-lines bug comes
from these not being nested as one row; this structure prevents that by
construction:

```html
<div class="log-panel">
  <div class="log-row">
    <div class="log-row-summary" onclick="toggleLogRow(this)">
      <span class="log-dot success"></span>
      <span class="log-time">12:03</span>
      <span class="log-script">collection.collect</span>
      <span class="log-message">Collection complete: 387 places</span>
      <span class="log-chevron">⌄</span>
    </div>
    <div class="log-row-detail"><!-- full stdout/stderr, hidden unless expanded --></div>
  </div>
  <!-- one .log-row per entry -->
</div>
```

```css
.log-panel {
  background: #0d1117;
  border-radius: 8px;
  font-family: 'SFMono-Regular', Consolas, monospace;
  overflow: hidden;
}
.log-row { border-bottom: 1px solid rgba(255,255,255,0.08); }
.log-row:last-child { border-bottom: none; }
.log-row-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  cursor: pointer;
}
.log-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.log-dot.success { background: #14b8a6; }  /* same teal used everywhere else */
.log-dot.error { background: #ef4444; }
.log-dot.running { background: #3b82f6; }
.log-time { color: #8b949e; font-size: 12px; flex-shrink: 0; }
.log-script { color: #e6e6e6; font-weight: 600; font-size: 13px; flex-shrink: 0; }
.log-message {
  color: #9ca3af;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}
.log-chevron { color: #8b949e; flex-shrink: 0; }
.log-row-detail {
  display: none;
  padding: 0 16px 16px 34px;
  max-height: 400px;
  overflow-y: auto;
  color: #d1d5db;
  font-size: 12px;
  white-space: pre-wrap;
}
.log-row.expanded .log-row-detail { display: block; }
```

Key points this structure enforces:
- **The entire row is the click target** (`.log-row-summary`, not just the
  chevron) — `toggleLogRow` adds/removes an `expanded` class on the parent
  `.log-row`. Clicking anywhere on the row toggles it, not just the tiny
  icon.
- **One row, one flex line** — dot, time, script name, message, and
  chevron are all children of the same flex container, so they can never
  drift apart into separately-floating elements the way they did before.
- **Status dot colors match the app's existing palette** (teal for
  done/success, red for error, blue for running) — same colors used
  everywhere else in the dashboard, just set against the dark background
  here. Not a separate green-terminal color scheme unique to this tab.
- **Message truncates with ellipsis when collapsed** — for a successful
  run, the stored `summary` field; for an error, the **last line only** of
  the traceback (the actual `ExceptionType: message` line, not "Traceback
  (most recent call last):") — that's the part worth seeing without
  expanding.
- **Expanded detail scrolls within its own box** (max-height ~400px) —
  never blows out the page length no matter how long the traceback is.

Filtered to this directory by default (Q9). Filter dropdowns use the same
styled component already fixed on the Overview page — not plain native
`<select>` elements.

**The Pipeline tab's "Recent Activity" condensed feed uses this same dark
panel treatment** (reverting the earlier light-row instruction there too)
— same `.log-panel`/`.log-row` structure, just showing the last ~5 entries
with no expand needed (it's a preview). The "View all →" link takes you to
this Logs tab.

### Tab: Stats

Renamed from "Live Stats" — unchanged otherwise. Only shows meaningful
content once Deploy is `Done`; otherwise shows "Deploy this directory to
see live stats."

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
