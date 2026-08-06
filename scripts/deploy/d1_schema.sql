-- ============================================================
-- D1 Schema for Directory Factory sites
-- Based on Data-Model-Spec.md (authoritative D1 schema, created 2026-08-05)
-- One database per directory site
-- ============================================================

-- GEOGRAPHY

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

-- CORE ENTITY

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

-- FEATURES / HOURS

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

-- SERVICES — with pricing fields, ready for whenever pricing
-- data becomes available (not required to be populated now)

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

-- CONTENT (EEAT)

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

-- SITE CONFIG

CREATE TABLE site_config (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,
    value TEXT,
    value_type TEXT NOT NULL DEFAULT 'text' CHECK (value_type IN ('text','number','boolean','json')),
    config_group TEXT NOT NULL DEFAULT 'general',   -- 'general' | 'appearance' | 'contact' | 'legal' | 'seo'
    is_public INTEGER NOT NULL DEFAULT 1,           -- exposed to the Astro frontend, vs. internal-only
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
