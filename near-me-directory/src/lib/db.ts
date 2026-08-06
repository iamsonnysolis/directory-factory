/**
 * Database utilities for near-me-directory
 * D1-based data fetching with graceful error handling
 * All queries use parameterized SQL on Cloudflare D1
 */

import { getD1Client, runQuery, runQuerySingle, runCount } from './d1';
import type { D1Database } from '@cloudflare/workers-types';

// Types for database records
export interface ListingRecord {
  listing_id: string;
  slug: string;
  name: string;
  address?: string;
  town?: string;
  state_code?: string;
  suburb_slug?: string;
  region_slug?: string;
  latitude?: number;
  longitude?: number;
  is_open_24h?: boolean;
  opening_hours_note?: string;
}

export interface StateRecord {
  code: string;
  name: string;
  slug: string;
  listing_count?: number;
}

export interface RegionRecord {
  id: string;
  name: string;
  slug: string;
  state_code: string;
  listing_count: number;
  name_clean?: string;
}

export interface SuburbRecord {
  id: string;
  name: string;
  slug: string;
  state_code: string;
  listing_count: number;
  latitude?: number;
  longitude?: number;
}

export interface FeatureRecord {
  listing_id: string;
  feature_key: string;
}

export interface HourRow {
  day_of_week: number | null;
  month_start: number | null;
  month_end: number | null;
  open_mins: number | null;
  close_mins: number | null;
  is_open_24h: boolean;
  is_daylight: boolean;
  is_unknown: boolean;
}

export interface NoteRecord {
  note_type: string;
  note: string;
}

export interface NearbyListingRecord {
  listing_id: string;
  slug: string;
  name: string;
  suburb?: string;
  suburb_slug?: string;
  region_slug?: string;
  state_code?: string;
  state?: string;
  distance_m: number;
}

export interface ContentRow {
  content_type: string;
  body: string;
}

export interface FeatureCounts {
  accessible?: number;
  open_24h?: number;
  baby_change?: number;
  baby_care_room?: number;
  changing_places?: number;
  dump_point?: number;
  shower?: number;
  parking?: number;
  drinking_water?: number;
}

/**
 * Fetches all data required for a listing detail page
 * All secondary queries are wrapped in try/catch to prevent build failures
 */
export async function fetchListingDetailData(params: {
  state: string;
  region: string;
  suburb: string;
  listing: string;
}, env?: { DB?: D1Database }) {
  const { state, region, suburb, listing } = params;
  const stateCode = state.toUpperCase();

  const db = getD1Client(env);

  // Primary fetch - the listing itself
  const listingData = await runQuerySingle(db,
    `SELECT * FROM listings WHERE slug = ? AND suburb_slug = ? AND region_slug = ? LIMIT 1`,
    [listing, suburb, region]
  );

  if (!listingData || listingData.state_code !== stateCode) {
    return null;
  }

  // Parallel secondary fetches with error handling
  const [stateResult, regionResult, suburbResult] = await Promise.all([
    runQuerySingle(db, 'SELECT code, name, slug FROM states WHERE code = ? LIMIT 1', [stateCode]),
    runQuerySingle(db, 'SELECT id, name, slug, state_code, listing_count, name_clean FROM regions WHERE slug = ? AND state_code = ? LIMIT 1', [region, stateCode]),
    runQuerySingle(db, 'SELECT id, name, slug, state_code, listing_count FROM suburbs WHERE slug = ? AND state_code = ? LIMIT 1', [suburb, stateCode]),
  ]);

  // Feature, hours, and notes fetch with error handling
  let features: FeatureRecord[] | null = null;
  let hours: HourRow[] | null = null;
  let notes: NoteRecord[] | null = null;
  try {
    [features, hours, notes] = await Promise.all([
      runQuery(db, 'SELECT listing_id, feature_key FROM features WHERE listing_id = ?', [listingData.listing_id]),
      runQuery(db, 'SELECT day_of_week, month_start, month_end, open_mins, close_mins, is_open_24h, is_daylight, is_unknown FROM hours WHERE listing_id = ? ORDER BY day_of_week', [listingData.listing_id]),
      runQuery(db, 'SELECT note_type, note FROM notes WHERE listing_id = ?', [listingData.listing_id]),
    ]);
  } catch (err) {
    console.warn('Feature/hours/notes fetch failed:', err);
  }

  // Nearby listings via SQL (replaces RPC find_nearby_listings)
  let nearbyListings: NearbyListingRecord[] = [];
  if (listingData.latitude && listingData.longitude) {
    try {
      // Haversine formula for distance calculation in D1
      const nearby = await runQuery(db, `
        SELECT listing_id, slug, name, suburb, suburb_slug, region_slug, state_code, state,
          CAST(
            6371000 * acos(
              cos(radians(?)) * cos(radians(latitude)) * cos(radians(longitude) - radians(?)) +
              sin(radians(?)) * sin(radians(latitude))
            ) AS INTEGER
          ) AS distance_m
        FROM listings
        WHERE listing_id != ?
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY distance_m ASC
        LIMIT 5
      `, [listingData.latitude, listingData.longitude, listingData.latitude, listingData.listing_id]);

      nearbyListings = (nearby || []) as NearbyListingRecord[];
    } catch (err) {
      console.warn('Nearby listings fetch failed:', err);
    }
  }

  return {
    listing: listingData as ListingRecord,
    state: stateResult as StateRecord | null,
    region: regionResult as RegionRecord | null,
    suburb: suburbResult as SuburbRecord | null,
    features,
    hours,
    notes,
    nearbyListings,
    stateSlug: state.toLowerCase(),
    stateCode,
  };
}

