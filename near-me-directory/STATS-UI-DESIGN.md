# Toilets Near Me — Stats Section UI Design
## Frontend Specification for Astro Build Agent
### v3 — Based on live page audit of v1 and v2

This document covers the Astro frontend only.
It assumes the Supabase `stats` table is populated and correct.
Data pipeline fixes are handled separately by the data pipeline agent.

---

## 0. Priority Framework

This governs every design and layout decision across all stats pages.

| Priority | Topic | Why |
|---|---|---|
| **1 — Primary** | Wheelchair accessibility | Widest audience — disability, elderly, mobility aids |
| **2 — Primary** | Baby change | Parents with infants — large active search audience |
| **3 — Secondary** | 24-hour access | Medical conditions, shift workers, night travel |
| **4 — Not featured** | Everything else | Dump points, Changing Places, MLAK — data exists but not headline |

---

## 1. Supabase Query Functions
### `src/lib/stats.js`

```javascript
import { supabase } from './supabase'

// All metrics for one entity — returns object keyed by metric name
export async function getEntityStats(entityType, entityId) {
  const { data } = await supabase
    .from('stats')
    .select('metric, value, rank, rank_of, metadata, source_version')
    .eq('entity_type', entityType)
    .eq('entity_id', entityId ?? null)
  return Object.fromEntries((data ?? []).map(r => [r.metric, r]))
}

// All 8 states ranked by one metric — for comparison charts
export async function getStateRankings(metric) {
  const { data } = await supabase
    .from('stats')
    .select('entity_id, value, rank, rank_of, metadata')
    .eq('entity_type', 'state')
    .eq('metric', metric)
    .order('rank', { ascending: true })
  return data ?? []
}

// All nation-level rows — for the /stats homepage
export async function getNationStats() {
  const { data } = await supabase
    .from('stats')
    .select('metric, value, rank, rank_of, metadata, source_version')
    .eq('entity_type', 'nation')
  return Object.fromEntries((data ?? []).map(r => [r.metric, r]))
}

// Available data versions for history switcher
export async function getAvailableVersions() {
  const { data } = await supabase
    .from('stats')
    .select('source_version')
    .eq('entity_type', 'nation')
    .eq('metric', 'toilet_count')
    .order('source_version', { ascending: false })
  return (data ?? []).map(r => r.source_version)
}

// Historical version of stats for one entity
export async function getEntityStatsByVersion(entityType, entityId, version) {
  const { data } = await supabase
    .from('stats')
    .select('metric, value, rank, rank_of, metadata')
    .eq('entity_type', entityType)
    .eq('entity_id', entityId ?? null)
    .eq('source_version', version)
  return Object.fromEntries((data ?? []).map(r => [r.metric, r]))
}
```

---

## 2. Utility Functions
### `src/lib/stats-utils.js`

```javascript
// Grade for COMPOSITE SCORES (0–100)
// Used on state score cards only
export function scoreToGrade(score) {
  if (score === null || score === undefined) return { grade: '—', color: 'neutral' }
  if (score >= 70) return { grade: 'A', color: 'green' }
  if (score >= 45) return { grade: 'B', color: 'amber' }
  return { grade: 'C', color: 'red' }
}

// Grade for RAW PERCENTAGES on comparison charts
// Relative to national average — always produces meaningful A/B/C spread
// regardless of the absolute range of the data
export function pctToGrade(pct, nationalAvg) {
  if (pct === null || nationalAvg === null) return { grade: '—', color: 'neutral' }
  if (pct >= nationalAvg + 3) return { grade: 'A', color: 'green' }
  if (pct >= nationalAvg - 3) return { grade: 'B', color: 'amber' }
  return { grade: 'C', color: 'red' }
}
// Example with national avg 56.9%:
//   NSW 61.9% → A (well above avg)
//   VIC 57.3% → B (near avg)
//   NT  49.5% → C (well below avg)

// Minutes-from-midnight to readable time: 1080 → "6:00pm"
export function minsToTime(mins) {
  if (mins === null || mins === undefined) return null
  const m = mins % 1440
  const h = Math.floor(m / 60)
  const min = m % 60
  const period = h < 12 ? 'am' : 'pm'
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
  return min === 0
    ? `${h12}${period}`
    : `${h12}:${String(min).padStart(2, '0')}${period}`
}

// source_version to display date: '2025-01' → 'January 2025'
export function formatVersion(version) {
  if (!version) return 'Unknown'
  const [year, month] = version.split('-')
  const names = ['','January','February','March','April','May','June',
                 'July','August','September','October','November','December']
  return `${names[parseInt(month)]} ${year}`
}

// Large number with commas: 25062 → "25,062"
export function formatCount(n) {
  if (n === null || n === undefined) return '—'
  return Number(n).toLocaleString('en-AU')
}

// Ordinal suffix: 1 → "1st", 2 → "2nd", 3 → "3rd"
export function ordinal(n) {
  if (!n) return '—'
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export const STATE_NAMES = {
  nsw: 'New South Wales',  vic: 'Victoria',
  qld: 'Queensland',       wa:  'Western Australia',
  sa:  'South Australia',  tas: 'Tasmania',
  act: 'Australian Capital Territory', nt: 'Northern Territory'
}

export const stateName = code =>
  STATE_NAMES[code?.toLowerCase()] ?? code?.toUpperCase()
```

