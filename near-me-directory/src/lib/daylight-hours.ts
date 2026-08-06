/**
 * Daylight hours data for Australia (~27°S latitude)
 * Single source of truth used by both hours.ts and open-status API
 */

// Daylight hours in minutes since midnight
// Format: [openMins, closeMins]
export const DAYLIGHT_MINS_BY_MONTH: Record<number, [number, number]> = {
  1:  [330, 1185],  // Jan  5:30am – 7:45pm
  2:  [360, 1110],  // Feb  6:00am – 7:30pm
  3:  [380, 1010],  // Mar  6:20am – 6:50pm
  4:  [360, 990],   // Apr  6:00am – 5:30pm
  5:  [380, 960],   // May  6:20am – 5:00pm
  6:  [430, 990],   // Jun  7:10am – 5:10pm
  7:  [420, 990],   // Jul  7:00am – 5:10pm
  8:  [360, 1005],  // Aug  6:00am – 5:45pm
  9:  [370, 970],   // Sep  6:10am – 5:40pm
  10: [340,  990],  // Oct  5:40am – 6:30pm
  11: [315, 1110],  // Nov  5:15am – 7:00pm
  12: [315, 1125],  // Dec  5:15am – 7:30pm
};

/**
 * Get daylight hours as formatted strings
 * Used by hours.ts for display formatting
 */
export function getDaylightHoursFormatted(month: number): { open: string; close: string } {
  const [openMins, closeMins] = DAYLIGHT_MINS_BY_MONTH[month] ?? [360, 1080];
  
  const openH = Math.floor(openMins / 60);
  const openM = openMins % 60;
  const closeH = Math.floor(closeMins / 60);
  const closeM = closeMins % 60;
  
  const formatTime = (h: number, m: number): string => {
    const period = h < 12 ? 'am' : 'pm';
    const displayH = h % 12 === 0 ? 12 : h % 12;
    return m === 0 ? `${displayH} ${period}` : `${displayH}:${String(m).padStart(2, '0')} ${period}`;
  };
  
  return {
    open: formatTime(openH, openM),
    close: formatTime(closeH, closeM),
  };
}

/**
 * Get daylight hours as minutes array
 * Used by open-status.ts for time comparison
 */
export function getDaylightHoursMinutes(month: number): [number, number] {
  return DAYLIGHT_MINS_BY_MONTH[month] ?? [360, 1080];
}