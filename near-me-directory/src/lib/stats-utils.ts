// Convert minutes-from-midnight to readable time e.g. 1080 → "6:00 pm"
export function minsToTime(mins: number | null | undefined): string | null {
  if (mins === null || mins === undefined) return null;
  const m = mins % 1440; // handle >24h (next-day closes)
  const h = Math.floor(m / 60);
  const min = m % 60;
  const period = h < 12 ? 'am' : 'pm';
  const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return min === 0 ? `${h12} ${period}` : `${h12}:${String(min).padStart(2, '0')} ${period}`;
}

// Format source_version for display: '2025-01' → 'January 2025'
export function formatVersion(version: string | null | undefined): string {
  if (!version) return 'Unknown';
  const [year, month] = version.split('-');
  const monthNames = [
    '', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];
  return `${monthNames[parseInt(month)]} ${year}`;
}

// Canonical 0-100 score → letter grade + color token.
export function scoreToGradeDisplay(score: number | null | undefined): { grade: string; color: string } {
  if (score === null || score === undefined) return { grade: '—', color: 'neutral' };
  if (score >= 70) return { grade: 'A', color: 'good' };
  if (score >= 45) return { grade: 'B', color: 'hours' };
  return { grade: 'C', color: 'gap' };
}

// String-only variant for callers that just want the letter (legacy signature).
export function scoreToGrade(score: number | null | undefined): string {
  return scoreToGradeDisplay(score).grade;
}

// Grade for RAW PERCENTAGES on comparison charts, relative to national average —
// always produces a meaningful A/B/C spread regardless of the absolute range
// of the data.
export function pctToGrade(pct: number | null | undefined, nationalAvg: number | null | undefined): { grade: string; color: string } {
  if (pct === null || pct === undefined || nationalAvg === null || nationalAvg === undefined) {
    return { grade: '—', color: 'neutral' };
  }
  if (pct >= nationalAvg + 3) return { grade: 'A', color: 'good' };
  if (pct >= nationalAvg - 3) return { grade: 'B', color: 'mid' };
  return { grade: 'C', color: 'low' };
}

// Format large numbers with commas: 25062 → "25,062"
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-AU');
}

// Format a percentage: 42.3 → "42.3%"
export function formatPct(n: number | null | undefined, decimals: number = 1): string {
  if (n === null || n === undefined) return '—';
  return `${Number(n).toFixed(decimals)}%`;
}

// Format per-capita: 12.4 → "12.4 per 10,000"
export function formatPerCapita(n: number | null | undefined, scale: string = '10,000'): string {
  if (n === null || n === undefined) return '—';
  return `${Number(n).toFixed(1)} per ${scale}`;
}