/**
 * Fetches data for state listing pages
 */
export async function fetchStateData(state: string, env?: { DB?: D1Database }) {
  const stateCode = state.toUpperCase();
  const db = getD1Client(env);

  const stateData = await runQuerySingle(db,
    'SELECT code, name, slug, listing_count FROM states WHERE code = ? LIMIT 1',
    [stateCode]
  );

  const regions = await runQuery(db,
    'SELECT id, name, slug, state_code, listing_count, name_clean FROM regions WHERE state_code = ? ORDER BY name_clean',
    [stateCode]
  );

  return {
    state: stateData as StateRecord | null,
    regions: (regions || []) as RegionRecord[],
    stateSlug: state.toLowerCase(),
  };
}

/**
 * Fetches data for region listing pages
 */
export async function fetchRegionData(state: string, region: string, env?: { DB?: D1Database }) {
  const stateCode = state.toUpperCase();
  const db = getD1Client(env);

  const [stateResult, regionResult] = await Promise.all([
    runQuerySingle(db, 'SELECT code, name, slug, listing_count FROM states WHERE code = ? LIMIT 1', [stateCode]),
    runQuerySingle(db, 'SELECT id, name, slug, state_code, listing_count, name_clean FROM regions WHERE slug = ? AND state_code = ? LIMIT 1', [region, stateCode]),
  ]);

  const suburbs = await runQuery(db,
    'SELECT id, name, slug, state_code, listing_count, latitude, longitude FROM suburbs WHERE state_code = ? AND region_slug = ? ORDER BY name',
    [stateCode, region]
  );

  return {
    state: stateResult as StateRecord | null,
    region: regionResult as RegionRecord | null,
    suburbs: (suburbs || []) as SuburbRecord[],
    stateSlug: state.toLowerCase(),
  };
}

/**
 * Fetches data for suburb listing pages
 */
export async function fetchSuburbData(state: string, region: string, suburb: string, env?: { DB?: D1Database }) {
  const stateCode = state.toUpperCase();
  const db = getD1Client(env);

  const [stateResult, regionResult, suburbResult] = await Promise.all([
    runQuerySingle(db, 'SELECT code, name, slug, listing_count FROM states WHERE code = ? LIMIT 1', [stateCode]),
    runQuerySingle(db, 'SELECT id, name, slug, state_code, listing_count, name_clean FROM regions WHERE slug = ? AND state_code = ? LIMIT 1', [region, stateCode]),
    runQuerySingle(db, 'SELECT id, name, slug, state_code, listing_count FROM suburbs WHERE slug = ? AND state_code = ? LIMIT 1', [suburb, stateCode]),
  ]);

  const listings = await runQuery(db,
    'SELECT listing_id, slug, name, address, town, latitude, longitude, is_open_24h FROM listings WHERE state_code = ? AND region_slug = ? AND suburb_slug = ? ORDER BY name',
    [stateCode, region, suburb]
  );

  return {
    state: stateResult as StateRecord | null,
    region: regionResult as RegionRecord | null,
    suburb: suburbResult as SuburbRecord | null,
    listings: (listings || []) as ListingRecord[],
    stateSlug: state.toLowerCase(),
  };
}

/**
 * Fetches EEAT content blocks for a state/region/suburb
 */
export async function fetchContent(entityType: string, entityId: string, env?: { DB?: D1Database }): Promise<ContentRow[]> {
  const db = getD1Client(env);
  const rows = await runQuery(db,
    'SELECT content_type, body FROM content WHERE entity_type = ? AND entity_id = ? AND approved = 1',
    [entityType, entityId]
  );
  return (rows || []) as ContentRow[];
}

