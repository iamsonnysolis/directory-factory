import { defineConfig } from 'astro/config';
import tailwind from '@astrojs/tailwind';
import cloudflare from '@astrojs/cloudflare';

export default defineConfig({
  output: 'server',
  adapter: cloudflare({
    // D1 bindings are passed through to Astro.locals via server context
    platformProxy: {
      // During `astro dev`, use the platform proxy to load wrangler bindings
      config: 'wrangler.toml',
    },
  }),
  server: {
    allowedHosts: ['localhost', '*.pages.dev', '*.taila*.ts.net'],
  },
  env: {
    schema: {
      PUBLIC_SITE_URL: {
        type: 'string',
        default: 'https://nearme.directory',
      },
    },
  },
  integrations: [tailwind()],
});
