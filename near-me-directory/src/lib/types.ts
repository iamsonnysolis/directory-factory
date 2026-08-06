/**
 * TypeScript types for FacilitiesNearMe V2
 * Canonical feature key definitions and filter state
 */

// Feature key constants - canonical list matching database feature_key values
// Source: src/lib/feature-icons.ts (single source of truth for features)
export const FEATURE_KEYS = [
  'accessible',
  'adult_change',
  'all_gender',
  'ambulant',
  'baby_care_room',
  'baby_change',
  'changing_places',
  'drinking_water',
  'dump_point',
  'female',
  'key_required',
  'lh_transfer',
  'male',
  'mens_pad_disposal',
  'mlak',
  'parking',
  'parking_accessible',
  'payment_required',
  'rh_transfer',
  'sanitary_disposal',
  'sharps_disposal',
  'shower',
  'unisex',
] as const;

export type FeatureKey = (typeof FEATURE_KEYS)[number];

// Note: Display labels are defined in src/lib/feature-icons.ts as FEATURE_LABELS
// Import from there for UI display to ensure consistency

// Convert snake_case to kebab-case for URLs
export function toKebabCase(snakeStr: string): string {
  return snakeStr.replace(/_/g, '-');
}

// Convert kebab-case back to snake_case for database queries
export function toSnakeCase(kebabStr: string): string {
  return kebabStr.replace(/-/g, '_');
}

// Active filter state
export interface FilterState {
  features: FeatureKey[];
  openNow: boolean;
  is24Hours: boolean;
}

export const DEFAULT_FILTERS: FilterState = {
  features: [],
  openNow: false,
  is24Hours: false,
};

// Map bounds
export interface MapBounds {
  north: number;
  south: number;
  east: number;
  west: number;
}

// Listing marker for map display
export interface FacilityMarker {
  listing_id: string;
  slug: string;
  name: string;
  address?: string;
  town?: string;
  latitude: number;
  longitude: number;
  is_open_24h: boolean;
  region_slug?: string;
  suburb_slug?: string;
  state_code?: string;
}