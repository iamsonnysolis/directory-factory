# Deployment Workflow

## Two-Tier Deployment (Preview + Production)

This project uses **two separate deploy commands**:

| Command | Branch | Environment | Who Uses It |
|---------|--------|-------------|-------------|
| `npm run preview-deploy` | `preview` | Preview | Agent |
| `npm run deploy` | `main` | Production | Maintainer (explicit approval) |

## Deploy Commands

### Preview Deployment
```bash
cd /home/shanon/web-dev/directory-factory/near-me-directory
CLOUDFLARE_API_TOKEN=*** npm run preview-deploy
```

### Production Deployment
```bash
cd /home/shanon/web-dev/directory-factory/near-me-directory
CLOUDFLARE_API_TOKEN=*** npm run deploy
```

## URLs

| Branch | URL |
|--------|-----|
| Preview | https://preview.near-me-directory.pages.dev |
| Production | https://nearme.directory |

## Milestone: Production Live ✅

**Date** - Site went live on custom domain `nearme.directory`

## Credentials

- **Cloudflare Account ID:** Configure in wrangler.toml
- **Cloudflare API Token:** Stored in CI/CD secrets

## Development

```bash
# Start dev server (localhost:4321)
npm run dev

# Build only (no deploy)
npm run build

# Build + deploy
npm run preview-deploy  # for preview
npm run deploy          # for production
```

## Notes

- Site is configured for Cloudflare Pages with D1 database bindings
- The `wrangler.toml` configures the D1 database binding (`DB`)
- Astro config schema expects `PUBLIC_SITE_URL` env var
- No `.env` file is needed; secrets are managed via Cloudflare Pages Environment Variables
