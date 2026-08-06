# Directory Factory — Data Model Spec (D1 Schema)

This is the authoritative shape of every directory's Cloudflare D1
database, adapted from the `toiletsnearme.com.au` Postgres schema for a
generic business directory. Phase 4 (Upload) writes to this shape; Phase 5
(the Astro template) reads from it; Phase 2 (Cleaning/Enrichment) produces
the values that fill it. If any part of the project needs to know what the
data looks like, this is the doc.

## Why this matters (the three project values)

Every decision below serves one of these, and it's worth being explicit
about which, so the reasoning doesn't get lost in the schema details:

- **Useful** — regions exist because they match how people actually
  search ("mobile dog groomers in Brisbane"), not just how the data
  happens to be structured.
- **SEO-focused / EEAT** — `content` is the backbone of this: every page
  level, including individual business pages, gets real generated text,
  not just a data table rendered as a list. This is also the layer that
  makes these sites legible to LLMs pulling structured, well-written data.
- **Enjoyable** — consistent naming and a simple, predictable lookup
  pattern (below) means less to get wrong when building the template,
  which means fewer broken pages and rough edges for the end user.

---

## What's different from the toilets schema, and why

| Toilets table | This project | Reason |
|---|---|---|
| `toilets` | → `businesses` | Same core entity, generic name, with phone/website/structured flags folded in from the enrichment stage |
| `features` | → `business_features`, simplified | Dropped the denormalized `state_code`/`region_slug`/`suburb_slug`/`toilet_slug` columns — those existed for fast queries at 25,000-facility scale. Our directories are far smaller (hundreds to low thousands per niche); a plain `business_id` + `feature_key` join is fast enough and much simpler to reason about |
| `hours` | → `business_hours`, simplified | Dropped seasonal fields (`month_start`/`month_end`), `is_daylight`, `is_unknown`, `raw_source`, `parse_status`, `parse_notes`. One row per day of the week, that's it |
| `notes` | **Not used** | Not needed for this project |
| `stats` | **Not used** | Regional ranking/composite-score pages were a toilets-specific SEO feature, not part of this project's scope |
| `content` | **Kept, extended to `business`** | See "Content model" below — this carries all the EEAT text, at every level including individual businesses (toilets never needed business-level content since individual facilities don't get prose — individual *businesses* should) |
| `regions` | **Kept, simplified** | See "Geography model" below — populated from a Google Places field directly, no spatial computation needed |
| — | **New: `business_services`** | What services a business offers, with pricing fields ready for whenever pricing data becomes available |
| `states`, `suburbs` | Kept, simplified | Dropped `geom`/PostGIS columns — D1 is SQLite, it has no spatial types, and our data doesn't need them (see below) |

---

## Naming & ID Conventions

The rule set — apply it everywhere, not per-table judgment calls:

- **Every table has a surrogate primary key named `id`** (`INTEGER PRIMARY
  KEY AUTOINCREMENT`) — **except `states`**, which uses `code` (e.g.
  `'QLD'`) as its primary key. This is a deliberate, single exception:
  states are a tiny, fixed, stable set (8 rows, never changes), and using
  a real code instead of a meaningless surrogate number avoids a pointless
  join on the single most-referenced table in the schema, and keeps state
  values human-readable in every other table that references one.
- **Foreign keys are named `<parent>_id`** for every surrogate-keyed
  parent (`region_id`, `suburb_id`, `business_id`), and **`state_code`**
  specifically for the one natural-keyed parent. `state_code` instead of
  `state_id` isn't an inconsistency — it's the same rule applied
  correctly: the column name matches what kind of key the parent table
  actually uses.
- **Every user-facing entity has a `slug`** (state, region, suburb,
  business) for building URLs. The slug is never the primary or foreign
  key — the integer `id` (or `code`, for states) always is.

### Slug vs. id vs. code — the lookup pattern to use

URLs are built from slugs (human-readable, good for SEO):
`/qld/brisbane/west-end/mobile-dog-groomers-west-end`

On page load, resolve **top-down, once**, then use integer ids for
everything after that:

1. State: look up by `code` directly (it's already the primary key — no
   separate resolution step needed)
2. Region: indexed lookup on `(slug, state_code)` → get `region.id`
3. Suburb: indexed lookup on `(slug, state_code)` → get `suburb.id`
4. Business: indexed lookup on `(slug, suburb_id)` → get `business.id`

Every other query on that page (features, hours, services, content) joins
on the integer ids resolved in steps 2–4 — never on slugs again after that
first lookup. One extra indexed lookup per page level (negligible), every
join after that is a fast integer comparison instead of a string
comparison, and it's one pattern reused everywhere rather than a different
convention per table.

---

## Geography model: state → region → suburb

Regions matter for SEO — "[niche] in [region name]" (Brisbane, Sydney,
Melbourne) is how people actually search in Australia, more than by
suburb, and the toilets site's own SEO performance backs this up compared
to a state→suburb-only structure.

**What populates a region:** Google's own `addressComponents` includes an
`administrative_area_level_2` field — this is the LGA-level data
(Brisbane, or similar), available directly on every Places API result, the
same place `administrative_area_level_1` (state) and locality (suburb)
come from. **No shapefile, no spatial join, no PostGIS — just another
field read off the same API response already being parsed in Phase 2
Cleaning.**

`region_id` on `suburbs` and `businesses` is nullable — a small number of
addresses may not resolve a clean `administrative_area_level_2`. When that
happens, the business still gets a suburb-level page; it just won't
appear on a region-level listing. That's an acceptable, rare edge case.

---

## Content model (EEAT)

The `content` table carries all the EEAT text — the
`about`/`local_context`/`faq` style blocks (like the QLD state page
example) exist at every level: `state`, `region`, `suburb`, and
**`business`**.

### `content_type` values for this project

| Type | Used at | Purpose |
|---|---|---|
| `about` | state, region, suburb, business | General overview/intro |
| `local_context` | state, region, suburb | How the niche operates in this area — demand, geography, travel patterns |
| `faq` | all levels | Common questions, e.g. "Do mobile groomers in Brisbane travel to my suburb?" |
| `tips` | all levels | e.g. "What to ask a mobile dog groomer before booking" |
| `meta_title` | all levels | `<title>` tag content |
| `meta_description` | all levels | meta description tag content |
| `seo_keywords` | all levels | comma-separated or JSON list, used for schema markup / internal targeting, not displayed as prose |

This is a trimmed set — the toilets-specific `where_to_find`,
`accessibility`, and `counts` types aren't included since they don't map
to a generic business directory.

### Placeholders

Content is generated once and stored with `{{placeholders}}` still in the
text, replaced with live values at render time (so counts stay current
without regenerating content on every data refresh). Placeholders for this
project: `{{business_count}}`, `{{state_name}}`, `{{region_name}}`,
`{{suburb_name}}`, `{{niche_label}}`, `{{avg_rating}}`

### One implementation note

`word_count` should be computed in Python (`len(body.split())`) at the
point a content row is written, and stored as a plain nullable `INTEGER`
column. SQLite/D1 has no `regexp_split_to_array` or built-in regex
functions, so it can't be a database-generated column the way it is in
Postgres — same end result, just computed in the pipeline instead of the
database.

---

## Full Schema (SQLite / D1 DDL)

```sql
-- ============================================================
-- GEOGRAPHY
-- ============================================================

-- Natural key — the one deliberate exception to "every table uses id".
CREATE TABLE states (
    code TEXT PRIMARY KEY,              -- e.g. 'QLD'
    name TEXT NOT NULL,                 -- e.g. 'Queensland'
    slug TEXT NOT NULL UNIQUE,          -- e.g. 'queensland'
    business_count INTEGER NOT NULL DEFAULT 0
);

-- Populated from Places API addressComponents
-- (administrative_area_level_2) during Phase 2 Cleaning — no
-- shapefile, no spatial join.
CREATE TABLE regions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                 -- e.g. 'Brisbane'
    slug TEXT NOT NULL,
    state_code TEXT NOT NULL REFERENCES states(code),
    business_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(slug, state_code)
);
CREATE INDEX regions_state_code_idx ON regions(state_code);

CREATE TABLE suburbs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    state_code TEXT NOT NULL REFERENCES states(code),
    region_id INTEGER REFERENCES regions(id),   -- nullable, see above
    postcode TEXT,
    business_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(slug, state_code)
);
CREATE INDEX suburbs_state_code_idx ON suburbs(state_code);
CREATE INDEX suburbs_region_id_idx ON suburbs(region_id);

-- ============================================================
-- CORE ENTITY
-- ============================================================

CREATE TABLE businesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_place_id TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    slug TEXT NOT NULL,
    category TEXT,                       -- e.g. 'Mobile Dog Groomer'

    address TEXT,
    suburb_id INTEGER REFERENCES suburbs(id),
    region_id INTEGER REFERENCES regions(id),   -- denormalized from suburb, for fast region-listing pages
    state_code TEXT REFERENCES states(code),
    postcode TEXT,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,

    phone TEXT,
    website TEXT,

    is_mobile_service INTEGER NOT NULL DEFAULT 0,     -- boolean (0/1)
    is_emergency_service INTEGER NOT NULL DEFAULT 0,
    service_radius_km INTEGER,

    opening_hours_raw TEXT,              -- fallback display text if structured hours don't parse
    is_24_hours INTEGER NOT NULL DEFAULT 0,

    google_rating REAL,
    google_rating_count INTEGER,
    google_photo_url TEXT,

    data_completeness_score INTEGER,     -- from Phase 1 Collection (0-100)
    quality_score INTEGER,               -- from Phase 2 Enrichment (0-100)

    enriched_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),

    UNIQUE(slug, suburb_id)
);
CREATE INDEX businesses_suburb_id_idx ON businesses(suburb_id);
CREATE INDEX businesses_region_id_idx ON businesses(region_id);
CREATE INDEX businesses_state_code_idx ON businesses(state_code);
CREATE INDEX businesses_slug_idx ON businesses(slug);

-- Note: description / meta_description / seo_keywords are NOT columns
-- here — that text lives in the `content` table (entity_type='business'),
-- consistent with how state/region/suburb content works. Rule of thumb:
-- factual/structured data is a column on `businesses`; AI-generated
-- prose or SEO text is a `content` row.

-- ============================================================
-- FEATURES / HOURS
-- ============================================================

CREATE TABLE business_features (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    feature_key TEXT NOT NULL,
    UNIQUE(business_id, feature_key)
);
CREATE INDEX business_features_business_id_idx ON business_features(business_id);
CREATE INDEX business_features_key_idx ON business_features(feature_key);

CREATE TABLE business_hours (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    day_of_week INTEGER NOT NULL CHECK (day_of_week BETWEEN 0 AND 6),
    open_mins INTEGER,      -- minutes since midnight, NULL if closed that day
    close_mins INTEGER,
    is_closed INTEGER NOT NULL DEFAULT 0,
    UNIQUE(business_id, day_of_week)
);
CREATE INDEX business_hours_business_id_idx ON business_hours(business_id);

-- ============================================================
-- SERVICES — with pricing fields, ready for whenever pricing
-- data becomes available (not required to be populated now)
-- ============================================================

CREATE TABLE business_services (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    service_name TEXT NOT NULL,          -- e.g. 'Nail Trimming'
    price_display TEXT,                  -- free-form fallback: '$50–$80', 'Free quote', 'From $120'
    price_min REAL,                      -- nullable — populate once/if pricing is clean enough to parse
    price_max REAL,
    price_unit TEXT,                     -- e.g. 'per visit', 'per hour', 'flat fee'
    UNIQUE(business_id, service_name)
);
CREATE INDEX business_services_business_id_idx ON business_services(business_id);

-- ============================================================
-- CONTENT (EEAT)
-- ============================================================

CREATE TABLE content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('state','region','suburb','business')),
    entity_id TEXT NOT NULL,             -- states: the code (e.g. 'QLD'); others: the integer id, as text
    content_type TEXT NOT NULL CHECK (content_type IN
        ('about','local_context','faq','tips','meta_title','meta_description','seo_keywords')),
    body TEXT NOT NULL,
    word_count INTEGER,                  -- computed in Python at write time — see note above
    ai_model TEXT,
    approved INTEGER NOT NULL DEFAULT 1,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, entity_id, content_type)
);
CREATE INDEX content_entity_idx ON content(entity_type, entity_id);

-- ============================================================
-- SITE CONFIG
-- ============================================================

CREATE TABLE site_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    value_type TEXT NOT NULL DEFAULT 'text' CHECK (value_type IN ('text','number','boolean','json')),
    config_group TEXT NOT NULL DEFAULT 'general',   -- 'general' | 'appearance' | 'contact' | 'legal' | 'seo'
    is_public INTEGER NOT NULL DEFAULT 1,           -- exposed to the Astro frontend, vs. internal-only
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### `site_config` expected rows

| `key` | `value_type` | `config_group` |
|---|---|---|
| `site_name` | text | general |
| `tagline` | text | general |
| `niche_label` | text | general |
| `domain` | text | general |
| `contact_email` | text | contact |
| `contact_phone` | text | contact |
| `social_links` | json | contact |
| `theme_primary_color` | text | appearance |
| `theme_secondary_color` | text | appearance |
| `logo_url` | text | appearance |
| `og_image_url` | text | seo |
| `legal_privacy_copy` | text | legal |
| `legal_terms_copy` | text | legal |

Every current key is `is_public = 1` — none of this table is meant to hold
secrets (API keys/tokens stay in `.env`, not the database). `is_public`
exists so that rule stays enforced by the schema itself if a server-only
setting is ever added later, rather than by convention alone.

---

## Field origin map — which pipeline stage fills which column/row

| Data | Filled by | Notes |
|---|---|---|
| `google_place_id`, `name`, `address`, `latitude`, `longitude`, `phone`, `website`, `google_rating`, `google_rating_count`, `google_photo_url` | Phase 1 Collection → Phase 1 Cleaning | Straight from Places API, normalized in cleaning |
| `slug`, `category`, `suburb_id`, `region_id`, `state_code`, `postcode` | Phase 1 Cleaning | Region/suburb/state resolved from `addressComponents` |
| `opening_hours_raw`, `is_24_hours`, rows in `business_hours` | Phase 1 Cleaning | Parsed from `regularOpeningHours` |
| rows in `business_features` | Phase 1 Cleaning | Per-niche taxonomy, derived from `types`/`paymentOptions`/`parkingOptions`/`accessibilityOptions` |
| `data_completeness_score` | Phase 1 Collection | Already implemented, unchanged |
| rows in `business_services` (name only — pricing fields left null for now) | Phase 2 Enrichment | AI-extracted service list |
| rows in `content` where `entity_type='business'` | Phase 2 Enrichment | `about`, `faq`, `tips`, `meta_title`, `meta_description`, `seo_keywords` per business |
| rows in `content` where `entity_type IN ('state','region','suburb')` | Phase 2 Enrichment | Geography-level EEAT content, same shape as the toilets site |
| `quality_score`, `is_mobile_service`, `is_emergency_service`, `service_radius_km` | Phase 2 Enrichment | AI-inferred structured flags |
| `enriched_at` | Phase 2 Enrichment | Timestamp |
| everything else, plus `states`/`regions`/`suburbs`.`business_count` | Phase 4 Upload | Writes finished records; recomputes count columns as part of the upload |

---

## What this means for each phase of the master plan

**Phase 2 (Cleaning + Enrichment):**
- Resolve suburb, region, and state during cleaning by reading
  `addressComponents` (locality, `administrative_area_level_2`,
  `administrative_area_level_1`) from the raw Places data. Create the
  region/suburb row if it doesn't exist yet for this directory. No
  spatial/shapefile logic anywhere.
- Add a geography-level content generation task: for every state/region/
  suburb that ends up with at least one business, generate `about`/
  `local_context`/`faq`/`meta_title`/`meta_description` content rows —
  same style as the toilets site's QLD example, adapted to the niche
  (e.g. "mobile dog groomers" instead of "public toilets"), using the
  placeholder list above.
- Business-level enrichment writes `content` rows (`about`, `faq`, `tips`,
  `meta_title`, `meta_description`, `seo_keywords`) rather than columns
  directly on `businesses`.
- `business_services` enrichment: extract service names only for now;
  leave pricing fields null unless/until pricing data is actually
  available from a source — don't invent prices.

**Phase 4 (D1 Upload):**
- Upload order (FK-safe): `states` → `regions` → `suburbs` → `businesses`
  → `business_features` / `business_hours` / `business_services` →
  `content` (content last, since business-level rows need `business.id`
  to already exist).
- Recompute `business_count` on `states`/`regions`/`suburbs` as part of
  the upload pass (a simple `COUNT` grouped by the relevant FK — no
  trigger needed, D1 doesn't have Postgres-style triggers for this
  anyway).

**Phase 5 (Astro template):**
- Routes: `[state]/[region]/index.astro`, `[state]/[region]/[suburb]/
  index.astro`, `[state]/[region]/[suburb]/[business].astro`.
- Every page level queries `content` for its EEAT blocks (`about`,
  `local_context`, `faq`, etc.) and renders them with the
  `{{placeholder}}` substitution described above, at request/build time —
  same pattern as the toilets site's `EeatContent.astro`.
- Follow the slug→id resolution pattern above on every page: resolve the
  slug chain to integer ids once, then join everything else on those ids.

---

## Explicitly out of scope for v1

- **`stats` table** — not planned. Ranking/comparison pages were a
  toilets-specific feature; revisit only if that becomes an actual goal.
- **`notes` table** — not needed.
- **Pricing on `business_services`** — the columns exist, but don't
  populate them until real pricing data is actually available from a
  source. Don't estimate or infer prices to fill the gap.
