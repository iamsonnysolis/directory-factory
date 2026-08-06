/**
 * SEO metadata utilities for near-me-directory
 * Config-driven: branding, URL, and social metadata come from site_config
 */

import type { SiteConfig } from '../site-config';

// ─── Internal helpers ────────────────────────────────────────────────────

function stateSegment(stateCode: string): string {
  return stateCode.toLowerCase();
}

/**
 * Shared OG + Twitter fields so we never forget either block
 */
interface SocialMetaOpts {
  title: string;
  description: string;
  url: string;
  image?: string;
  config: Pick<SiteConfig, 'site_name' | 'twitter_handle'>;
}

function socialMeta(opts: SocialMetaOpts): { openGraph: any; twitter: any } {
  const img = opts.image ?? '';
  return {
    openGraph: {
      siteName: opts.config.site_name,
      type: 'website' as const,
      title: opts.title,
      description: opts.description,
      url: opts.url,
      images: img ? [{ url: img, width: 1200, height: 630, alt: opts.title }] : [],
    },
    twitter: {
      card: 'summary_large_image' as const,
      site: opts.config.twitter_handle,
      title: opts.title,
      description: opts.description,
      images: img ? [img] : [],
    },
  };
}

// ─── Default config (fallback when D1 is unavailable) ────────────────────

const DEFAULT_CONFIG: Pick<SiteConfig, 'site_url' | 'site_name' | 'twitter_handle'> = {
  site_url: 'https://nearme.directory',
  site_name: 'Near Me Directory',
  twitter_handle: '@nearmedirectory',
};

// Legacy exports for backward compatibility with pages that import constants
export const SITE_URL = DEFAULT_CONFIG.site_url;
export const SITE_NAME = DEFAULT_CONFIG.site_name;
export const TWITTER_HANDLE = DEFAULT_CONFIG.twitter_handle;

// ─── Metadata builders ────────────────────────────────────────────────────
// Each accepts an optional config param; falls back to DEFAULT_CONFIG

export function getHomeMetadata(config?: Partial<SiteConfig>): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const title = `Find ${cfg.site_name} Locations | ${cfg.site_name}`;
  const description =
    `Find ${cfg.site_name.toLowerCase()} locations across Australia instantly. ` +
    `Filter by open now, accessible, and 24-hour options. ` +
    `Comprehensive directory with opening hours and directions.`;
  const url = cfg.site_url;

  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

export interface StateForSEO {
  code: string;
  name: string;
  listing_count: number;
}

export function getStateMetadata(
  state: StateForSEO,
  config?: Partial<SiteConfig>,
  customTitle?: string,
  customDesc?: string,
): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const url = `${cfg.site_url}/${stateSegment(state.code)}`;

  const title = customTitle ??
    `Public Listings in ${state.name} | Open Now, Accessible and Nearby Locations`;

  const description = customDesc ??
    `Find public ${cfg.site_name.toLowerCase()} across ${state.name}, including accessible and 24-hour locations. View opening hours and find ${cfg.site_name.toLowerCase()} near you instantly.`;

  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

export interface RegionForSEO {
  name_clean: string;
  slug: string;
  listing_count: number;
}

export function getRegionMetadata(
  stateCode: string,
  region: RegionForSEO,
  config?: Partial<SiteConfig>,
  customTitle?: string,
  customDesc?: string,
): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const url = `${cfg.site_url}/${stateSegment(stateCode)}/${region.slug}`;

  const title = customTitle ??
    `Public Listings in ${region.name_clean}, ${stateCode.toUpperCase()} | Open Now and Nearby Locations`;

  const description = customDesc ??
    `Looking for public ${cfg.site_name.toLowerCase()} in ${region.name_clean}? Find nearby locations, check opening hours, and filter by accessibility and more.`;

  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

export interface SuburbForSEO {
  name: string;
  slug: string;
  listing_count: number;
  region_slug: string | null;
}

export function getSuburbMetadata(
  stateCode: string,
  region: RegionForSEO | null,
  suburb: SuburbForSEO,
  config?: Partial<SiteConfig>,
  customTitle?: string,
  customDesc?: string,
): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const regionSlug = region?.slug ?? suburb.region_slug ?? '';
  const url = `${cfg.site_url}/${stateSegment(stateCode)}/${regionSlug}/${suburb.slug}`;

  const title = customTitle ??
    `Public Listings in ${suburb.name} | Open Now and Nearby Locations`;

  const description = customDesc ??
    `Find public ${cfg.site_name.toLowerCase()} in ${suburb.name}, including open now locations, accessible and 24-hour facilities. Fast, simple and easy to use.`;

  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

export interface ListingForSEO {
  name: string;
  address: string | null;
  town: string | null;
  region_slug: string | null;
  suburb_slug: string | null;
  slug: string;
}

export function getListingMetadata(
  listing: ListingForSEO,
  stateParam: string,
  config?: Partial<SiteConfig>,
  customTitle?: string,
  customDesc?: string,
): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const url = listing.region_slug && listing.suburb_slug
    ? `${cfg.site_url}/${stateParam}/${listing.region_slug}/${listing.suburb_slug}/${listing.slug}`
    : cfg.site_url;

  const suburbLabel = listing.town
    ?? (listing.suburb_slug?.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) ?? '');

  const title = customTitle ??
    `Public Listing at ${listing.name} (${suburbLabel}) | Hours and Features`;

  const description = customDesc ??
    `View details for the public ${cfg.site_name.toLowerCase()} at ${listing.name} in ${suburbLabel}. See opening hours, accessibility features, and nearby locations.`;

  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

// Backward-compatible alias
export { getListingMetadata as getFacilityMetadata };
export { ListingForSEO as FacilityForSEO };

// ─── 404 ─────────────────────────────────────────────────────────────────

export function get404Metadata(config?: Partial<SiteConfig>): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const title = `404 Page Not Found - ${cfg.site_name}`;
  const description = `The page you are looking for could not be found. Find public ${cfg.site_name.toLowerCase()} across Australia.`;
  const url = `${cfg.site_url}/404`;
  return {
    title,
    description,
    canonical: url,
    robots: { index: false, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

// ─── Contact ─────────────────────────────────────────────────────────────

export function getContactMetadata(config?: Partial<SiteConfig>): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const title = `Contact Us - ${cfg.site_name}`;
  const description = `Get in touch with ${cfg.site_name} for questions, suggestions, or to report data issues.`;
  const url = `${cfg.site_url}/contact`;
  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

// ─── Privacy ─────────────────────────────────────────────────────────────

export function getPrivacyMetadata(config?: Partial<SiteConfig>): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const title = `Privacy Policy - ${cfg.site_name}`;
  const description = `Learn about ${cfg.site_name} privacy practices. We do not collect personal information and use minimal cookies only for site functionality.`;
  const url = `${cfg.site_url}/privacy`;
  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}

// ─── Terms ───────────────────────────────────────────────────────────────

export function getTermsMetadata(config?: Partial<SiteConfig>): { title: string; description: string; canonical: string; openGraph: any; twitter: any } {
  const cfg = { ...DEFAULT_CONFIG, ...config };
  const title = `Terms of Use - ${cfg.site_name}`;
  const description = `Terms of use for ${cfg.site_name}. Learn about website use, data accuracy limitations, and liability.`;
  const url = `${cfg.site_url}/terms`;
  return {
    title,
    description,
    canonical: url,
    robots: { index: true, follow: true },
    ...socialMeta({ title, description, url, config: cfg }),
  } as any;
}
