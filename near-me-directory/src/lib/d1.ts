/**
 * D1 Database client wrapper
 * Replaces Supabase client for Cloudflare D1
 * Provides a resilient data-fetching layer with graceful error handling
 */

import type { D1Database } from '@cloudflare/workers-types';

let d1: D1Database | null = null;

/**
 * Get the D1 database binding.
 * In Astro SSR/Server context, env comes from Astro.locals or getDBBinding().
 * In prerendered routes, callers pass the binding directly.
 */
export function getD1Client(env?: { DB?: D1Database }): D1Database {
  // 1. Explicit env passed by caller (SSR/API routes)
  if (env?.DB) {
    return env.DB;
  }
  // 2. Astro.locals (middleware / SSR)
  // 3. Cached singleton (non-Astro runtime, e.g. scripts)
  if (d1) {
    return d1;
  }
  // 4. Global binding (Cloudflare Workers runtime)
  //     @ts-ignore
  if (typeof DB !== 'undefined' && DB) {
    // @ts-ignore
    d1 = DB;
    return d1;
  }
  throw new Error('D1 database binding not available. Ensure DB binding is configured in wrangler.toml.');
}

/**
 * Set the D1 client manually (for non-Astro contexts or testing)
 */
export function setD1Client(db: D1Database): void {
  d1 = db;
}

/**
 * Run a query with automatic JSON result parsing
 */
export async function runQuery(
  db: D1Database,
  sql: string,
  params: any[] = []
): Promise<any[]> {
  const stmt = db.prepare(sql);
  const result = await stmt.bind(...params).all();
  return result.results || [];
}

/**
 * Run a query expecting a single row
 */
export async function runQuerySingle(
  db: D1Database,
  sql: string,
  params: any[] = []
): Promise<any | null> {
  const rows = await runQuery(db, sql, params);
  return rows.length > 0 ? rows[0] : null;
}

/**
 * Run a count query
 */
export async function runCount(
  db: D1Database,
  sql: string,
  params: any[] = []
): Promise<number> {
  const rows = await runQuery(db, sql, params);
  if (rows.length > 0) {
    const val = Object.values(rows[0])[0] as number;
    return val || 0;
  }
  return 0;
}