---

## 3. Visual Design System

### 3.1 Color tokens

| Token | Value | Used for |
|---|---|---|
| `stats-accessible` | Blue `#2563EB` | Accessibility topic |
| `stats-family` | Teal `#0D9488` | Baby change / family topic |
| `stats-hours` | Amber `#D97706` | 24-hour / opening hours |
| `stats-good` | Green `#16A34A` | A grade / above average |
| `stats-mid` | Amber `#D97706` | B grade / near average |
| `stats-low` | Red `#DC2626` | C grade / below average / gaps |
| `stats-neutral` | Grey `#6B7280` | Supporting stats, secondary text |

### 3.2 Lucide icon assignments

One icon per concept, used consistently across all pages and components.

```
Accessibility topic:  <Accessibility />
Baby change topic:    <Baby />
24-hour / time:       <Clock />
Top rankings:         <Trophy />
Gap / missing:        <AlertCircle />
Good coverage:        <CheckCircle2 />
Per capita / people:  <Users />
State / region:       <Map />
History / date:       <CalendarDays />
Info / methodology:   <Info />
CTA arrow:            <ChevronRight />
Grade badge:          <BadgeCheck />
```

### 3.3 Section rhythm

Alternate section backgrounds throughout every page:
- Section 1: white
- Section 2: `gray-50`
- Section 3: white
- Section 4: `gray-50`
- etc.

This creates visual separation without borders or dividers.

### 3.4 Storytelling pattern

Every section on every page follows this exact sequence:

1. **H2 heading** — what this section covers
2. **InsightCallout** — one finding with real numbers (tells the story)
3. **Evidence** — chart, table, or tiles (proves the finding)
4. **CTA** — specific link (not "see more")

The callout always comes before the evidence. Users read the finding, then
see the data that backs it up — not the other way around.

---

## 4. Component Specifications

### StatTile
Three tiles per section maximum. Layout: 2-column grid on mobile (tiles 1+2
side by side, tile 3 full-width below). 3-column on tablet+. Never single
column — too much vertical scroll.

```
┌─────────────────────────────────┐
│  [Lucide icon — topic color]    │
│  [Large number — 36px bold]     │
│  [Label — 14px grey]            │
│  [Context — 12px grey]          │
│  e.g. "of 25,413 facilities"    │
└─────────────────────────────────┘
```

### InsightCallout
Left border 4px solid topic color. Background: light tint of topic color
(e.g. `blue-50` for accessibility, `teal-50` for baby change).

```
┌────────────────────────────────────────────────────┐
│ [Icon]  [One strong finding sentence]              │
│         [1–2 sentences of context with real data]  │
└────────────────────────────────────────────────────┘
```

**Critical rule:** Values in the callout MUST come from the same data query
as the chart or table below it. Never hardcode or derive separately.

### CoverageBar
Used in tables and state comparisons. Shows percentage as filled bar + grade.

```
♿  Accessible toilets
████████████░░░░░  61.9%  [A]
```

**Critical rule:** Bar width is proportional to position within the dataset range
(min to max) — NOT proportional to 0–100. With states ranging 49–62%, a
0–100 scale makes all bars look identical. Scale from the minimum value to
the maximum value so differences are visible.

