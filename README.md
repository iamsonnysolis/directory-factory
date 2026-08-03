# Directory Factory

A standalone, Python-based orchestration system for building and deploying
white-labeled "near-me" directory websites (e.g. `toiletsnearme.com.au`,
`mobiledoggroomers.com`, etc.). It collects data from Google Places, cleans
and enriches it with Gemini, uploads to a per-directory Cloudflare D1
database, and deploys a white-labeled Astro site to Cloudflare Pages.

> Everything below is a summary of the working agreement. The source of
> truth for tasks and status is [`Directory-Factory-Project-Plan.md`](./Directory-Factory-Project-Plan.md).

## Architecture

- **Local-first orchestrator.** The dashboard/runner lives and runs on the
  laptop — not hosted. It calls Google Places, Gemini, and the Cloudflare REST
  API over HTTP, and shells out to `git`/`wrangler` where needed.
- **The deployed websites** remain 100% on Cloudflare Pages/D1 — only the
  management tool is local.
- **Copy, don't extend.** Working code is copied from three existing projects
  (`dataset-collector`, `toiletsnearme-data`, `toilets-near-me-au-v2`) into this
  system and adapted to a standard interface.
- **One D1 database per directory.** No shared database with `project_id`
  scoping.
- **Branding/config lives in each site's D1 database** (`site_config` table).

## Language

- The entire orchestration system (`directory-factory`) is **Python**.
- The white-labeled Astro template repo (`near-me-directory`) is
  **Astro/TypeScript** — it is the website codebase, not part of the
  orchestrator.

## Folder structure

```
directory-factory/
├── scripts/
│   ├── collection/            ← Phase 1: Google Places collection engine
│   ├── cleaning_enrichment/   ← Phase 2: cleaning + enrichment (JS→Python port)
│   └── deploy/                ← Phase 4 & 6: D1 upload + site provisioning
├── import/                    ← Phase 7: import existing data from old collector
├── dashboard/                 ← Phase 8: FastAPI + static frontend
├── runner/                    ← Phase 3: standardized script runner + contract
├── runs.db                    ← the run-log store (Phase 3)
├── .env                       ← credentials (git-ignored)
├── .env.example
└── README.md
```

The companion white-label template lives at:
[`../near-me-directory/`](https://github.com/example/near-me-directory)
(`NEW_NEAR_ME_DIRECTORY_PATH`).

## Standardized script execution

Every script (collection, cleaning, enrichment, upload, deploy) is invoked
through `runner/run.py` and writes a row to `runs.db`:

```bash
python runner/run.py collection.collect --project-id=42
```

See Phase 3 of the project plan for the exact contract.

## Credentials

Copy `.env.example` to `.env` and fill in:

- `GOOGLE_PLACES_API_KEY`
- `GEMINI_API_KEY`
- `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID`
- `GITHUB_TOKEN`

Per-directory D1 credentials are passed at runtime as script params, not
stored in `.env`.

## Phases

| Phase | Name | Objective |
|---|---|---|
| 0 | Setup | Repo structure, git, `.env.example`, README |
| 1 | Collection | Port the Google Places collection engine |
| 2 | Cleaning + Enrichment | Port the JS pipeline to Python |
| 3 | Standardized runner | Uniform script invocation + `runs.db` logging |
| 4 | D1 upload | Build the schema + batch upsert to per-directory D1 |
| 5 | White-label template | Genericize `toilets-near-me-au-v2` into `near-me-directory` |
| 6 | Deployment | Script to provision a Cloudflare Pages site per directory |
| 7 | Import tool | Bring existing `dataset-collector` data across |
| 8 | Dashboard | Thin UI over the standardized runner |
| 9 | End-to-end test | Prove the whole pipeline on one real directory |
