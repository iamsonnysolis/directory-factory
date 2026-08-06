/**
 * API endpoint for checking if listings are open now
 * Returns open status map for listing IDs
 *
 * Params: ids=1,2,3&dow=0&month=3&mins=540
 * - dow: day of week (0=Monday, 6=Sunday) in user's local time
 * - month: current month (1-12) in user's local time
 * - mins: minutes from midnight in user's local time
 */
import type { APIRoute } from 'astro';
import { getD1Client, runQuery } from '../../lib/d1';
import { getDaylightHoursMinutes } from '../../lib/daylight-hours';

interface OpenStatusMap {
  [listingId: string]: { isOpen: boolean; label: string } | null;
}

/** Format minutes-from-midnight as "6am", "6:30pm" etc. */
function minsToTimeLabel(mins: number): string {
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  const period = h < 12 ? 'am' : 'pm';
  const hour = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return m === 0 ? `${hour}${period}` : `${hour}:${String(m).padStart(2, '0')}${period}`;
}

/** True if current month is within a seasonal range (supports wraparound e.g. Oct-Mar) */
function monthInSeason(month: number, monthStart: number | null, monthEnd: number | null): boolean {
  if (monthStart === null || monthEnd === null) return true;
  if (monthStart <= monthEnd) return month >= monthStart && month <= monthEnd;
  // Wraparound: e.g. Oct(10)--Mar(3)
  return month >= monthStart || month <= monthEnd;
}

/**
 * API Route: GET /api/open-status?ids=1,2,3&dow=0&month=3&mins=540
 * Returns open status for each listing based on user's local time
 */
export const GET: APIRoute = async ({ url, locals }) => {
  const db = getD1Client({ DB: (locals as any)?.DB });
  const p = url.searchParams;
  const raw = p.get('ids');
  const dow = parseInt(p.get('dow') ?? '0', 10);
  const month = parseInt(p.get('month') ?? '1', 10);
  const mins = parseInt(p.get('mins') ?? '0', 10);

  if (!raw) {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const ids = raw.split(',').map(s => parseInt(s.trim(), 10)).filter(n => !isNaN(n) && n > 0).slice(0, 500);
  if (ids.length === 0) {
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  try {
    const placeholders = ids.map(() => '?').join(',');
    const rows = await runQuery(db,
      `SELECT listing_id, day_of_week, month_start, month_end, open_mins, close_mins,
              is_open_24h, is_daylight, is_unknown
       FROM hours WHERE listing_id IN (${placeholders})`,
      ids
    );

    const [daylightOpen, daylightClose] = getDaylightHoursMinutes(month);

    // Group hours by listing
    const byListing = new Map<number, any[]>();
    for (const row of rows) {
      const arr = byListing.get(row.listing_id) ?? [];
      arr.push(row);
      byListing.set(row.listing_id, arr);
    }

    const result: Record<number, { isOpen: boolean; label: string }> = {};

    for (const id of ids) {
      const rows = byListing.get(id) ?? [];

      if (rows.length === 0) {
        result[id] = { isOpen: false, label: 'Hours unknown' };
        continue;
      }

      // Check if listing has 24h hours in the hours table
      if (rows.some(r => r.is_open_24h)) {
        result[id] = { isOpen: true, label: 'Open 24 hrs' };
        continue;
      }

      // If all rows are unknown
      if (rows.every(r => r.is_unknown)) {
        result[id] = { isOpen: false, label: 'Hours unknown' };
        continue;
      }

      // Normalize rows: filter out unknown, handle daylight hours
      type NormRow = { day_of_week: number; month_start: number | null; month_end: number | null; open_mins: number; close_mins: number };

      const normRows: NormRow[] = rows
        .filter(r => !r.is_unknown && r.day_of_week !== null)
        .map(r => ({
          day_of_week: r.day_of_week,
          month_start: r.month_start,
          month_end: r.month_end,
          open_mins: r.is_daylight ? daylightOpen : (r.open_mins ?? 0),
          close_mins: r.is_daylight ? daylightClose : (r.close_mins ?? 1439),
        }));

      // Handle day_of_week=null (applies to all days)
      const allDayRows: NormRow[] = rows
        .filter(r => !r.is_unknown && r.day_of_week === null)
        .map(r => ({
          day_of_week: dow,
          month_start: r.month_start,
          month_end: r.month_end,
          open_mins: r.is_daylight ? daylightOpen : (r.open_mins ?? 0),
          close_mins: r.is_daylight ? daylightClose : (r.close_mins ?? 1439),
        }));

      const all = [...normRows, ...allDayRows];
      if (all.length === 0) {
        result[id] = { isOpen: false, label: 'Hours unknown' };
        continue;
      }

      // Filter to today's rows (matching day_of_week and season)
      const todayRows = all.filter(r => r.day_of_week === dow && monthInSeason(month, r.month_start, r.month_end));
      if (todayRows.length === 0) {
        result[id] = { isOpen: false, label: 'Closed today' };
        continue;
      }

      // Check if currently open
      const openNow = todayRows.find(r => mins >= r.open_mins && mins <= r.close_mins);
      if (openNow) {
        result[id] = {
          isOpen: true,
          label: openNow.close_mins >= 1439 ? 'Open' : `Open \u00b7 Closes ${minsToTimeLabel(openNow.close_mins)}`,
        };
        continue;
      }

      // Check if opening later today
      const upcoming = todayRows.filter(r => r.open_mins > mins).sort((a, b) => a.open_mins - b.open_mins)[0];
      if (upcoming) {
        result[id] = { isOpen: false, label: `Closed \u00b7 Opens ${minsToTimeLabel(upcoming.open_mins)}` };
        continue;
      }

      // Find next opening time (look ahead up to 6 days)
      let foundLabel: string | null = null;
      for (let d = 1; d <= 6; d++) {
        const nextDow = (dow + d) % 7;
        const nextRows = all.filter(r => r.day_of_week === nextDow && monthInSeason(month, r.month_start, r.month_end));
        if (nextRows.length > 0) {
          const earliest = nextRows.sort((a, b) => a.open_mins - b.open_mins)[0];
          foundLabel = d === 1
            ? `Closed \u00b7 Opens ${minsToTimeLabel(earliest.open_mins)} tomorrow`
            : 'Closed';
          break;
        }
      }
      result[id] = { isOpen: false, label: foundLabel ?? 'Closed' };
    }

    return new Response(JSON.stringify(result), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store, max-age=0',
      },
    });
  } catch (err) {
    console.error('[/api/open-status] Error:', err);
    return new Response(JSON.stringify({}), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
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