```javascript
// Bar width calculation
const barWidth = ((value - dataMin) / (dataMax - dataMin)) * 100
// This makes the lowest value show a short bar and the highest a full bar
// even when the absolute range is narrow (e.g. 49% to 62%)
```

Grade uses `pctToGrade(value, nationalAvg)` — relative to national average,
not fixed thresholds.

### GradeBadge
`[A]` green · `[B]` amber · `[C]` red — white text on colored background.
Always use `pctToGrade()` for chart percentages.
Always use `scoreToGrade()` for composite scores on state pages.
Never use one where the other is appropriate.

### RankBadge
`#1` gold · `#2` silver · `#3` bronze · rest neutral grey.
**Always show rank_of total:** "#1 of 8" not "#1".
If `rank_of` from the database is not 8 for state rows, override it to 8
in the component — this is a known data bug being fixed in the pipeline.

```javascript
// Safe rank display — override bad rank_of values
const displayRankOf = entityType === 'state' ? 8 : rankOf
```

### StateComparisonChart
Tab group with three tabs: `[♿ Accessibility]` `[👶 Baby Change]` `[🕐 24-Hour Access]`

**Rules:**
- All three tabs must use the same UI element — tabs, not a mix of tabs and toggles
- All three datasets fetched at build time, stored as JSON in the component
- Tab switching is CSS/JS visibility — no re-fetching on tab change
- Chart subtitle updates when tab changes to describe the metric shown
- National average line drawn as a subtle vertical rule on the chart

---

## 5. Page Specifications

---

### PAGE 1: `/stats`

**SEO:**
```
<title>Australian Public Toilet Statistics [Year] | Toilets Near Me</title>
<meta name="description" content="[accessible_pct_avg]% of Australia's
[toilet_count] public toilets are wheelchair accessible and [baby_change_pct]%
have baby change. Complete data by state and region." />
<h1>Australian Public Toilet Statistics [Year]</h1>
```
Schema.org: `Dataset` type — name, description, datePublished from `source_version`.

**Data fetched at build time:**
```javascript
const [nation, accessRankings, babyRankings, hoursRankings] = await Promise.all([
  getNationStats(),
  getStateRankings('accessible_pct'),
  getStateRankings('baby_change_pct'),
  getStateRankings('open_24h_pct'),
])
```

**Page layout — top to bottom:**

---

**[white] SECTION 1 — Page header**
```
Australian Public Toilet Statistics 2026
Based on 25,413 facilities across 8 states and ~548 local government areas
Data current as of [formatVersion(nation['toilet_count'].source_version)]
```

---

**[white] SECTION 2 — InsightCallout (before tiles)**

The story comes before the numbers.

```javascript
const bestState  = accessRankings[0]
const worstState = accessRankings[accessRankings.length - 1]
```

```
┌──────────────────────────────────────────────────────┐
│ ♿  More than half of Australia's public toilets are  │
│    wheelchair accessible.                            │
│    Coverage ranges from [bestState.value]% in        │
│    [stateName(bestState.entity_id)] to               │
│    [worstState.value]% in                            │
│    [stateName(worstState.entity_id)].                │
└──────────────────────────────────────────────────────┘
```

---

**[white] SECTION 3 — Three stat tiles**

2-column mobile (tile 3 full-width below), 3-column tablet+.

```
┌─────────────────┐  ┌─────────────────┐
│  ♿              │  │  👶              │
│  56.9%          │  │  5,364          │
│  Wheelchair     │  │  Baby Change    │
│  Accessible     │  │  Facilities     │
│  of 25,413      │  │  21.1% of all   │
└─────────────────┘  └─────────────────┘
┌─────────────────────────────────────┐
│  🕐  11,367 · Open 24 Hours         │
│  44.7% of all facilities            │
└─────────────────────────────────────┘
```

Values:
- Tile 1: `nation['accessible_pct_avg'].value` + `nation['toilet_count'].value`
- Tile 2: `nation['baby_change_count'].value` + calculate % client-side
- Tile 3: `nation['open_24h_count'].value` + `nation['open_24h_pct_avg'].value`

---

**[gray-50] SECTION 4 — State comparison chart**

