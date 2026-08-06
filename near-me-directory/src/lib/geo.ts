/**
 * Geographic utilities for FacilitiesNearMe V2
 * Ported from Next.js reference implementation
 */

// --- Australia defaults -------------------------------------------------------

/** Geographic centre of Australia - used as fallback when geolocation fails */
export const AUSTRALIA_CENTRE = { lat: -25.2744, lng: 133.7751 };

/** Default zoom level when showing all of Australia */
export const AUSTRALIA_ZOOM = 4;

/** Default zoom level when showing a suburb/location */
export const LOCATION_ZOOM = 14;

// --- Location Caching (sessionStorage with expiry) ------------------------------

/** Location cache expiry time - 4 hours in milliseconds */
export const LOCATION_CACHE_EXPIRY_MS = 4 * 60 * 60 * 1000;

/**
 * Stores user location in sessionStorage with timestamp.
 * Session-only storage respects privacy while providing UX continuity.
 */
export function cacheUserLocation(lat: number, lng: number): void {
  try {
    const cache = {
      lat,
      lng,
      timestamp: Date.now()
    };
    sessionStorage.setItem('tnm_user_location', JSON.stringify(cache));
  } catch (e) {
    // Silently fail if sessionStorage unavailable (private browsing, etc.)
  }
}

/**
 * Retrieves cached user location if still valid.
 * Returns null if expired (>4 hours) or not found.
 */
export function getCachedUserLocation(): { lat: number; lng: number } | null {
  try {
    const cached = sessionStorage.getItem('tnm_user_location');
    if (!cached) return null;
    
    const { lat, lng, timestamp } = JSON.parse(cached);
    const age = Date.now() - timestamp;
    
    if (age > LOCATION_CACHE_EXPIRY_MS) {
      sessionStorage.removeItem('tnm_user_location');
      return null;
    }
    
    return { lat, lng };
  } catch (e) {
    return null;
  }
}

/**
 * Clears cached user location.
 */
export function clearCachedUserLocation(): void {
  try {
    sessionStorage.removeItem('tnm_user_location');
  } catch (e) {
    // Silently fail
  }
}

// --- URL helpers ----------------------------------------------------------------

/**
 * Builds a Google Maps directions URL for the given destination.
 * Uses label if provided, otherwise falls back to lat/lng.
 */
export function getDirectionsUrl(lat: number, lng: number, label?: string): string {
  const dest = label
    ? encodeURIComponent(label)
    : `${lat},${lng}`;
  return `https://www.google.com/maps/dir/?api=1&destination=${dest}&destination_place_id=`;
}

/**
 * Builds an Apple Maps directions URL (iOS fallback).
 */
export function getAppleMapsUrl(lat: number, lng: number, label?: string): string {
  const name = label ? encodeURIComponent(label) : 'Listing';
  return `https://maps.apple.com/?daddr=${lat},${lng}&t=m&dirflg=d&q=${name}`;
}

// --- Distance helpers -----------------------------------------------------------

/**
 * Haversine distance between two lat/lng points in metres.
 * Use for rough client-side sorting - the DB RPC is authoritative for display.
 */
export function haversineDistanceM(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number,
): number {
  const R = 6_371_000; // Earth radius in metres
  const f1 = (lat1 * Math.PI) / 180;
  const f2 = (lat2 * Math.PI) / 180;
  const df = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lng2 - lng1) * Math.PI) / 180;

  const a =
    Math.sin(df / 2) * Math.sin(df / 2) +
    Math.cos(f1) * Math.cos(f2) * Math.sin(dl / 2) * Math.sin(dl / 2);

  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/**
 * Formats a distance in metres to a human-readable string.
 *
 * Examples:
 *   450   -> "450 m"
 *   1200  -> "1.2 km"
 *   15400 -> "15.4 km"
 */
export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres)} m`;
  const km = metres / 1000;
  return km < 10 ? `${km.toFixed(1)} km` : `${Math.round(km)} km`;
}