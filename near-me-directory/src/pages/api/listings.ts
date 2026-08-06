/**
 * API endpoint for fetching listings within a bounding box
 * Ultra-lightweight response for client-side map rendering with routing info
 *
 * Caching strategy:
 * - s-maxage=300: Served from Cloudflare edge cache for 5 minutes
 * - stale-while-revalidate=60: Serve stale while revalidating in background
 */

import type { APIRoute } from 'astro';
import { getD1Client, runQuery } from '../../lib/d1';

interface Env {
  DB: any;
}

/**
 * Response type for map markers with routing and feature data
 */
interface MapFacility {
  listing_id: string;
  name: string;
  latitude: number;
  longitude: number;
  slug: string;
  state_code: string;
  region_slug?: string;
  suburb_slug?: string;
  address?: string;
  is_open_24h: boolean;
}

/**
 * API Route: GET /api/listings?minLat=-34&maxLat=-33&minLng=150&maxLng=151
 * Returns listings within the specified bounding box
 */
export const GET: APIRoute = async ({ url, locals }) => {
  const db = getD1Client({ DB: (locals as any)?.DB });

  // Extract and parse bounding box parameters
  const minLatParam = url.searchParams.get('minLat');
  const maxLatParam = url.searchParams.get('maxLat');
  const minLngParam = url.searchParams.get('minLng');
  const maxLngParam = url.searchParams.get('maxLng');

  // Optional feature filter (comma-separated feature keys)
  const featuresParam = url.searchParams.get('features');
  const features = featuresParam?.split(',').filter(Boolean) ?? [];

  // Optional 24-hour filter
  const h24 = url.searchParams.get('h24') === '1';

  // Parse and validate coordinates
  const minLat = minLatParam ? parseFloat(minLatParam) : NaN;
  const maxLat = maxLatParam ? parseFloat(maxLatParam) : NaN;
  const minLng = minLngParam ? parseFloat(minLngParam) : NaN;
  const maxLng = maxLngParam ? parseFloat(maxLngParam) : NaN;

  // Validate all required parameters present and valid
  if ([minLat, maxLat, minLng, maxLng].some(isNaN)) {
    return new Response(
      JSON.stringify({ error: 'Invalid or missing bounds parameters' }),
      { status: 400, headers: { 'Content-Type': 'application/json' } }
    );
  }

  try {
    // Build SQL query with required columns for popup routing
    let sql = `
      SELECT listing_id, name, latitude, longitude, slug, state_code,
             region_slug, suburb_slug, address, is_open_24h
      FROM listings
      WHERE latitude >= ? AND latitude <= ?
        AND longitude >= ? AND longitude <= ?
    `;
    const params: any[] = [minLat, maxLat, minLng, maxLng];

    if (h24) {
      sql += ' AND is_open_24h = 1';
    }

    sql += ' LIMIT 200';

    const allRows: MapFacility[] = await runQuery(db, sql, params);

    // Feature filtering in JS (AND logic for multi-feature filters)
    let listings = allRows;
    if (features.length > 0) {
      const ids = listings.map((t) => t.listing_id);
      if (ids.length > 0) {
        const placeholders = ids.map(() => '?').join(',');
        const featRows = await runQuery(db,
          `SELECT listing_id, feature_key FROM features
           WHERE listing_id IN (${placeholders})
           AND feature_key IN (${features.map(() => '?').join(',')})`,
          [...ids, ...features]
        );

        const featureCounts: Record<string, number> = {};
        featRows.forEach((r: any) => {
          featureCounts[r.listing_id] = (featureCounts[r.listing_id] || 0) + 1;
        });

        // Keep only listings that have ALL requested features
        listings = listings.filter((t) => featureCounts[t.listing_id] === features.length);
      }
    }

    return new Response(JSON.stringify(listings), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=60, s-maxage=300, stale-while-revalidate=60',
      },
    });
  } catch (err) {
    console.error('[/api/listings] Unexpected error:', err);
    return new Response(
      JSON.stringify({ error: 'Internal server error' }),
      { status: 500, headers: { 'Content-Type': 'application/json' } }
    );
  }
};

/**
 * OPTIONS handler for CORS preflight
 */
export const OPTIONS: APIRoute = async () => {
  return new Response(null, {
    status: 204,
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET',
      'Access-Control-Allow-Headers': 'Content-Type',
    },
  });
};