H2: How accessible are public toilets in your state?

Three tabs (all same UI element):
```
[♿ Accessibility]  [👶 Baby Change]  [🕐 24-Hour Access]
```

Active tab subtitle (changes per tab):
- Accessibility: "% of toilets that are wheelchair accessible"
- Baby Change: "% of toilets with baby change facilities"
- 24-Hour: "% of toilets open around the clock"

Chart for each tab — bars scaled min to max, grade relative to national avg:
```
                          % WHEELCHAIR ACCESSIBLE (national avg: 56.9%)
NSW         ████████████████████████  61.9%  [A]  #1 of 8
QLD         ████████████████████████  60.4%  [A]  #2 of 8
SA          ███████████████████████   60.0%  [A]  #3 of 8
WA          ██████████████████████    59.5%  [A]  #4 of 8
VIC         █████████████████████     57.3%  [B]  #5 of 8
ACT         ████████████████████      54.1%  [B]  #6 of 8
TAS         ███████████████████       52.5%  [C]  #7 of 8
NT          ████████████████          49.5%  [C]  #8 of 8
             ↑ 49% (min)                    ↑ 62% (max)
```

State names link to `/stats/[state]`.

CTA below chart: "See full state breakdown →" `/stats/accessibility`

---

**[white] SECTION 5 — Baby change**

H2: Baby change facilities across Australia 👶

InsightCallout (teal):
```javascript
const bestBaby  = babyRankings[0]
const worstBaby = babyRankings[babyRankings.length - 1]
```
"Only 1 in 5 Australian public toilets has a baby change table. [bestBaby state]
leads with [bestBaby.value]% coverage while [worstBaby state] has the lowest at
[worstBaby.value]%."

State bars — baby_change_pct, scaled min to max, grades relative to avg.

Top 5 regions table (from `nation['top_regions_family_score'].metadata.list`):
```
┌───┬────────────────┬───────┬──────────────┐
│ # │ Region         │ State │ Baby change  │
├───┼────────────────┼───────┼──────────────┤
│ 1 │ [region]       │ VIC   │ 38.2%        │
└───┴────────────────┴───────┴──────────────┘
```

CTA: "Find toilets with baby change →" `/toilets?feature=baby_change`

---

**[gray-50] SECTION 6 — 24-hour access**

H2: When are Australia's public toilets open? 🕐

Two tiles (side by side):
```
┌─────────────────┐  ┌─────────────────┐
│  11,367         │  │  44.7%          │
│  Open 24 hours  │  │  of all         │
│                 │  │  facilities     │
└─────────────────┘  └─────────────────┘
```

If `nation['open_after_10pm_count'].value` is not null: show as third tile.
If null: do not render the tile. No dashes, no placeholders.

State comparison bars — open_24h_pct.

CTA: "Find 24-hour toilets →" `/toilets?feature=24_hours`

---

**[white] SECTION 7 — Top accessible regions**

H2: Best-covered regions for accessible toilets 🏆

Note: "Minimum 10 facilities and 5,000 population required to qualify."

Data from: `nation['top_regions_accessible_pct'].metadata.list`

```
┌────┬────────────────┬───────┬─────────────┬─────────┐
│ #  │ Region         │ State │ Accessible% │ Toilets │
└────┴────────────────┴───────┴─────────────┴─────────┘
```

`Toilets` column reads from `item.toilet_count`. If this is undefined, do not
show a dash — contact the data pipeline team (this is a known data fix).

CTA: "See full accessibility rankings →" `/stats/accessibility`

---

**[gray-50] SECTION 8 — Methodology**

H2: About this data ℹ️

```
Data sourced from the National Public Toilet Map (Australian Government)
and the Australian Bureau of Statistics. Statistics reflect
[formatCount(nation['toilet_count'].value)] facilities as of
[formatVersion(source_version)].
```

Year history — plain text, no special component needed:
```
Previous data releases:
[formatVersion('2024-10')]  ·  [formatVersion('2026-06')]
```
Each links to `?version=YYYY-MM`. When version param is present, call
`getEntityStatsByVersion()` and show a banner: "Viewing historical data from
[version]. View current data →"

---

---

### PAGE 2: `/stats/accessibility`

