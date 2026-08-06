import { getD1Client, runQuery, runQuerySingle } from './d1';
import type { D1Database } from '@cloudflare/workers-types';

// ─── Types ────────────────────────────────────────────────────────────────

export type EntityType = 'state' | 'region' | 'nation';

export interface StatRow {
  value: number | null;
  rank: number | null;
  rank_of: number | null;
  metadata: Record<string, any>;
  source_version: string;
}

export type StatsMap = Record<string, StatRow>;

export interface RankingRow {
  entity_id: string;
  value: number | null;
  rank: number | null;
  rank_of: number | null;
  metadata: Record<string, any>;
}

// nation rows use this sentinel entity_id (schema decision, Phase 1).
// Rows generated before this change used entity_id = null — getEntityStatsByVersion
// falls back to that for old versions so historical links don't silently 404.
export const NATION_ENTITY_ID = 'au';

// ─── Internal helpers ───────────────────────────────────────────────────────

function toStatsMap(rows: any[]): StatsMap {
  return Object.fromEntries(
    rows.map((r) => [
      r.metric,
      { value: r.value, rank: r.rank, rank_of: r.rank_of, metadata: r.metadata, source_version: r.source_version },
    ])
  );
}

// Given rows spanning multiple source_versions (no version filter was applied),
// keep only the rows belonging to the newest version. Rows must be pre-sorted
// with source_version descending, or this re-sorts defensively.
function keepLatestVersion<T extends { source_version: string }>(rows: T[]): T[] {
  if (rows.length === 0) return rows;
  const latest = rows.reduce((max, r) => (r.source_version > max ? r.source_version : max), rows[0].source_version);
  return rows.filter((r) => r.source_version === latest);
}

// ─── Single-entity stats (state page, region page, nation/homepage) ───────

// Get all metrics for one entity, at the latest approved version by default,
// or a specific historical version if `version` is provided.
export async function getEntityStats(
  entityType: EntityType,
  entityId: string | null = null,
  version?: string
): Promise<StatsMap> {
  const db = getD1Client();
  if (!db) return {};

  const approved = true;

  let sql = `
    SELECT metric, value, rank, rank_of, metadata, source_version
    FROM stats
    WHERE entity_type = ? AND approved = ?
  `;
  const params: any[] = [entityType, approved];

  if (entityId === null) {
    sql += ' AND entity_id IS NULL';
  } else {
    sql += ' AND entity_id = ?';
    params.push(entityId);
  }

  if (version) {
    sql += ' AND source_version = ?';
    params.push(version);
  } else {
    sql += ' ORDER BY source_version DESC';
  }

  const rows = await runQuery(db, sql, params);
  if (!rows || rows.length === 0) {
    // Nation rows generated before the entity_id migration used `null` instead
    // of 'au'. If a historical version lookup for nation comes back empty,
    // retry once against the legacy null entity_id.
    if (entityType === 'nation' && entityId === NATION_ENTITY_ID) {
      return getEntityStats(entityType, null, version);
    }
    return {};
  }

  return toStatsMap(keepLatestVersion(rows as any[]));
}

// Convenience wrapper: nation stats, latest version (or a specific historical one).
export async function getNationStats(version?: string): Promise<StatsMap> {
  return getEntityStats('nation', NATION_ENTITY_ID, version);
}

// Explicit historical lookup — kept for backward compatibility with existing
// callers; behaves identically to getEntityStats(entityType, entityId, version).
export async function getEntityStatsByVersion(
  entityType: EntityType,
  entityId: string | null,
  version: string
): Promise<StatsMap> {
  return getEntityStats(entityType, entityId, version);
}

// ─── Cross-entity rankings (comparison tables, feature pages) ─────────────

// Get all entities of one type ranked by a single metric, at the latest
// approved version. `stateCode` optionally scopes region rankings to one
// state (e.g. "top regions in NSW" on a state page).
export async function getEntityRankings(
  entityType: EntityType,
  metric: string,
  opts: { stateCode?: string } = {}
): Promise<RankingRow[]> {
  const db = getD1Client();
  if (!db) return [];

  let sql = `
    SELECT entity_id, value, rank, rank_of, metadata, source_version
    FROM stats
    WHERE entity_type = ?
      AND metric = ?
      AND approved = true
    ORDER BY source_version DESC, rank ASC
  `;
  const params: any[] = [entityType, metric];

  const rows = await runQuery(db, sql, params);
  if (!rows || rows.length === 0) return [];

  let result = keepLatestVersion(rows as any[]);

  if (opts.stateCode) {
    const wanted = opts.stateCode.toLowerCase();
    result = result.filter((r: any) => (r.metadata?.state_code ?? '').toLowerCase() === wanted);
  }

  return result.map((r: any) => ({
    entity_id: r.entity_id,
    value: r.value,
    rank: r.rank,
    rank_of: r.rank_of,
    metadata: r.metadata,
  }));
}

// Backward-compatible name used by existing feature pages.
export async function getStateRankings(metric: string): Promise<RankingRow[]> {
  return getEntityRankings('state', metric);
}

export async function getRegionRankings(metric: string, stateCode?: string): Promise<RankingRow[]> {
  return getEntityRankings('region', metric, { stateCode });
}

// ─── Version history ───────────────────────────────────────────────────────

// Get all available data versions for the history section, newest first.
export async function getAvailableVersions(): Promise<string[]> {
  const db = getD1Client();
  if (!db) return [];

  const rows = await runQuery(db,
    `SELECT source_version FROM stats WHERE entity_type = 'nation' AND metric = 'listing_count' ORDER BY source_version DESC`
  );

  if (!rows || rows.length === 0) return [];

  // dedupe defensively — should already be one row per version
  return Array.from(new Set(rows.map((r: any) => r.source_version)));
}
