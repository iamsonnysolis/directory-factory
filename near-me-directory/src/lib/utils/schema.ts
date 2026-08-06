/**
 * Schema.org structured data utilities for Near Me Directory
 * Astro SSR implementation
 */

// Site URL - can be overridden via environment variable
import { PUBLIC_SITE_URL } from 'astro/env/server';
const SITE_URL = PUBLIC_SITE_URL ?? 'https://nearme.directory';

import { getFeatureLabel } from '../feature-icons';

/**
 /**
  * State URL segment: always state_code.toLowerCase() e.g. "qld"
  */
 function stateSegment(stateCode: unknown): string {
   // Guard against non-string input to avoid runtime TypeError in SSR
   if (typeof stateCode !== 'string' || !stateCode.length) {
     return '';
   }
   return stateCode.toLowerCase();
 }

/**
 * Builds structured data for the homepage
 */
export function buildHomeSchema(): object {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: 'Find a Public Listing Near Me',
    url: SITE_URL,
    description: 'Find a public facility near you with opening hours, accessibility information, baby change facilities and nearby locations across Australia.',
  };
}

/**
 * Builds BreadcrumbList structured data for SEO
 */
export interface BreadcrumbItem {
  label: string;
  href: string;
}

export function buildBreadcrumbSchema(crumbs: BreadcrumbItem[]) {
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: crumbs.map((c, i) => ({
      '@type': 'ListItem',
      position: i + 1,
      name: c.label,
      item: `${SITE_URL}${c.href}`,
    })),
  };
}

/**
 * Builds LocalBusiness structured data for a facility
 */
export interface ListingDetailForSchema {
  name: string;
  address: string | null;
  town: string | null;
  latitude: number;
  longitude: number;
  is_open_24h: boolean;
}

export function buildListingSchema(
  listing: ListingDetailForSchema,
  stateParam: string, // already code.toLowerCase() from URL param
  regionSlug: string | null,
  suburbSlug: string | null,
  slug: string
) {
  const url = regionSlug && suburbSlug
    ? `${SITE_URL}/${stateParam}/${regionSlug}/${suburbSlug}/${slug}`
    : SITE_URL;

  return {
    '@context': 'https://schema.org',
    '@type': 'LocalBusiness',
    name: listing.name,
    description: `Public listing${listing.address ? ` at ${listing.address}` : ''}`,
    url,
    address: {
      '@type': 'PostalAddress',
      streetAddress: listing.address ?? undefined,
      addressLocality: listing.town ?? undefined,
      addressCountry: 'AU',
    },
    geo: {
      '@type': 'GeoCoordinates',
      latitude: listing.latitude,
      longitude: listing.longitude,
    },
    ...(listing.is_open_24h ? {
      openingHours: 'Mo-Su 00:00-24:00',
    } : {}),
  };
}

/**
 * Builds schema for a state page
 */
export interface StateForSchema {
  code: string;
  name: string;
  listing_count: number;
}

export function buildStateSchema(state: StateForSchema) {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: `Find a Public Listing in ${state.name}`,
    url: `${SITE_URL}/${stateSegment(state.code)}`,
    description: `Find a public facility in ${state.name}, including accessible listings, baby change facilities and nearby locations.`,
  };
}

/**
 * Builds schema for a region page
 */
export interface RegionForSchema {
  name_clean: string;
  slug: string;
  listing_count: number;
}

export function buildRegionSchema(stateCode: string, region: RegionForSchema) {
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: `Find a Public Listing in ${region.name_clean}`,
    url: `${SITE_URL}/${stateSegment(stateCode)}/${region.slug}`,
    description: `Find a public facility in ${region.name_clean}. View opening hours, accessibility information, baby change facilities and nearby locations.`,
  };
}

/**
 * Builds schema for a suburb page
 */
export interface SuburbForSchema {
  name: string;
  slug: string;
  listing_count: number;
}