**SEO:**
```
<title>Wheelchair Accessible Toilets in Australia — State Rankings [Year]</title>
<meta name="description" content="[accessible_pct_avg]% of Australia's public
toilets are wheelchair accessible. Complete state and region rankings." />
<h1>Wheelchair Accessible Public Toilets in Australia</h1>
```

**Data:**
```javascript
const [nation, accessRankings, perCapitaRankings] = await Promise.all([
  getNationStats(),
  getStateRankings('accessible_pct'),
  getStateRankings('accessible_per_10k'),
])
const nationalAvg = nation['accessible_pct_avg']?.value ?? 0
```

**Layout:**

```
[white] Two tiles
  accessible_count | people_per_accessible (national avg)

[white] InsightCallout ♿
  Best vs worst state — real values from accessRankings[0] and [7]

[gray-50] State rankings table
  H2: Accessible toilets by state ♿
  Columns: Rank | State (→/stats/[state]) | Accessible | Total | % (CoverageBar + grade) | Per 10k | Rank badge
  Grade: pctToGrade(value, nationalAvg)
  Sorted by rank ascending

[white] InsightCallout — the per-capita finding
  "[State] ranks last by percentage but [better rank] per capita."
  Values from comparing accessRankings and perCapitaRankings arrays.

[gray-50] Top regions
  H2: Best-covered regions ♿
  Table from nation['top_regions_accessible_pct'].metadata.list
  Columns: Rank | Region | State | % Accessible | Toilets
  Note: "Minimum 10 facilities and 5,000 population to qualify."

[white] Bottom regions
  H2: Where coverage is lowest ♿
  Table from nation['bottom_regions_accessible_pct'].metadata.list
  Same columns. Brief framing note.

[gray-50] MLAK (supporting only — compact)
  H2: Key-access facilities
  2-sentence explainer. One stat: X% of accessible toilets require MLAK.
  State table: mlak_of_accessible_pct. External MLAK link.

[white] Changing Places (supporting only — compact)
  H2: Changing Places facilities
  changing_places_count nationally. State table: count per state.
  Distinction note: "Not the same as an accessible toilet."
```

---

### PAGE 3: `/stats/families`

**SEO:**
```
<title>Baby Change Facilities in Australian Public Toilets — [Year]</title>
<meta name="description" content="[baby_change_count] Australian public toilets
have baby change facilities. State and region rankings for families." />
<h1>Baby Change Facilities in Australia</h1>
```

**Critical:** Do not mention Changing Places on this page except in a clearly
labelled distinction note. They serve completely different audiences.

**Data:**
```javascript
const [nation, babyRankings] = await Promise.all([
  getNationStats(),
  getStateRankings('baby_change_pct'),
])
const nationalAvg = babyRankings.reduce((s,r) => s + r.value, 0) / babyRankings.length
```

**Layout:**

```
[white] Two tiles
  baby_change_count | baby_change as % of total

[white] InsightCallout 👶 (teal)
  Best vs worst state — real values from babyRankings

[gray-50] State comparison
  H2: Baby change by state 👶
  Bar chart: baby_change_pct, scaled min-max, grades relative to avg
  Table: State | Count | Total | % | Per 10k | Rank

[white] Top regions for families
  H2: Best regions for families 👶
  Table from nation['top_regions_family_score'].metadata.list
  Columns: Rank | Region | State | Baby change % | Family score

[gray-50] Baby care rooms (distinct from baby change)
  H2: Baby care rooms
  baby_care_room_count nationally.
  "A baby care room is a private dedicated space — a step above a fold-down
  bench. All baby care rooms include a change table."

[white] CTAs
  "Find toilets with baby change →"    /toilets?feature=baby_change
  "Find toilets with baby care rooms →" /toilets?feature=baby_care_room
```

---

### PAGE 4: `/stats/24-hours`

**SEO:**
```
<title>24-Hour Public Toilets in Australia — State Coverage [Year]</title>
<meta name="description" content="[open_24h_count] Australian public toilets are
open 24 hours. See which states have the most coverage." />
<h1>24-Hour Public Toilets in Australia</h1>
```

**Critical rule:** Only render metric rows that have non-null values.
If a value is null: skip the entire tile or row. Never show a dash or placeholder.