/**
 * Fetches feature counts for a state (for EEAT placeholder resolution)
 */
export async function fetchStateFeatureCounts(stateCode: string, env?: { DB?: D1Database }): Promise<FeatureCounts> {
  const db = getD1Client(env);
  const featureKeys = ['accessible', 'baby_change', 'baby_care_room', 'changing_places', 'dump_point', 'shower', 'parking', 'drinking_water'];

  const results = await Promise.all([
    ...featureKeys.map((key) =>
      runCount(db, 'SELECT COUNT(*) as cnt FROM features WHERE state_code = ? AND feature_key = ?', [stateCode.toUpperCase(), key])
        .then((count) => ({ key, count }))
    ),
    runCount(db, 'SELECT COUNT(*) as cnt FROM listings WHERE state_code = ? AND is_open_24h = 1', [stateCode.toUpperCase()])
      .then((count) => ({ key: 'open_24h', count })),
  ]);

  const map: Record<string, number> = {};
  for (const r of results) map[r.key] = r.count;

  return {
    accessible: map['accessible'] ?? 0,
    open_24h: map['open_24h'] ?? 0,
    baby_change: map['baby_change'] ?? 0,
    baby_care_room: map['baby_care_room'] ?? 0,
    changing_places: map['changing_places'] ?? 0,
    dump_point: map['dump_point'] ?? 0,
    shower: map['shower'] ?? 0,
    parking: map['parking'] ?? 0,
    drinking_water: map['drinking_water'] ?? 0,
  };
}

/**
 * Fetches feature counts for a region (for EEAT placeholder resolution)
 */
export async function fetchRegionFeatureCounts(regionSlug: string, stateCode: string, env?: { DB?: D1Database }): Promise<FeatureCounts> {
  const db = getD1Client(env);
  const featureKeys = ['accessible', 'baby_change', 'baby_care_room', 'changing_places', 'dump_point', 'shower', 'parking', 'drinking_water'];

  const results = await Promise.all([
    ...featureKeys.map((key) =>
      runCount(db, 'SELECT COUNT(*) as cnt FROM features WHERE state_code = ? AND region_slug = ? AND feature_key = ?', [stateCode.toUpperCase(), regionSlug, key])
        .then((count) => ({ key, count }))
    ),
    runCount(db, 'SELECT COUNT(*) as cnt FROM listings WHERE state_code = ? AND region_slug = ? AND is_open_24h = 1', [stateCode.toUpperCase(), regionSlug])
      .then((count) => ({ key: 'open_24h', count })),
  ]);

  const map: Record<string, number> = {};
  for (const r of results) map[r.key] = r.count;

  return {
    accessible: map['accessible'] ?? 0,
    open_24h: map['open_24h'] ?? 0,
    baby_change: map['baby_change'] ?? 0,
    baby_care_room: map['baby_care_room'] ?? 0,
    changing_places: map['changing_places'] ?? 0,
    dump_point: map['dump_point'] ?? 0,
    shower: map['shower'] ?? 0,
    parking: map['parking'] ?? 0,
    drinking_water: map['drinking_water'] ?? 0,
  };
}

/**
 * Fetches listings for a region (for map markers on region pages)
 */
export async function fetchRegionListings(stateCode: string, regionSlug: string, env?: { DB?: D1Database }): Promise<ListingRecord[]> {
  const db = getD1Client(env);
  const listings = await runQuery(db,
    'SELECT listing_id, slug, name, address, latitude, longitude, is_open_24h, region_slug, suburb_slug, state_code FROM listings WHERE state_code = ? AND region_slug = ? ORDER BY name',
    [stateCode.toUpperCase(), regionSlug]
  );
  return (listings || []) as ListingRecord[];
}

/**
 * Fetches listings for a state (for map markers on state pages - limited for performance)
 */
export async function fetchStateListings(stateCode: string, limit: number = 100, env?: { DB?: D1Database }): Promise<ListingRecord[]> {
  const db = getD1Client(env);
  const listings = await runQuery(db,
    'SELECT listing_id, slug, name, address, latitude, longitude, is_open_24h, region_slug, suburb_slug, state_code FROM listings WHERE state_code = ? ORDER BY name LIMIT ?',
    [stateCode.toUpperCase(), limit]
  );
  return (listings || []) as ListingRecord[];
}

/**
 * Fetches listings for a state filtered by feature key
 * Used for state-level feature-filter pages
 */