export function buildSuburbSchema(stateCode: string, region: RegionForSchema | null, suburb: SuburbForSchema) {
  const regionSlug = region?.slug ?? '';
  return {
    '@context': 'https://schema.org',
    '@type': 'WebPage',
    name: `Find a Public Listing in ${suburb.name}`,
    url: `${SITE_URL}/${stateSegment(stateCode)}/${regionSlug}/${suburb.slug}`,
    description: `Find a public facility in ${suburb.name}, including open now locations, accessible facilities and baby change stations. Fast, simple and easy to use.`,
  };
}

/**
 * Builds FAQ structured data
 */
export function buildFaqSchema(items: Array<{ question: string; answer: string }>) {
  return {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map((item) => ({
      '@type': 'Question',
      name: item.question,
      acceptedAnswer: { '@type': 'Answer', text: item.answer },
    })),
  };
}

/**
 * Serializes schema object to JSON string for <script type="application/ld+json">
 */
export function serializeSchema(schema: object): string {
  return JSON.stringify(schema);
}

/**
 * Builds schema for a state feature page: /[state]/with/[feature]/
 */
export interface StateFeatureForSchema {
  code: string;
  name: string;
  listing_count: number;
  featureLabel: string;
  featureCount: number;
}

// Convert snake_case to kebab-case for URLs
const toKebabCase = (snakeStr: string): string => snakeStr.replace(/_/g, '-');

export function buildStateFeatureSchema(
  state: StateFeatureForSchema,
  featureKey: string, // snake_case from DB
  facilityCount: number
) {
  const featureLabel = getFeatureLabel(featureKey);
  const featureKeyKebab = toKebabCase(featureKey);
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: `Find ${featureLabel} Facilities in ${state.name}`,
    url: `${SITE_URL}/${stateSegment(state.code)}/with/${featureKeyKebab}`,
    description: `Find ${featureLabel.toLowerCase()} public listings in ${state.name}. Check opening hours, accessibility information and directions across ${facilityCount} locations.`,
  };
}

/**
 * Builds schema for a region feature page: /[state]/[region]/with/[feature]/
 */
export interface RegionFeatureForSchema {
  name_clean: string;
  slug: string;
  listing_count: number;
  featureLabel: string;
  featureCount: number;
}

export function buildRegionFeatureSchema(
  stateCode: string,
  region: { name_clean: string; slug: string; listing_count: number },
  featureKey: string, // snake_case from DB
  facilityCount: number
) {
  const featureLabel = getFeatureLabel(featureKey);
  const featureKeyKebab = toKebabCase(featureKey);
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: `Find ${featureLabel} Facilities in ${region.name_clean}`,
    url: `${SITE_URL}/${stateSegment(stateCode)}/${region.slug}/with/${featureKeyKebab}`,
    description: `Find ${featureLabel.toLowerCase()} public listings in ${region.name_clean}, ${stateCode.toUpperCase()}. View addresses, features and directions for ${facilityCount} locations.`,
  };
}

/**
 * Builds schema for a suburb feature page: /[state]/[region]/[suburb]/with/[feature]/
 */
export interface SuburbFeatureForSchema {
  name: string;
  slug: string;
  listing_count: number;
  region_slug: string;
  featureLabel: string;
  featureCount: number;
}

export function buildSuburbFeatureSchema(
  stateCode: string,
  region: { slug: string },
  suburb: { name: string; slug: string; listing_count: number; region_slug: string; featureLabel: string; featureCount: number },
  featureKey: string, // snake_case from DB
  facilityCount: number
) {
  const featureLabel = getFeatureLabel(featureKey);
  const featureKeyKebab = toKebabCase(featureKey);
  const regionSlug = region.slug;
  return {
    '@context': 'https://schema.org',
    '@type': 'CollectionPage',
    name: `Find ${featureLabel} Facilities in ${suburb.name}`,
    url: `${SITE_URL}/${stateSegment(stateCode)}/${regionSlug}/${suburb.slug}/with/${featureKeyKebab}`,
    description: `Find ${featureLabel.toLowerCase()} public listings in ${suburb.name}. Includes addresses, opening hours and nearby options.`,
  };
}