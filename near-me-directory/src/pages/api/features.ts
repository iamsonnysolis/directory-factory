/**
 * API endpoint for fetching features for listings
 * Returns a map of listing_id -> array of feature keys
 */

import type { APIRoute } from 'astro';
import { getD1Client, runQuery } from '../../lib/d1';

interface FeaturesMap {
  [listingId: string]: string[];
}

/**
 * API Route: GET /api/features?ids=123,456,789
 * Returns features map for the given listing IDs
 */
export const GET: APIRoute = async ({ url, locals }) => {
  const db = getD1Client({ DB: (locals as any)?.DB });
  const idsParam = url.searchParams.get('ids');

  if (!idsParam) {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // Parse listing IDs (convert to integers for query)
  const ids = idsParam.split(',').map(id => parseInt(id.trim())).filter(id => !isNaN(id));

  if (ids.length === 0) {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  try {
    const placeholders = ids.map(() => '?').join(',');
    const rows = await runQuery(db,
      `SELECT listing_id, feature_key FROM features WHERE listing_id IN (${placeholders})`,
      ids
    );

    // Build features map
    const featuresMap: FeaturesMap = {};
    rows.forEach((row: any) => {
      const id = String(row.listing_id);
      if (!featuresMap[id]) featuresMap[id] = [];
      featuresMap[id].push(row.feature_key);
    });

    return new Response(JSON.stringify(featuresMap), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=60, s-maxage=300, stale-while-revalidate=60',
      },
    });
  } catch (err) {
    console.error('[/api/features] Unexpected error:', err);
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
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