**Data:**
```javascript
const [nation, hoursRankings] = await Promise.all([
  getNationStats(),
  getStateRankings('open_24h_pct'),
])
```

**Layout:**

```
[white] Tiles (render only if value is not null)
  Always show: open_24h_count | open_24h_pct
  Conditionally show: open_after_10pm_count (if not null)
  Conditionally show: avg_open_hours_per_day (if not null)

[white] InsightCallout 🕐 (amber)
  Best vs worst state for 24-hour access.

[gray-50] State comparison
  H2: 24-hour access by state 🕐
  Bar chart: open_24h_pct, scaled min-max
  Table: State | 24hr count | Total | % | Per 10k | Rank

[white] Weekend access (only if open_weekend_count data available)
  H2: Weekend coverage
  Show only if at least 6 states have non-null open_weekend_count values.
  If fewer than 6 have data: skip this section entirely.

[gray-50] CTA
  "Find 24-hour toilets →" /toilets?feature=24_hours
```

---

### PAGE 5: `/stats/[state]`

**8 static pages.**

**Static params:**
```javascript
export async function getStaticPaths() {
  return ['nsw','vic','qld','wa','sa','tas','act','nt'].map(state => ({
    params: { state }
  }))
}
```

**SEO:**
```javascript
// In each page — values from stats query
title: `Public Toilet Statistics — ${stateName(state)} ${year} | Toilets Near Me`
description: `${stateName(state)} has ${toilet_count} public toilets.
  ${accessible_pct}% are wheelchair accessible, ranking
  ${ordinal(accessible_rank)} in Australia.`
h1: `Public Toilet Statistics — ${stateName(state)}`
```

**Data:**
```javascript
const stats = await getEntityStats('state', Astro.params.state)
// Access as: stats['accessible_pct'].value, stats['accessible_pct'].rank, etc.
```

**Layout:**

```
[white] SECTION 1 — Header
  H1: Public Toilet Statistics — [State Name]
  [toilet_count] public toilets · [formatVersion(source_version)]

[white] SECTION 2 — Three primary tiles (2-col mobile, 3-col tablet+)
  ┌──────────────────┐  ┌──────────────────┐
  │ ♿ [accessible_pct]│  │ 👶 [baby_change_pct]│
  │ #[rank] of 8    │  │ #[rank] of 8    │
  └──────────────────┘  └──────────────────┘
  ┌────────────────────────────────────────┐
  │ 🕐 [open_24h_pct] · #[rank] of 8      │
  └────────────────────────────────────────┘

  RankBadge always shows "of 8" — override any bad rank_of from DB.
  Rank colour: #1 gold, #2 silver, #3 bronze, rest neutral.

[gray-50] SECTION 3 — National rank summary table
  H2: How [State] ranks nationally
  
  ┌──────────────────────────┬──────────┬────────────┐
  │ ♿  Accessible toilets    │ 61.9%    │ #1 of 8 🥇  │
  │ 👶  Baby change           │ 25.1%    │ #3 of 8    │
  │ 🕐  Open 24 hours         │ 44.2%    │ #4 of 8    │
  └──────────────────────────┴──────────┴────────────┘

[white] SECTION 4 — Accessibility
  H2: Accessibility in [State] ♿
  
  CoverageBar with pctToGrade(value, 56.9)
  Three sub-stats: accessible_count | ambulant_count | mlak_count
  InsightCallout if state rank is #1 or #8.

[gray-50] SECTION 5 — Family facilities
  H2: Family facilities in [State] 👶
  
  CoverageBar with pctToGrade(value, nationalBabyAvg)
  Three sub-stats: baby_change_count | baby_care_room_count | adult_change_count

[white] SECTION 6 — Opening hours
  H2: Opening hours in [State] 🕐
  
  Always show: open_24h_count + open_24h_pct
  Only show if not null: open_after_10pm_count
  Only show if not null: "Average closing time: [minsToTime(avg_closing_time)]"

[gray-50] SECTION 7 — Per capita (only if population data loaded)
  H2: [State] per capita
  [toilets_per_10k] per 10,000 people — #[rank] nationally
  [accessible_per_10k] accessible per 10,000 — #[rank] nationally
  [people_per_toilet] people per toilet — #[rank] nationally

[white] SECTION 8 — Score cards
  H2: [State] at a glance
  
  Three cards:
  ♿ Accessibility Score  [score]/100  Grade [A/B/C]  #[rank] of 8
  👶 Family Score         [score]/100  Grade [A/B/C]  #[rank] of 8
  🕐 24-Hour Score        [score]/100  Grade [A/B/C]  #[rank] of 8
  
  Grade uses scoreToGrade() — composite score thresholds (A≥70, B≥45, C<45)
  NOT pctToGrade() — these are 0–100 scores, not raw percentages.

[gray-50] SECTION 9 — CTAs
  "Find accessible toilets in [State] →" /toilets/[state]?feature=accessible
  "Find baby change in [State] →"        /toilets/[state]?feature=baby_change
  "View all state comparisons →"         /stats
```

