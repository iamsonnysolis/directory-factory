/**
 * API endpoint for geolocation — Cloudflare Workers IP geo
 * Returns latitude/longitude from CF-IP-geo headers (instant, city-level accuracy)
 * Used for initial map positioning without user permission prompt
 */
import type { APIRoute } from 'astro';

/**
 * Cloudflare Workers provides geo headers:
 * - CF-IP-Country: AU (if Australian)
 * - CF-IP-Latitude: approximate lat
 * - CF-IP-Longitude: approximate lng
 */
export const GET: APIRoute = async ({ request }) => {
  // Try to get geo from Cloudflare headers
  const cfLat = request.headers.get('cf-ip-latitude');
  const cfLng = request.headers.get('cf-ip-longitude');
  const cfCountry = request.headers.get('cf-ip-country');

  if (cfLat && cfLng) {
    return new Response(JSON.stringify({
      available: true,
      latitude: parseFloat(cfLat),
      longitude: parseFloat(cfLng),
      country: cfCountry?.toLowerCase() || 'au',
      accuracy: 'ip',
    }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=60',
      },
    });
  }

  // Fallback: try to get from platform context (Cloudflare)
  // Note: In Astro SSR, we can also access via platform.context
  const url = new URL(request.url);
  const cfGeo = url.searchParams.get('cf_geo');

  // If no geo available, return unavailable
  return new Response(JSON.stringify({
    available: false,
  }), {
    status: 200,
    headers: {
      'Content-Type': 'application/json',
      'Cache-Control': 'public, max-age=60',
    },
  });
};

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