/**
 * Hours formatting utilities for FacilitiesNearMe V2
 * Pure functions - no Astro/UI dependencies
 */

import { getDaylightHoursFormatted } from './daylight-hours';

export const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'] as const;

export interface HourRow {
  day_of_week: number | null;
  month_start: number | null;
  month_end: number | null;
  open_mins: number | null;
  close_mins: number | null;
  is_open_24h: boolean;
  is_daylight: boolean;
  is_unknown: boolean;
}

export interface FormattedSlot {
  open: string;
  close: string;
  is24Hours: boolean;
  isDaylight: boolean;
  isUnknown: boolean;
  seasonLabel?: string;
}

export interface FormattedDay {
  day: number;
  label: string;
  slots: FormattedSlot[];
}

const MONTH_NAMES = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'] as const;

/**
 * Normalizes minutes into human-readable time format
 * Handles next-day close values (>1440 minutes) via modulo
 */
export function formatMins(mins: number | null | undefined): string {
  if (mins === null || mins === undefined) return '';
  const normalised = mins % 1440;
  const h = Math.floor(normalised / 60);
  const m = normalised % 60;
  const period = h < 12 ? 'am' : 'pm';
  const displayH = h % 12 === 0 ? 12 : h % 12;
  return m === 0 ? `${displayH} ${period}` : `${displayH}:${String(m).padStart(2, '0')} ${period}`;
}

/**
 * Formats month range into short season label (e.g., "Mar - May")
 * Returns undefined for full-year coverage
 */
export function formatSeasonLabel(monthStart: number | null, monthEnd: number | null): string | undefined {
  if (!monthStart || !monthEnd) return undefined;
  if (monthStart === 1 && monthEnd === 12) return undefined;
  return `${MONTH_NAMES[monthStart]} - ${MONTH_NAMES[monthEnd]}`;
}

/**
 * Returns estimated daylight hours for a given month
 * Now uses unified data source
 */
export function getDaylightHoursEstimate(month: number): { open: string; close: string } {
  return getDaylightHoursFormatted(month);
}

/**
 * Formats raw hour rows into display-ready structure with all 7 days
 */
export function formatHoursForDisplay(rows: HourRow[]): FormattedDay[] {
  const currentMonth = new Date().getMonth() + 1;
  
  // Check for full-week 24h coverage
  if (rows.some(r => r.is_open_24h && r.day_of_week === null)) {
    return DAY_NAMES.map((label, day) => ({
      day,
      label,
      slots: [{ open: 'Open', close: '24 hours', is24Hours: true, isDaylight: false, isUnknown: false }],
    }));
  }
  
  return DAY_NAMES.map((label, day) => {
    const applicableRows = rows.filter(r => r.day_of_week === null || r.day_of_week === day);
    
    const slots: FormattedSlot[] = applicableRows.map(r => {
      if (r.is_open_24h) {
        return { open: 'Open', close: '24 hours', is24Hours: true, isDaylight: false, isUnknown: false, seasonLabel: formatSeasonLabel(r.month_start, r.month_end) };
      }
      if (r.is_unknown) {
        return { open: 'Hours', close: 'unknown', is24Hours: false, isDaylight: false, isUnknown: true };
      }
      if (r.is_daylight) {
        const est = getDaylightHoursEstimate(currentMonth);
        return { open: est.open, close: est.close, is24Hours: false, isDaylight: true, isUnknown: false, seasonLabel: formatSeasonLabel(r.month_start, r.month_end) };
      }
      if (r.open_mins !== null && r.close_mins !== null) {
        return { open: formatMins(r.open_mins), close: formatMins(r.close_mins), is24Hours: false, isDaylight: false, isUnknown: false, seasonLabel: formatSeasonLabel(r.month_start, r.month_end) };
      }
      return { open: 'Closed', close: '', is24Hours: false, isDaylight: false, isUnknown: false };
    });
    
    return { 
      day, 
      label, 
      slots: slots.length > 0 ? slots : [{ open: 'Closed', close: '', is24Hours: false, isDaylight: false, isUnknown: false }] 
    };
  });
}