export async function fetchStateListingsByFeature(stateCode: string, featureKey: string, env?: { DB?: D1Database }): Promise<ListingRecord[]> {
  const db = getD1Client(env);

  // Get listings with this feature using a JOIN
  const listings = await runQuery(db, `
    SELECT DISTINCT l.listing_id, l.slug, l.name, l.address, l.town, l.latitude, l.longitude, l.is_open_24h, l.region_slug, l.suburb_slug, l.state_code
    FROM listings l
    INNER JOIN features f ON f.listing_id = l.listing_id
    WHERE l.state_code = ? AND f.feature_key = ?
    ORDER BY l.name
  `, [stateCode.toUpperCase(), featureKey.toLowerCase()]);

  return (listings || []) as ListingRecord[];
}

/**
 * Fetches listings for a region filtered by feature key
 * Used for region-level feature-filter pages
 */
export async function fetchRegionListingsByFeature(stateCode: string, regionSlug: string, featureKey: string, env?: { DB?: D1Database }): Promise<ListingRecord[]> {
  const db = getD1Client(env);

  const listings = await runQuery(db, `
    SELECT DISTINCT l.listing_id, l.slug, l.name, l.address, l.town, l.latitude, l.longitude, l.is_open_24h, l.region_slug, l.suburb_slug, l.state_code
    FROM listings l
    INNER JOIN features f ON f.listing_id = l.listing_id
    WHERE l.state_code = ? AND l.region_slug = ? AND f.feature_key = ?
    ORDER BY l.name
  `, [stateCode.toUpperCase(), regionSlug, featureKey.toLowerCase()]);

  return (listings || []) as ListingRecord[];
}

/**
 * Fetches listings for a suburb filtered by feature key
 * Used for suburb-level feature-filter pages
 */
export async function fetchSuburbListingsByFeature(stateCode: string, regionSlug: string, suburbSlug: string, featureKey: string, env?: { DB?: D1Database }): Promise<ListingRecord[]> {
  const db = getD1Client(env);

  const listings = await runQuery(db, `
    SELECT DISTINCT l.listing_id, l.slug, l.name, l.address, l.town, l.latitude, l.longitude, l.is_open_24h, l.region_slug, l.suburb_slug, l.state_code
    FROM listings l
    INNER JOIN features f ON f.listing_id = l.listing_id
    WHERE l.state_code = ? AND l.region_slug = ? AND l.suburb_slug = ? AND f.feature_key = ?
    ORDER BY l.name
  `, [stateCode.toUpperCase(), regionSlug, suburbSlug, featureKey.toLowerCase()]);

  return (listings || []) as ListingRecord[];
}

/**
 * Fetches feature counts for a suburb (for EEAT placeholder resolution)
 * Also used to determine which feature-filter URLs to include in sitemap
 */
export async function fetchSuburbFeatureCounts(stateCode: string, regionSlug: string, suburbSlug: string, env?: { DB?: D1Database }): Promise<FeatureCounts> {
  const db = getD1Client(env);
  const featureKeys = ['accessible', 'baby_change', 'baby_care_room', 'changing_places', 'dump_point', 'shower', 'parking', 'drinking_water'];

  const results = await Promise.all([
    ...featureKeys.map((key) =>
      runCount(db, 'SELECT COUNT(*) as cnt FROM features WHERE state_code = ? AND region_slug = ? AND suburb_slug = ? AND feature_key = ?', [stateCode.toUpperCase(), regionSlug, suburbSlug, key])
        .then((count) => ({ key, count }))
    ),
    runCount(db, 'SELECT COUNT(*) as cnt FROM listings WHERE state_code = ? AND region_slug = ? AND suburb_slug = ? AND is_open_24h = 1', [stateCode.toUpperCase(), regionSlug, suburbSlug])
      .then((count) => ({ key: 'open_24h', count })),
  ]);

  const map: Record<string, number> = {};
  for (const r of results) map[r.key] = r.count;

  return {
    accessible: map['accessible'] ?? 0,
    open_24h: map['open_24h'] ?? 0,
    baby_change: map['baby_change'] ?? 0,
    baby_care_room: map['baby_care_room'] ?? 0,
    changing_places: map['changing_places'] ?? 0,
    dump_point: map['dump_point'] ?? 0,
    shower: map['shower'] ?? 0,
    parking: map['parking'] ?? 0,
    drinking_water: map['drinking_water'] ?? 0,
  };
}

/**
 * Legacy alias — returns the D1 database binding.
 * Kept for backward compatibility with callers that used getDBClient()
 * during the Supabase era. All new code should prefer getD1Client() from ./d1.
 */
export function getDBClient(env?: { DB?: D1Database }): D1Database {
  return getD1Client(env);
}
