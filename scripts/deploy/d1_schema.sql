-- D1 Schema for Directory Factory sites
-- One database per directory (per architecture decision in plan doc)
--
-- Tables:
--   site_config  — branding and configuration (read by the Astro template at build time)
--   businesses   — the core place/business records (parallels 'toilets' in toilets-near-me)
--   business_features — tags/features/attributes for each business
--   business_hours     — structured opening hours for each business
--   business_notes     — supplementary textual notes (editorial, address details)

-- ─── site_config ────────────────────────────────────────────────────────────
-- Single row (key/value-ish). Branding/config lives in the D1 database,
-- not in env vars or codebase (Phase 5 architecture decision).
CREATE TABLE IF NOT EXISTS site_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ─── businesses ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS businesses (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    slug               TEXT UNIQUE NOT NULL,       -- URL segment, e.g. "joe-s-grooming-and-spa"
    name               TEXT NOT NULL,               -- display name
    place_id           TEXT,                        -- original Google Place ID (for updates)
    primary_type       TEXT,                        -- e.g. "pet_store", "restaurant"
    business_status    TEXT,                        -- e.g. "OPERATIONAL"
    address            TEXT,                        -- full formatted address
    locality           TEXT,                        -- city/suburb
    state_code         TEXT,                        -- e.g. "NSW", "VIC"
    postal_code        TEXT,                        -- e.g. "2000"
    country            TEXT,                        -- e.g. "AU"
    lat                REAL,                        -- latitude
    lng                REAL,                        -- longitude
    phone              TEXT,                        -- national phone number (normalized)
    website            TEXT,                        -- business website URL
    rating             REAL,                        -- Google rating 0–5
    user_rating_count  INTEGER,                     -- number of reviews
    is_24_hours        INTEGER DEFAULT 0,           -- 0/1 boolean
    opening_hours_raw  TEXT,                        -- human-readable hours string
    opening_hours_note TEXT,                        -- additional hours note
    quality_score      INTEGER,                     -- 0–100 composite score from enrichment
    ai_generated       INTEGER DEFAULT 0,           -- 0/1 whether enrichment used AI
    data_completeness  INTEGER,                     -- 0–100 data richness score (cleaning)
    created_at         TEXT DEFAULT (CURRENT_TIMESTAMP),
    updated_at         TEXT DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX IF NOT EXISTS idx_businesses_slug       ON businesses(slug);
CREATE INDEX IF NOT EXISTS idx_businesses_place_id   ON businesses(place_id);
CREATE INDEX IF NOT EXISTS idx_businesses_locality   ON businesses(locality);
CREATE INDEX IF NOT EXISTS idx_businesses_quality    ON businesses(quality_score);

-- ─── business_features ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS business_features (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id   INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    feature_key   TEXT NOT NULL,                          -- e.g. "accessible", "child_friendly"
    source        TEXT NOT NULL                           -- e.g. "types", "accessibility", "pricing"
);

CREATE INDEX IF NOT EXISTS idx_features_business ON business_features(business_id);
CREATE INDEX IF NOT EXISTS idx_features_key      ON business_features(feature_key);

-- ─── business_hours ─────────────────────────────────────────────────────────
-- One row per (day_of_week × season) combination.
-- day_of_week: 0=Sunday, 1=Monday, ..., 6=Saturday (null = all days)
-- month_start/month_end: null = all year, else month number 1–12
-- open_mins/close_mins: minutes from midnight (0–1439, 1440 = midnight end-of-day)
CREATE TABLE IF NOT EXISTS business_hours (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id   INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    day_of_week   INTEGER,                              -- 0-6 (Sun-Sat), null = all days
    month_start   INTEGER,                              -- 1-12, null = all year
    month_end     INTEGER,                              -- 1-12, null = all year
    open_mins     INTEGER,                              -- minutes from midnight
    close_mins    INTEGER,                              -- minutes from midnight (1440 = end of day)
    is_24_hours   INTEGER DEFAULT 0,
    is_daylight   INTEGER DEFAULT 0,
    is_unknown    INTEGER DEFAULT 0,
    parse_status  TEXT,                                 -- "parsed" | "failed" | "unknown"
    raw_source    TEXT                                  -- original raw hours string for this entry
);

CREATE INDEX IF NOT EXISTS idx_hours_business  ON business_hours(business_id);
CREATE INDEX IF NOT EXISTS idx_hours_dow        ON business_hours(day_of_week);

-- ─── business_notes ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS business_notes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    business_id   INTEGER NOT NULL REFERENCES businesses(id) ON DELETE CASCADE,
    note_type     TEXT NOT NULL,                        -- e.g. "editorial", "address_detail"
    note          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_notes_business ON business_notes(business_id);
CREATE INDEX IF NOT EXISTS idx_notes_type     ON business_notes(note_type);

-- ─── enrichment_content (AI-generated content) ──────────────────────────────
-- Stores the AI-generated description, services, specialties, SEO fields.
CREATE TABLE IF NOT EXISTS enrichment_content (
    business_id    INTEGER PRIMARY KEY REFERENCES businesses(id) ON DELETE CASCADE,
    description    TEXT,                -- 2-3 sentences about the business
    services       TEXT,                -- JSON array of service strings
    specialties    TEXT,                -- JSON array of specialty strings
    seo_keywords   TEXT,                -- JSON array of SEO keyword strings
    seo_meta_desc  TEXT,                -- 150-160 char meta description
    ai_model       TEXT,                -- e.g. "gemini-2.5-flash-lite"
    generated_at   TEXT                 -- ISO timestamp of generation
);
