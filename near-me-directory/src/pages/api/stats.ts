/**
 * API endpoint for fetching pre-calculated statistics
 *
 * GET /api/stats?version=2024-q4     - Get specific version
 * GET /api/stats?version=latest       - Get latest version
 * GET /api/stats?metric=facilities_per_1000  - Get specific metric
 * GET /api/stats?entity_type=state    - Get all state stats
 */

import type { APIRoute } from 'astro';
import { getD1Client, runQuery } from '../../lib/d1';

interface StatsRow {
  entity_type: 'state' | 'region' | 'nation';
  entity_id: string | null;
  metric: string;
  rank: number | null;
  rank_of: number | null;
  value: number | null;
  metadata: Record<string, unknown>;
  source_version: string;
  generated_at: string;
  approved: boolean;
}

interface StatsResponse {
  version: string;
  stats: StatsRow[];
  count: number;
}

// Default version fallback
const DEFAULT_VERSION = '2024-q4';

export const GET: APIRoute = async ({ url, locals }) => {
  const db = getD1Client({ DB: (locals as any)?.DB });

  const version = url.searchParams.get('version') || DEFAULT_VERSION;
  const metric = url.searchParams.get('metric');
  const entityType = url.searchParams.get('entity_type');

  try {
    let sql = 'SELECT * FROM stats WHERE 1=1';
    const params: any[] = [];

    // Version filter
    if (version === 'latest') {
      // Get most recent version first
      const versions = await runQuery(db,
        'SELECT source_version FROM stats ORDER BY generated_at DESC LIMIT 1'
      );
      if (versions && versions.length > 0 && versions[0].source_version) {
        sql += ' AND source_version = ?';
        params.push(versions[0].source_version);
      }
    } else {
      sql += ' AND source_version = ?';
      params.push(version);
    }

    // Optional filters
    if (metric) {
      sql += ' AND metric = ?';
      params.push(metric);
    }
    if (entityType) {
      sql += ' AND entity_type = ?';
      params.push(entityType);
    }

    const rows = await runQuery(db, sql, params);

    const response: StatsResponse = {
      version: version,
      stats: rows || [],
      count: rows?.length || 0
    };

    return new Response(JSON.stringify(response), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 's-maxage=3600, stale-while-revalidate=300'
      }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: String(err) }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
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
