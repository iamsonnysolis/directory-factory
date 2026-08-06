/**
 * src/lib/content-utils.ts
 *
 * Replaces {{placeholder}} tokens in EEAT content with live values.
 * Ported from Next.js reference implementation.
 */

// -- Types ---------------------------------------------------------------------

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

export type PlaceholderValues = Record<string, string | number | undefined>;

export interface ResolvedContent {
  about?: string;
  local_context?: string;
  where_to_find?: string;
  accessibility?: string;
  tips?: string[];
  faq?: string[];
  meta_title?: string;
  meta_description?: string;
}

// -- Core resolver -------------------------------------------------------------

/**
 * Replace all {{key}} tokens with values. Unknown tokens are left as-is
 * so missing values are visible as {{key}} during development.
 */
export function resolvePlaceholders(
  text: string | null | undefined,
  values: PlaceholderValues,
): string {
  if (!text) return '';
  return text.replace(/\{\{([^}]+)\}\}/g, (_match, key: string) => {
    const val = values[key];
    return val !== undefined && val !== null ? String(val) : _match;
  });
}

/**
 * Resolve placeholders across all content rows for an entity and return
 * a typed object keyed by content_type.
 *
 * `tips` and `faq` are stored as JSON arrays -- parsed and resolved per item.
 */
export function resolveContent(
  rows: ContentRow[],
  values: PlaceholderValues,
): ResolvedContent {
  const result: ResolvedContent = {};

  for (const row of rows) {
    const ct = row.content_type as keyof ResolvedContent;

    if (ct === 'tips' || ct === 'faq') {
      try {
        const items: unknown = JSON.parse(row.body);
        (result as Record<string, string[]>)[ct] = Array.isArray(items)
          ? items.map((item) =>
              typeof item === 'string' ? resolvePlaceholders(item, values) : String(item),
            )
          : [];
      } catch {
        (result as Record<string, string[]>)[ct] = [];
      }
    } else {
      (result as Record<string, string>)[ct] = resolvePlaceholders(row.body, values);
    }
  }

  return result;
}

// -- Values builders -----------------------------------------------------------

interface StateRow {
  name: string;
  listing_count: number;
}

interface RegionRow {
  name_clean: string;
  listing_count: number;
}

interface SuburbRow {
  name: string;
  listing_count: number;
}

/**
 * Build placeholder values for state-level EEAT content.
 */
export function stateValues(state: StateRow, counts: FeatureCounts = {}): PlaceholderValues {
  const n = counts.accessible ?? 0;
  return {
    area_name: state.name,
    state_name: state.name,
    listing_count: state.listing_count ?? 0,
    accessible_count: n,
    accessible_pct: state.listing_count ? Math.round((n / state.listing_count) * 100) : 0,
    open_24h_count: counts.open_24h ?? 0,
    baby_change_count: counts.baby_change ?? 0,
    baby_care_room_count: counts.baby_care_room ?? 0,
    changing_places_count: counts.changing_places ?? 0,
    dump_point_count: counts.dump_point ?? 0,
    shower_count: counts.shower ?? 0,
    parking_count: counts.parking ?? 0,
    drinking_water_count: counts.drinking_water ?? 0,
  };
}

/**
 * Build placeholder values for region-level EEAT content.
 */
export function regionValues(
  region: RegionRow,
  state: StateRow,
  counts: FeatureCounts = {},
): PlaceholderValues {
  const n = counts.accessible ?? 0;
  return {
    area_name: region.name_clean,
    region_name: region.name_clean,
    state_name: state.name,
    listing_count: region.listing_count ?? 0,
    accessible_count: n,
    accessible_pct: region.listing_count ? Math.round((n / region.listing_count) * 100) : 0,
    open_24h_count: counts.open_24h ?? 0,
    baby_change_count: counts.baby_change ?? 0,
    baby_care_room_count: counts.baby_care_room ?? 0,
    changing_places_count: counts.changing_places ?? 0,
    dump_point_count: counts.dump_point ?? 0,
    shower_count: counts.shower ?? 0,
    parking_count: counts.parking ?? 0,
    drinking_water_count: counts.drinking_water ?? 0,
  };
}

/**
 * Build placeholder values for suburb-level EEAT content.
 */
export function suburbValues(
  suburb: SuburbRow,
  state: StateRow,
  region: RegionRow | null,
  counts: FeatureCounts = {},
): PlaceholderValues {
  const n = counts.accessible ?? 0;
  return {
    area_name: suburb.name,
    suburb_name: suburb.name,
    state_name: state.name,
    region_name: region?.name_clean ?? '',
    listing_count: suburb.listing_count ?? 0,
    accessible_count: n,
    accessible_pct: suburb.listing_count ? Math.round((n / suburb.listing_count) * 100) : 0,
    open_24h_count: counts.open_24h ?? 0,
    baby_change_count: counts.baby_change ?? 0,
    baby_care_room_count: counts.baby_care_room ?? 0,
    changing_places_count: counts.changing_places ?? 0,
    dump_point_count: counts.dump_point ?? 0,
    shower_count: counts.shower ?? 0,
    parking_count: counts.parking ?? 0,
    drinking_water_count: counts.drinking_water ?? 0,
  };
}