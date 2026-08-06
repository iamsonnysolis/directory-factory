/**
 * Site configuration loader
 * Reads branding and legal content from D1 at build/render time
 * Falls back to sensible defaults if the config table is empty or unavailable
 */

import { runQuerySingle, runQuery } from './d1';

export interface SiteConfig {
  id: string;
  site_name: string;
  site_tagline: string;
  site_url: string;
  default_title: string;
  default_description: string;
  logo_svg: string;
  logo_initial: string;
  primary_color: string;
  accent_color: string;
  feature_label: string;     // e.g. "Facility" or "Listing" (for EEAT copy)
  entity_label_singular: string;  // e.g. "facility"
  entity_label_plural: string;    // e.g. "facilities"
  entity_type_name: string;       // e.g. "Public Facility"
  footer_copyright: string;
  footer_brand_text: string;
  ga_measurement_id: string;
  data_source_url: string;
  data_source_name: string;
  data_source_attribution: string;
  privacy_policy_html: string;
  terms_of_service_html: string;
  contact_page_html: string;
  header_nav_stats_label: string;
  header_nav_stats_title: string;
  footer_find_label: string;
  footer_stats_label: string;
  [key: string]: any;
}

export interface LegalPageContent {
  title: string;
  html: string;
}

// Default config used as fallback when D1 has no config row
const DEFAULT_CONFIG: SiteConfig = {
  id: 'default',
  site_name: 'Near Me Directory',
  site_tagline: 'Find public facilities near you',
  site_url: 'https://nearme.directory',
  default_title: 'Near Me Directory',
  default_description: 'Find public facilities across regions. Search by state, region, or suburb for accessible facilities, baby change, and more.',
  logo_svg: '',
  logo_initial: 'N',
  primary_color: '#1d4ed8',
  accent_color: '#f59e0b',
  feature_label: 'Feature',
  entity_label_singular: 'facility',
  entity_label_plural: 'facilities',
  entity_type_name: 'Public Facility',
  footer_copyright: '&copy; {{year}} Near Me Directory',
  footer_brand_text: 'Near Me Directory',
  ga_measurement_id: '',
  data_source_url: 'https://example.com',
  data_source_name: 'Data Source',
  data_source_attribution: 'Data sourced from the public data provider.',
  privacy_policy_html: '<p>Privacy policy content is configured via the site_config table in D1.</p>',
  terms_of_service_html: '<p>Terms of service content is configured via the site_config table in D1.</p>',
  contact_page_html: '<p>Contact information is configured via the site_config table in D1.</p>',
  header_nav_stats_label: 'Stats',
  header_nav_stats_title: 'Facility Statistics',
  footer_find_label: 'Find near me',
  footer_stats_label: 'Stats',
};

let configCache: SiteConfig | null = null;
let configLoading: Promise<SiteConfig> | null = null;

/**
 * Load site configuration from D1.
 * Caches the result for the duration of the process to avoid repeated queries.
 * Pass the D1 binding explicitly if in a server/SSR context.
 */
export async function loadSiteConfig(env?: { DB?: any }): Promise<SiteConfig> {
  // Return cached config if available (build-time caching)
  if (configCache) {
    return configCache;
  }

  // Prevent concurrent loads
  if (configLoading) {
    return configLoading;
  }

  configLoading = _loadSiteConfigFromDB(env);
  const result = await configLoading;
  configCache = result;
  configLoading = null;
  return result;
}

async function _loadSiteConfigFromDB(env?: { DB?: any }): Promise<SiteConfig> {
  try {
    // Try to get the D1 binding
    let db;
    try {
      const { getD1Client } = await import('./d1');
      db = getD1Client(env);
    } catch {
      // No D1 binding available — use defaults
      return { ...DEFAULT_CONFIG };
    }

    const row = await runQuerySingle(
      db,
      'SELECT * FROM site_config WHERE id = ? LIMIT 1',
      ['default']
    );

    if (!row) {
      return { ...DEFAULT_CONFIG };
    }

    // Merge with defaults to fill any gaps
    return { ...DEFAULT_CONFIG, ...row };
  } catch (err) {
    console.warn('Failed to load site_config from D1, using defaults:', err);
    return { ...DEFAULT_CONFIG };
  }
}

/**
 * Get legal page content (privacy, terms, contact) from site_config.
 * These are read at request time so editors can update them without redeploys.
 */
export async function getLegalPage(
  page: 'privacy' | 'terms' | 'contact',
  env?: { DB?: any }
): Promise<LegalPageContent> {
  const config = await loadSiteConfig(env);

  const pageMeta: Record<string, { title: string; field: string }> = {
    privacy: { title: 'Privacy Policy', field: 'privacy_policy_html' },
    terms: { title: 'Terms of Service', field: 'terms_of_service_html' },
    contact: { title: 'Contact', field: 'contact_page_html' },
  };

  const meta = pageMeta[page];
  const html = config[meta.field] || '';

  return {
    title: `${config.site_name} — ${meta.title}`,
    html,
  };
}

/**
 * Clear the config cache (useful in tests)
 */
export function clearConfigCache(): void {
  configCache = null;
  configLoading = null;
}

/**
 * Get default SEO metadata from site config
 */
export function getDefaultMetadata(config: SiteConfig) {
  return {
    title: config.default_title,
    description: config.default_description,
    openGraph: {
      url: config.site_url,
      siteName: config.site_name,
      title: config.default_title,
      description: config.default_description,
      type: 'website',
      images: [{ url: `${config.site_url}/og-default.png` }],
    },
    twitter: {
      card: 'summary_large_image',
      site: config.site_name,
      title: config.default_title,
      description: config.default_description,
      images: [`${config.site_url}/og-default.png`],
    },
  };
}
