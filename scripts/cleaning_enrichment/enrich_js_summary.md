# Phase 2.1 — `enrich.js` Plain-English Summary

Source: `OLD_TOILETSNEARME_DATA_PATH/enrich.js` (794 lines)
Target: `scripts/cleaning_enrichment/cleaning.py`

## What it does

`enrich.js` is the **cleaning + preparation** step (Step 1 of 2). It reads a raw
CSV export from the ABS National Public Toilet Map (via `data/datasets/`) and a
shapefile of LGA boundaries (via `data/LGA_2025_AUST_GDA2020/`), then writes
structured JSON to `data/output-YYYY-MM-DD/`.

**Pipeline stages (in `main()`):**

1. **Load CSV** — `loadCSV()` streams the CSV through `csv-parser`, strips BOM
   and trims headers. Returns an array of plain-string row objects.
2. **Load shapefile (optional, cached)** — `loadShapefile()` reads LGA polygons,
   converts geometry to WKT, maps ABS state codes to state codes/names, cleans
   region names, generates unique slugs (deduped with numeric suffixes), and
   caches to `output-regions-cache/regions.json`.
3. **Build entities** — `buildStates()`, `buildSuburbs()`, `buildToilets()`:
   - **States**: unique state codes from CSV rows, mapped to names + slugs.
   - **Suburbs**: grouped by `slugify(town)-state` key, centroid-computed
     from lat/lng averages, `toilet_count` = 0 (filled later).
   - **Toilets**: one row per FacilityID with cleaned fields, validated
     coordinates (Australian bounds check), slug deduped per-suburb.
4. **Assign regions** — `assignRegions()` runs point-in-polygon (with
   near-boundary fallback) to tag every toilet + suburb with a `region_slug`.
5. **Build features / notes / hours** — extracts boolean feature flags, note
   text, and parsed opening hours from each CSV row.
6. **Compute toilet counts** — aggregates per state, region, suburb.
7. **Write output** — states.json, regions.json, suburbs.json, toilets.json,
   features.json, notes.json, hours.json, metadata.json.

## Cleaning steps (the reusable logic → `clean_place()`)

### 1. Slug generation (`slugify`)
- Lowercase → NFD normalize → strip combining diacritical marks (0300–036F) →
  keep only `[a-z0-9\s-]` → trim → collapse whitespace/underscores to `-` →
  collapse multiple hyphens to single → strip leading/trailing hyphens.
- Used for: state slugs, suburb slugs, region slugs, toilet name slugs.

### 2. Text cleaning (`cleanText`)
- If empty/whitespace-only → `null`.
- Otherwise: collapse `\r\n` sequences to single space, collapse 2+ spaces to
  one, trim.

### 3. Boolean parsing (`parseBool`)
- `'true'` (case-insensitive, trimmed) → `true`; everything else → `false`.

### 4. Coordinate parsing (`parseCoord`)
- `parseFloat(val)` → if `NaN`, return `null`.

### 5. Coordinate validation (`isValidCoord`)
- Australian bounding box: lat `-44` to `-10`, lng `112` to `155`.

### 6. 24-hour detection (`is24Hours`)
- Raw value containing `'24 hour'` (case-insensitive) → `true`.

### 7. Opening hours parsing (`parseOpeningHours` from `parse-hours.js`)
- Delegates to the separate `parse-hours.js` module (280 lines).
- Handles: `OPEN: 24 hours`, `OPEN: Daylight hours`, `OPEN: 9am-5pm`,
  `Mon-Fri 8am-6pm, Sat 9am-1pm`, season prefixes (`Jun-Nov`), split days,
  multi-slot days, next-day overflow times, unknown/closed statuses.
- Returns one row per (day_of_week, month_start, month_end, open_mins,
  close_mins) with parse status + raw_source.

### 8. CSV column → feature key mapping (`CSV_TO_FEATURE`)
- Maps 21 CSV column names to internal feature keys (e.g. `Male` → `male`,
  `Parking` → `parking`, `ChangingPlaces` → `changing_places`).

### 9. CSV column → note type mapping (`NOTE_FIELDS`)
- Maps 6 note columns to note_type keys (e.g. `ToiletNote` → `toilet`,
  `AccessNote` → `access`).

## How `clean_place()` maps

In the directory factory context, `clean_place(raw_json)` receives a **Google
Places API response** (stored as `raw_json` in the `places` table), not a CSV
row. The equivalent cleaning steps are:

| `enrich.js` function | `clean_place()` equivalent |
|---|---|
| `slugify(name)` | slug generation from `displayName.text` |
| `cleanText(value)` | text normalization for address, phone, etc. |
| `parseBool(value)` | feature/flag extraction from `types` array |
| `parseCoord(lat)` | coordinate extraction from `location.lat/lng` |
| N/A (always valid) | coordinate validation (Google returns valid coords) |
| `is24Hours(openingHours)` | opening hours 24h flag from `regularOpeningHours` |
| `parseOpeningHours(raw)` | opening hours structured parsing (adapted format) |
| `CSV_TO_FEATURE` map | derive features from `types` + `accessibilityOptions` |
| `NOTE_FIELDS` map | notes extraction from `adrFormatAddress`, business status |