---

## 6. What Does NOT Appear on Any Stats Page

| Item | Decision |
|---|---|
| Dump points | Not featured — caravan audience is out of scope for stats v1 |
| Changing Places as headline | Supporting stat under accessibility only |
| Dashes / null values rendered | Skip the row or tile entirely — never render a dash |
| Equal-weight tiles for everything | Design must reflect the priority framework |
| Mixed tab + toggle UI | All three chart options must use the same UI element |
| Ranks without their total | "#3" without "of 8" gives no context |
| Callout values from different source than chart | Single query, same data |

---

## 7. Internal Linking

| From | To | Anchor text |
|---|---|---|
| `/stats` state chart | `/stats/[state]` | State name in chart row |
| `/stats` | `/stats/accessibility` | "See full state breakdown" |
| `/stats` | `/stats/families` | "See baby change coverage" |
| `/stats` | `/stats/24-hours` | "Explore 24-hour facilities" |
| `/stats/accessibility` | `/stats/[state]` | State name in rankings table |
| `/stats/[state]` | `/toilets/[state]?feature=accessible` | "Find accessible toilets in [State]" |
| `/stats/[state]` | `/toilets/[state]?feature=baby_change` | "Find baby change in [State]" |
| `/stats/[state]` | `/stats` | "View all state comparisons" |
| `/toilets/[state]` | `/stats/[state]` | "[State] public toilet statistics" |

---

## 8. Year History

At the bottom of every stats page, below the methodology section:

```
Previous data releases:
[formatVersion('2024-10')]  ·  [formatVersion('2026-06')]
```

Each is a link to the same URL with `?version=YYYY-MM` appended.

When `?version` is present in the URL:
- Call `getEntityStatsByVersion()` instead of `getEntityStats()`
- Show a banner at the top of the page:
  "You are viewing historical data from [formatVersion(version)]. View current data →"
- Add `<link rel="canonical">` pointing to the URL without the version param
  so search engines index only the current version

---

## 9. Build Order

1. `src/lib/stats-utils.js` — utility functions (two grade functions critical)
2. `src/lib/stats.js` — Supabase query functions
3. Components: `StatTile`, `CoverageBar`, `InsightCallout`, `GradeBadge`, `RankBadge`, `StateComparisonChart`, `RegionTable`
4. `/stats` — validate all data is working end-to-end
5. `/stats/[state]` — 8 static pages (simplest query)
6. `/stats/accessibility` — highest SEO priority
7. `/stats/families` — baby change
8. `/stats/24-hours` — only after confirming hours data is not null

---

## 10. Pre-launch Checklist

- [ ] No metric on any page shows null, "—", or undefined
- [ ] InsightCallout values match the chart on the same page (same data source)
- [ ] All state rank badges show "#N of 8" — not "of 5" or "of 7"
- [ ] Toilets column in top regions table shows real numbers (not dashes)
- [ ] Grade badges render on every state row — no missing badges
- [ ] Grades vary across states — not all the same letter
- [ ] CoverageBar chart scaled min-to-max — not 0-to-100
- [ ] All three chart tabs use the same UI element (no mixed tabs/toggles)
- [ ] Baby change section includes state bar chart
- [ ] 24-hour section shows no dashes for missing data
- [ ] Changing Places appears only as supporting stat under accessibility
- [ ] Dump points do not appear on any page
- [ ] State pages: scoreToGrade() used for score cards, pctToGrade() used for chart bars
- [ ] Version history links include canonical tag pointing to current URL