// Get ordinal: 1 → "1st", 2 → "2nd", 3 → "3rd"
export function ordinal(n: number | null | undefined): string {
  if (!n) return '—';
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Format a rank + rank_of pair for display: (2, 8) → "2nd of 8"
export function formatRank(rank: number | null | undefined, rankOf: number | null | undefined): string {
  if (!rank) return '—';
  return rankOf ? `${ordinal(rank)} of ${rankOf}` : ordinal(rank);
}

// State display names
export const STATE_NAMES: Record<string, string> = {
  nsw: 'New South Wales',
  vic: 'Victoria',
  qld: 'Queensland',
  wa: 'Western Australia',
  sa: 'South Australia',
  tas: 'Tasmania',
  act: 'Australian Capital Territory',
  nt: 'Northern Territory'
};

// Full state name from code: 'qld' → 'Queensland'
export function stateName(code: string | null | undefined): string {
  if (!code) return '';
  return STATE_NAMES[code.toLowerCase()] ?? code.toUpperCase();
}

// Determine coverage level label and color for a percentage (design spec Section 2.2)
export function coverageLevel(pct: number | null | undefined): { label: string; color: string } {
  if (pct === null || pct === undefined) return { label: 'No data', color: 'neutral' };
  if (pct >= 60) return { label: 'High', color: 'good' };
  if (pct >= 40) return { label: 'Moderate', color: 'hours' };
  return { label: 'Low', color: 'gap' };
}

// ─── Feature taxonomy ───────────────────────────────────────────────────────
//
// Drives the single dynamic /stats/features/[feature] template (Phase 4).
// Each entry maps a URL slug to the metric keys generate-stats.js writes for
// both `state` and `region` entity types (Phase 2 gives these full parity).
// `rankMetric` is whichever metric should drive the state comparison table
// on that page — usually the percentage, since it's population-fair.

export interface FeatureDefinition {
  slug: string;
  label: string;
  shortLabel: string;
  description: string;
  countMetric: string;
  pctMetric: string | null;
  perCapitaMetric: string | null; // state-side key; region equivalent swaps _10k for _1000
  rankMetric: string; // metric used to rank states/regions on the feature page
  // Audience framing (Phase 4): who this page is written for and why it matters —
  // replaces the old approach of a bespoke landing page per audience.
  audience: string; // e.g. "Parents and carers"
  whyItMatters: string; // one sentence, used in the hero/insight callout
  topic: 'primary' | 'family' | 'hours'; // drives StatTile/InsightCallout color theme
  searchFilterKey: string; // matches /listings?feature= query param
  legacySlug?: string; // old hardcoded page this feature replaces, for /_redirects
}

export const FEATURE_TAXONOMY: Record<string, FeatureDefinition> = {
  accessible: {
    slug: 'accessible',
    label: 'Wheelchair Accessible Facilities',
    shortLabel: 'Accessible',
    description: 'Facilities with wheelchair access, including Changing Places and ambulant facilities.',
    countMetric: 'accessible_count',
    pctMetric: 'accessible_pct',
    perCapitaMetric: 'accessible_per_10k',
    rankMetric: 'accessible_pct',
    audience: 'Wheelchair users and people with limited mobility',
    whyItMatters: 'Knowing which facilities are actually wheelchair accessible — not just nearby — is often the difference between a trip being possible or not.',
    topic: 'primary',
    searchFilterKey: 'accessible',
    legacySlug: 'accessibility',
  },
  'baby-change': {
    slug: 'baby-change',
    label: 'Baby Change Facilities',
    shortLabel: 'Baby Change',
    description: 'Facilities with baby change tables or dedicated baby care rooms.',
    countMetric: 'baby_change_count',
    pctMetric: 'baby_change_pct',
    perCapitaMetric: 'baby_change_per_10k',
    rankMetric: 'baby_change_pct',
    audience: 'Parents and carers of infants',
    whyItMatters: 'A missing baby change table can turn a short errand into a genuine problem — coverage varies a lot by state and region.',
    topic: 'family',
    searchFilterKey: 'baby_change',
    legacySlug: 'families',
  },
  'changing-places': {
    slug: 'changing-places',
    label: 'Changing Places Facilities',
    shortLabel: 'Changing Places',
    description: 'Larger accessible facilities for people with profound disability, including hoists and adult change tables.',
    countMetric: 'changing_places_count',
    pctMetric: 'changing_places_pct',
    perCapitaMetric: 'changing_places_per_100k',
    rankMetric: 'changing_places_pct',
    audience: 'People with profound disability and their carers',
    whyItMatters: 'Standard accessible listings aren\u2019t enough for everyone — Changing Places facilities with hoists and adult change tables are still rare nationally.',
    topic: 'primary',
    searchFilterKey: 'changing_places',
    legacySlug: 'changing-places',
  },
  shower: {
    slug: 'shower',
    label: 'Facilities with Showers',
    shortLabel: 'Shower',
    description: 'Public facilities offering a shower, useful for travellers and people experiencing homelessness.',
    countMetric: 'shower_count',
    pctMetric: 'shower_pct',
    perCapitaMetric: 'shower_per_10k',
    rankMetric: 'shower_pct',
    audience: 'Travellers, van-lifers, and people experiencing homelessness',
    whyItMatters: 'A public shower can matter as much as a bed — for people on the road or without stable housing, coverage gaps hit hardest.',
    topic: 'hours',
    searchFilterKey: 'shower',
  },
  parking: {
    slug: 'parking',
    label: 'Accessible Parking',
    shortLabel: 'Parking',
    description: 'Facilities with dedicated accessible parking bays nearby.',
    countMetric: 'parking_accessible_count',
    pctMetric: 'parking_accessible_pct',
    perCapitaMetric: null,
    rankMetric: 'parking_accessible_pct',
    audience: 'Drivers with a disability parking permit',
    whyItMatters: 'Without an accessible bay close by, an otherwise-accessible facility can still be out of reach.',
    topic: 'primary',
    searchFilterKey: 'parking_accessible',
  },
  'drinking-water': {
    slug: 'drinking-water',
    label: 'Drinking Water',
    shortLabel: 'Drinking Water',
    description: 'Facilities with an accessible drinking water fountain or tap.',
    countMetric: 'drinking_water_count',
    pctMetric: 'drinking_water_pct',
    perCapitaMetric: null,
    rankMetric: 'drinking_water_pct',
    audience: 'Runners, cyclists, and outdoor exercisers',
    whyItMatters: 'On a long walk or ride, a drinking fountain next to a facility stop is what makes the route actually workable in hot weather.',
    topic: 'hours',
    searchFilterKey: 'drinking_water',
  },
  'dump-point': {
    slug: 'dump-point',
    label: 'Dump Points',
    shortLabel: 'Dump Point',
    description: 'Facilities with a caravan/RV waste dump point, for travellers on the road.',
    countMetric: 'dump_point_count',
    pctMetric: 'dump_point_pct',
    perCapitaMetric: null,
    rankMetric: 'dump_point_pct',
    audience: 'Caravan, motorhome, and RV travellers',
    whyItMatters: 'Dump point access shapes road-trip routes — some regions are far better set up for grey/black water disposal than others.',
    topic: 'hours',
    searchFilterKey: 'dump_point',
    legacySlug: 'caravans',
  },
  'open-24h': {
    slug: 'open-24h',
    label: 'Open 24 Hours',
    shortLabel: 'Open 24h',
    description: 'Facilities open around the clock, with no set closing time.',
    countMetric: 'open_24h_count',
    pctMetric: 'open_24h_pct',
    perCapitaMetric: 'open_24h_per_10k',
    rankMetric: 'open_24h_pct',
    audience: 'Shift workers, night owls, and people with urgent medical needs',
    whyItMatters: 'For anyone out at 2am, whether a nearby facility is actually open around the clock is not something you want to find out the hard way.',
    topic: 'hours',
    searchFilterKey: 'open_24h',
    legacySlug: '24-hours',
  },
};

export type FeatureSlug = keyof typeof FEATURE_TAXONOMY;

export function getFeatureDefinition(slug: string): FeatureDefinition | null {
  return FEATURE_TAXONOMY[slug] ?? null;
}

export function listFeatureSlugs(): string[] {
  return Object.keys(FEATURE_TAXONOMY);
}

// ─── Tailwind color-class safelist ────────────────────────────────────────
//
// IMPORTANT: Tailwind's JIT compiler only includes classes it can find as
// *complete literal strings* in scanned source files — it cannot resolve
// `` `bg-${color}-500` `` or `'bg-' + color + '-500'` at build time, since
// those are runtime-constructed. Any class built that way silently vanishes
// from the compiled CSS. Every topic color used anywhere in the stats pages
// must have its full class names spelled out here (or somewhere) so the
// scanner picks them up. Always resolve through this map server-side and
// pass the resulting literal strings down — never re-concatenate a color
// name into a class string, including in client-side scripts.
export const TOPIC_COLOR_CLASSES: Record<string, {
  gradientFrom: string;
  bgLight: string;
  badgeBg: string;
  badgeText: string;
  bar: string;
  linkText: string;
  linkTextHover: string;
}> = {
  blue: {
    gradientFrom: 'from-blue-50', bgLight: 'bg-blue-50', badgeBg: 'bg-blue-100',
    badgeText: 'text-blue-800', bar: 'bg-blue-500', linkText: 'text-blue-700', linkTextHover: 'hover:text-blue-900',
  },
  teal: {
    gradientFrom: 'from-teal-50', bgLight: 'bg-teal-50', badgeBg: 'bg-teal-100',
    badgeText: 'text-teal-800', bar: 'bg-teal-500', linkText: 'text-teal-700', linkTextHover: 'hover:text-teal-900',
  },
  amber: {
    gradientFrom: 'from-amber-50', bgLight: 'bg-amber-50', badgeBg: 'bg-amber-100',
    badgeText: 'text-amber-800', bar: 'bg-amber-500', linkText: 'text-amber-700', linkTextHover: 'hover:text-amber-900',
  },
  purple: {
    gradientFrom: 'from-purple-50', bgLight: 'bg-purple-50', badgeBg: 'bg-purple-100',
    badgeText: 'text-purple-800', bar: 'bg-purple-500', linkText: 'text-purple-700', linkTextHover: 'hover:text-purple-900',
  },
};

export function topicColorClasses(color: string) {
  return TOPIC_COLOR_CLASSES[color] ?? TOPIC_COLOR_CLASSES.blue;
}
