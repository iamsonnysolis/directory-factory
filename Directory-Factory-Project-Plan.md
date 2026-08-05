# Directory Factory — Project Plan (v3: Full Rebuild)

> **This replaces the previous plan.** Earlier versions of this doc treated
> the Directory Factory as an in-place extension of the existing
> `dataset-collector` project. That approach is superseded. This version
> builds a **new, standalone system** that copies in working scripts from
> existing projects rather than extending them where they sit, standardizes
> how every script is run and logged, and adds an import tool to bring
> existing collected data across.

---

## How to use this document (task tracking)

Every phase below has a task table with a **Status** column. This doc *is*
the tracker — there's no separate system. As Hermes completes a task, it
edits that row directly: change `Not Started` → `In Progress` → `Done`, add
the date, and note anything worth remembering in **Notes**. If a task is
blocked (e.g. waiting on a path confirmation or a credential), set status to
`Blocked` and say why in Notes rather than skipping it silently.

Status values: `Not Started` · `In Progress` · `Blocked` · `Done`

---

## Path Placeholders — confirm/update before Phase 0

These are carried over from the previous plan's reference sections. Confirm
they're still correct (or update) before Hermes starts copying anything —
Phase 0 depends on them.

| Variable | Confirmed value | Language | Purpose |
|---|---|---|---|
| `OLD_DATASET_COLLECTOR_PATH` | `/home/shanon/web-dev/dataset-collector` | Python (FastAPI) | Source: existing Google Places collection engine |
| `OLD_TOILETSNEARME_DATA_PATH` | `/home/shanon/web-dev/toiletsnearme-data` | JavaScript (Node) | Source: existing cleaning/enrichment/upload pipeline |
| `OLD_TOILETS_NEAR_ME_V2_PATH` | `/home/shanon/web-dev/toilets-near-me-au-v2` | Astro/TypeScript | Source: existing Astro site to white-label |
|| `NEW_DIRECTORY_FACTORY_PATH` | `/home/shanon/web-dev/directory-factory` | Python (see Tech Stack below) | Destination: the new unified system — confirmed by shanon 2026-08-03 |
|| `NEW_NEAR_ME_DIRECTORY_PATH` | `/home/shanon/web-dev/near-me-directory` | Astro/TypeScript (unchanged — see Tech Stack note) | Destination: the white-labeled Astro template repo — confirmed by shanon 2026-08-03 |

---

## Architecture Decisions (confirmed)

- **Local-first orchestrator.** The dashboard/runner lives and runs on the
  laptop (`NEW_DIRECTORY_FACTORY_PATH`), not hosted on Cloudflare. It calls
  out to Google Places, Gemini, and the Cloudflare REST API over HTTP, and
  shells out to `git`/`wrangler` where needed. The deployed *websites*
  remain 100% on Cloudflare Pages/D1 — only the management tool is local.
- **Copy, don't extend.** Working code is copied from the three existing
  projects into the new system and adapted to a standard interface, rather
  than building new functionality directly into `dataset-collector` in
  place.
- **One D1 database per directory.** No shared database with `project_id`
  scoping.
- **Branding/config lives in each site's D1 database** (`site_config`
  table), not in env vars or the codebase — see Phase 5.
- **Standardized script execution + logging.** Every script — collection,
  cleaning, enrichment, upload, deploy — is wrapped in the same run
  interface and writes to the same run log, so the dashboard can trigger and
  monitor any of them identically. See Phase 3.
- **Simple by default.** No hosting, no auth system, no bells and whistles.
  If a phase can be done with a script + a log entry instead of a UI
  feature, do that first.

---

## Tech Stack & Language Decision (confirmed)

**The entire new orchestration system (`NEW_DIRECTORY_FACTORY_PATH`) is
written in Python.** This covers: collection scripts, cleaning/enrichment
scripts, the D1 upload module, the deployment automation script, the
standardized runner, and the dashboard backend.

**Why:** `dataset-collector` is already Python (FastAPI) — porting it is a
straight copy with no rewrite. `toiletsnearme-data` is JavaScript — its
*logic* (address normalization, slug generation, AI enrichment prompts,
scoring) gets ported into Python, it is not copied as JS files. One
language for the whole orchestration system means one dependency setup, one
set of conventions, and nothing for Hermes to context-switch between.
Google's Gemini SDK, HTTP clients, and the Cloudflare REST API are all
equally usable from Python — there's no functional reason to keep two
runtimes.

**Exception — the Astro template stays Astro/TypeScript.**
`near-me-directory` (Phase 5) is the actual website codebase that Cloudflare
Pages builds and serves — it is not part of the orchestration system, and
Astro sites are not written in Python. Do not attempt to port
`toilets-near-me-au-v2` to Python. Everything in `NEW_DIRECTORY_FACTORY_PATH`
is Python; everything in `NEW_NEAR_ME_DIRECTORY_PATH` stays Astro/TypeScript.

### Concrete library choices (use these — don't substitute alternatives)

| Purpose | Library | Notes |
|---|---|---|
| CLI argument parsing | `argparse` | Standard library — no extra dependency |
| Local database (runs log, and any per-project working data) | `sqlite3` | Standard library |
| HTTP calls (Google Places, Gemini, Cloudflare API) | `requests` | Already implied by existing `httpx` use in dataset-collector — either is fine, prefer `httpx` since dataset-collector already depends on it |
| AI enrichment | `google-generativeai` | Already used in the plan for Phase 2 |
| Phone number normalization | `phonenumbers` | Already specified in the old plan |
| Slug generation | `python-slugify` | Already specified in the old plan |
| Dashboard backend | FastAPI | Same framework as `dataset-collector` — consistent with the "copy working patterns" approach |
| Dashboard frontend | Plain HTML/CSS/vanilla JS, served as static files by FastAPI | Same pattern as `dataset-collector`'s existing dashboard (`static/index.html`, `app.js`) — no build step, no framework, matches "no bells and whistles" |

---

# Phase 0: New Repo & Structure Setup

## Objective
Stand up the new `directory-factory` repo with the folder structure
everything else lands in.

```
NEW_DIRECTORY_FACTORY_PATH/
├── scripts/
│   ├── collection/            ← Phase 1 lands here
│   ├── cleaning_enrichment/   ← Phase 2 lands here
│   └── deploy/                ← Phase 4 & 6 land here
├── import/                    ← Phase 7 lands here
├── dashboard/                 ← Phase 8 lands here
├── runner/                    ← Phase 3 lands here (standardized script runner)
├── runs.db                    ← the run-log store (Phase 3)
├── .env                       ← credentials (git-ignored)
├── .env.example
└── README.md
```

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 0.1 | Confirm all path placeholders above | Done | Shanon confirmed: NEW_DIRECTORY_FACTORY_PATH=/home/shanon/web-dev/directory-factory; NEW_NEAR_ME_DIRECTORY_PATH=/home/shanon/web-dev/near-me-directory (2026-08-03) |
|| 0.2 | Create `NEW_DIRECTORY_FACTORY_PATH` with the folder structure above | Done | scripts/{collection,cleaning_enrichment,deploy}, import/, dashboard/, runner/ all created |
|| 0.3 | Init git repo, initial commit | Done | git repo inited on `main`, initial commit `dcccffb` |
|| 0.4 | Create `.env.example` listing every credential this system will need (Google Places key, Gemini key, Cloudflare token + account ID, GitHub token) | Done | .env.example created with all 5 credentials; D1 creds noted as runtime params |
|| 0.5 | Write `README.md` documenting the folder structure and where each phase's code lands | Done | README created with architecture, language, folder tree, phases table |

## Test Process

### Prerequisites
- None. No credentials or external services needed for Phase 0.

### Steps
1. Check the repo exists and has the right structure:
   ```bash
   cd /home/shanon/web-dev/directory-factory
   ls -d scripts/ import/ dashboard/ runner/ 2>&1
   ls .env.example .gitignore README.md
   ```
2. Verify `.env.example` lists all 5 credentials:
   ```bash
   grep -c "REDACTED" .env.example  # should be 5
   ```
3. Verify `.gitignore` has per-line patterns:
   ```bash
   cat .gitignore | head -5
   ```

### Expected Results
- Directory structure matches the plan:
  `scripts/{collection,cleaning_enrichment,deploy}`, `import/`, `dashboard/`, `runner/`
- `.env.example` contains entries for: `GOOGLE_PLACES_API_KEY`, `GEMINI_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `GITHUB_TOKEN`
- `.gitignore` has one pattern per line (no space-separated lists)

---
# Phase 1: Port the Data Collection Engine

## Objective
Copy the existing, working Google Places collection engine across
unmodified in behavior — only its entry point changes, to fit the
standardized runner (Phase 3).

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 1.1 | Copy `OLD_DATASET_COLLECTOR_PATH` (excluding `data/` and `.env`) into `scripts/collection/` | Done | Copied 9 files: config.py, database.py, models.py, requirements.txt, services/{__init__,collector,google_places,grid_strategy,search_strategy}.py. Byte-identical to source. Excluded data/, .env, __pycache__/, venv/, main.py, api/, static/, schemas.py (dashboard/API layer, not collection engine). See note on imports below. |
| 1.2 | Confirm it still runs standalone in its new location (same behavior, same DB schema) before changing anything | Done | VERIFIED via ad-hoc script: all imports resolve, init_db() creates all 5 tables (projects, jobs, places, search_terms, logs), Project CRUD round-trip works. DB schema matches. NOTE: scripts use flat imports (from config import, from services.xxx import) — they only run correctly when CWD is scripts/collection/. Will need path adjustment when wrapping for Phase 3 runner. Also: `httpx` is a runtime dep not in requirements.txt (only phonenumbers + python-slugify listed) — needs to be added to the new system's requirements. |
| 1.3 | Wrap `collect_project()` and friends behind the standard script entry point defined in Phase 3 | Done | Created `scripts/collection/collect.py` — thin wrapper using @script_main. Sets up sys.path for flat imports (scripts/collection/ on path). Calls asyncio.run(collect_project(project_id)). Reports place/job counts from DB. Runnable via `python runner/run.py collection.collect --project-id=N`. |
| 1.4 | Confirm no functional changes were introduced — this is a port, not a rewrite | Done | Collection engine files are byte-identical to dataset-collector source (verified in Phase 1.2). Only the calling interface changed — collect.py is a new wrapper that delegates to the original functions without modification. No changes to collector.py, google_places.py, or any collection engine file. |
| 1.5 | Update `requirements.txt` / merge into the new system's dependency list | Done | Created unified `requirements.txt` at project root. Added missing `httpx>=0.27.0` (was a runtime dep not listed in original requirements.txt). Added `aiosqlite`, `SQLAlchemy`, `pydantic-settings` (collection engine deps). Added `python-slugify`, `google-generativeai` (Phase 2 enrichment deps). Runner is stdlib-only. |

## Test Process

### Prerequisites
- Create a `.env` file with at minimum `GOOGLE_PLACES_API_KEY=***  (the collection engine can't initialize `Settings` without it).
  Also create a `.env` file for the project-root-level runner:
  ```bash
  cp .env.example .env
  # Edit .env, paste a real Google Places API key
  # Create the data/ directory that the SQLite DB lives in:
  mkdir -p data
  ```
- Ensure the venv has the deps installed:
  ```bash
  source .venv/bin/activate  # or create it: python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```

### Steps

1. **Verify collection engine imports resolve standalone:**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   source .venv/bin/activate
   cd scripts/collection
   python3 -c "from config import settings; from database import init_db; from services.collector import collect_project; print('Imports OK')"
   ```
2. **Verify `init_db()` creates all 5 tables:**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   source .venv/bin/activate
   mkdir -p data  # ensure the data/ dir exists for the SQLite DB
   PYTHONPATH=scripts/collection python3 -c "import asyncio; from database import init_db; asyncio.run(init_db())"
   sqlite3 data/collector.db ".tables"  # should show: jobs, log, place, project, search_term
   ```
   **Note:** The DB lives at `data/collector.db` at the **project root** (`/home/shanon/web-dev/directory-factory/data/collector.db`). The `config.py` `DATABASE_URL` is `sqlite:///./data/collector.db` (relative to CWD), so always run commands from the project root. The old `scripts/collection/data/collector.db` was removed — all collection runs use the single project-root DB. If you get "no such table" errors from `sqlite3`, ensure you're running from the project root and have run `init_db()` first.
3. **Create a test project (required before collection — API layer not yet built in Phase 1):**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   source .venv/bin/activate
   python3 -c "
   import asyncio, json, sys, os
   sys.path.insert(0, 'scripts/collection')
   from database import AsyncSessionLocal, init_db
   from models import Project, SearchTerm, Job
   from slugify import slugify

   async def create_test_project():
       os.makedirs('data', exist_ok=True)  # ensure data/ dir exists for SQLite
       await init_db()
       async with AsyncSessionLocal() as db:
           project = Project(
               name='Test Directory',
               slug=slugify('Test Directory'),
               country='Australia',  # or your target country
               search_step_km=0.5,
               field_tier=1,
               status='running'  # must be 'running' for collect_project() to process it
           )
           db.add(project)
           await db.commit()
           await db.refresh(project)
           for term in ['your search term here']:  # e.g. 'mobile dog groomer'
               db.add(SearchTerm(project_id=project.id, term=term))
           await db.commit()
           return {'project_id': project.id, 'name': project.name, 'slug': project.slug, 'status': project.status}

   print(json.dumps(asyncio.run(create_test_project())))
   "
   # Note the project_id from the output — you'll use it in the next step
   ```
   **Note:** In the final system, project creation will be done via the dashboard API (Phase 4). This step is the Phase 1 workaround until the API layer exists.
   
   After testing, clean up the test project:
   ```bash
   python3 -c "
   import asyncio, sys
   sys.path.insert(0, 'scripts/collection')
   from database import AsyncSessionLocal
   from models import Project, SearchTerm, Job, Place, Log
   from sqlalchemy import delete

   async def cleanup():
       async with AsyncSessionLocal() as db:
           for model in [Place, Job, SearchTerm, Log, Project]:
               await db.execute(delete(model))
           await db.commit()
   asyncio.run(cleanup())
   print('Cleaned up test data')
   "
   sqlite3 data/collector.db "DELETE FROM projects WHERE name = 'Test Directory';"
   rm -f data/collector.db runs.db data/cleaned_*.jsonl data/enriched_*.jsonl
   ```
   **Important:** If you get `unable to open database file` errors, ensure the `data/` directory
   exists: `mkdir -p data` (the SQLite DB path is relative to CWD)
4. **Verify `collect_project()` runs via the Phase 3 runner:**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   python runner/run.py collection.collect --project-id=<your_project_id_from_step_3>
   # Creates a run row in runs.db, attempts collection (may 403 if key invalid — that's OK, code path works)
   sqlite3 runs.db "SELECT * FROM runs ORDER BY id DESC LIMIT 1;"
   ```

### Expected Results
- All three imports resolve with no errors
- `init_db()` creates tables: `projects`, `jobs`, `places`, `search_terms`, `logs`
- Test project is created successfully with `status="running"`
- `collect_project()` runs (a 403 from Google Places means the key is invalid — not a code issue)
- Run is logged to `runs.db` with stdout/stderr columns populated

## Constraints
- No functional changes to the collection logic itself during the port —
  only the calling interface changes.

---

# Phase 2: Port the Cleaning + Enrichment Pipeline (JS → Python)

## Objective
`toiletsnearme-data` is JavaScript. Per the Tech Stack decision above, this
is a **logic port to Python**, not a file copy — read each JS file to
understand its approach, then write an equivalent Python module. Do not
copy the `.js` files into the new repo.

## Target files (new, Python)

```
scripts/cleaning_enrichment/
├── cleaning.py       ← ports the logic from enrich.js
├── enrichment.py     ← ports the logic from generate-eeat.js and generate-stats.js
```

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 2.1 | Read `OLD_TOILETSNEARME_DATA_PATH/enrich.js` in full. Write a short plain-English summary of its cleaning steps (address normalization, phone normalization, slug generation, category normalization, opening-hours parsing) before writing any Python | Done | Written `scripts/cleaning_enrichment/enrich_js_summary.md`. Key functions ported: slugify, cleanText, parseBool, parseCoord, isValidCoord, is24Hours, parseOpeningHours. Adapted from ABS CSV-row input to Google Places API response input. |
| 2.2 | Write `cleaning.py` in Python implementing the same steps, using `phonenumbers` for phone normalization, `python-slugify` for slugs, `urllib.parse` for URLs. Function signature: `clean_place(raw_json: dict) -> dict` returning a cleaned record | Done | VERIFIED: 56/56 ad-hoc checks PASS — slugify, clean_text, parse_bool, parse_coord, is_valid_coord, is_24_hours, parse_opening_hours, parse_google_opening_hours, derive_features (with taxonomy filter), derive_notes, clean_place (full record + _raw wrapper + minimal data). |
| 2.3 | Design a per-niche feature taxonomy step (replaces the fixed 21-key toilet taxonomy in `enrich.js`) — draft the first taxonomy against a sample dataset (e.g. Mobile Dog Groomers) and get it reviewed before building extraction logic. Add as `derive_features(raw_json: dict, taxonomy: dict) -> list[dict]` in `cleaning.py` | Done | Drafted taxonomy in `scripts/cleaning_enrichment/taxonomy_draft.md` using real project 42 sample data (5 places). 13 feature keys covering service model, grooming services, amenities, accessibility, operational flags, quality signals. Extraction mapping from Google Places response fields documented. `derive_features` implemented with optional taxonomy filter. |
| 2.4 | Read `OLD_TOILETSNEARME_DATA_PATH/generate-eeat.js` in full. Write a short plain-English summary of its prompt structure and content types before writing any Python | Done | Written `scripts/cleaning_enrichment/generate_eeat_stats_summary.md`. Content types generalized: description, services, specialties, seo_keywords, seo_meta_desc. Prompt builder uses google-generativeai with retry/backoff. |
| 2.5 | Write `enrichment.py` in Python using `google-generativeai`, generating: business description, services list, specialties, SEO keywords, SEO meta description — generic content types instead of toilet-specific EEAT categories. Function signature: `enrich_place(cleaned_record: dict) -> dict` | Done | VERIFIED: build_place_prompt + call_gemini structure confirmed. enrich_place returns dict with 5 content fields + ai_model + generated_at. 10/10 enrichment checks PASS. |
| 2.6 | Read `OLD_TOILETSNEARME_DATA_PATH/generate-stats.js` for its composite-score approach, then add a `compute_quality_score(cleaned_record: dict, enriched_record: dict) -> int` function to `enrichment.py` | Done | VERIFIED: 4 composite functions ported (calc_accessibility_score, calc_family_score, calc_traveller_score, calc_provision_score) + compute_quality_score. 8/8 score checks PASS. |
| 2.7 | Wrap `cleaning.py` and `enrichment.py` behind the standard script entry point from Phase 3 (see the `@script_main` pattern there) | Done | Added `__main__` blocks to both files with @script_main. `cleaning.py` reads raw_json from collector.db, writes cleaned_*.jsonl. `enrichment.py` reads cleaned JSONL, calls enrich_place() via Gemini (skip_ai supported), writes enriched_*.jsonl with quality scores. Both verified via runner end-to-end. |

## Test Process

### Prerequisites
- No API keys needed for basic cleanup/enrichment tests (`enrich_place` supports `skip_ai=true` to skip Gemini calls).
- For the full enrichment test (optional), create `.env` with `GEMINI_API_KEY=*** Ensure deps are installed:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### Steps
1. **Test cleaning.py library functions standalone:**
   ```bash
   cd scripts/cleaning_enrichment
   python3 -c "
   from cleaning import clean_place, clean_text, derive_features, derive_notes
   print('Library imports OK')
   raw = {'displayName': {'text': 'Test Cafe'}, 'formattedAddress': 'Sydney NSW 2000'}
   cleaned = clean_place(raw)
   print(f'Name: {cleaned[\"name\"]}, Slug: {cleaned[\"slug\"]}')
   "
   ```
2. **Test enrichment.py library functions:**
   ```bash
   python3 -c "
   from enrichment import compute_quality_score, build_place_prompt
   print('Library imports OK')
   score = compute_quality_score({'name': 'Test'}, {})
   print(f'Score: {score} (type: {type(score).__name__})')
   "
   ```
3. **Test full pipeline via runner (with test data):**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   # Insert a test place with raw_json into collector.db first, then:
   python runner/run.py cleaning.clean --project-id=9999 --params='{"dry_run": false}'
   python runner/run.py enrichment.enrich --project-id=9999 --params='{"skip_ai": true}'
   cat data/cleaned_9999.jsonl      # should have cleaned record
   cat data/enriched_9999.jsonl    # should have enriched record with quality_score
   sqlite3 runs.db "SELECT script_name, status FROM runs WHERE project_id=9999;"
   ```

### Expected Results
- All library functions import and execute without errors
- `clean_place()` returns a dict with keys: `name`, `slug`, `locality`, `state_code`, `postal_code`, `lat`, `lng`, `quality_score`, `hours_rows`, `feature_keys`
- `compute_quality_score()` returns an integer in 0–100 range
- `build_place_prompt()` returns a non-empty string containing the business name
- Cleaning script reads `raw_json` from `collector.db`, writes `cleaned_*.jsonl`
- Enrichment script reads `cleaned_*.jsonl`, writes `enriched_*.jsonl` with quality scores
- Both runs logged to `runs.db` with `status=success`

## Constraints
- No JavaScript in the new repo. If a piece of `enrich.js` or
  `generate-eeat.js` logic is unclear, re-read the source file rather than
  guessing at Python-equivalent behavior.

---

# Phase 3: Standardized Script Runner

## Objective
One consistent way to invoke and log *every* script in the system —
collection, cleaning, enrichment, upload, deploy — regardless of what
language it's written in.

## The Contract — exact implementation

Build this file first — every other script imports from it:

```python
# runner/contract.py
import argparse
import json
import sys


def script_main(func):
    """
    Decorator for every standardized script entry point.

    `func(project_id: int, params: dict) -> dict` must return a dict with
    at least a "summary" key (str), and optionally a "counts" key (dict).
    Raise a normal Python exception on failure — this wrapper catches it,
    reports it, and exits non-zero. Do not catch-and-swallow errors inside
    `func` itself; let them raise.
    """
    def wrapper():
        parser = argparse.ArgumentParser()
        parser.add_argument("--project-id", type=int, required=True)
        parser.add_argument("--params", type=str, default="{}",
                             help="JSON string of extra parameters")
        args = parser.parse_args()
        params = json.loads(args.params)

        result = {"status": "success", "summary": None, "counts": {}, "error": None}
        try:
            output = func(args.project_id, params)
            result["summary"] = output.get("summary", "")
            result["counts"] = output.get("counts", {})
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        print(json.dumps(result))
        sys.exit(0 if result["status"] == "success" else 1)

    return wrapper
```

**Every script in `scripts/collection/`, `scripts/cleaning_enrichment/`, and
`scripts/deploy/` follows this exact pattern:**

```python
# example: scripts/collection/collect.py
from runner.contract import script_main

@script_main
def main(project_id: int, params: dict) -> dict:
    # ... call the ported collection logic here ...
    places_collected = 123  # replace with real count
    return {
        "summary": f"Collected {places_collected} places",
        "counts": {"places": places_collected},
    }

if __name__ == "__main__":
    main()
```

## The Runner — exact implementation

```python
# runner/run.py
import argparse
import datetime
import json
import sqlite3
import subprocess

SCRIPT_MAP = {
    "collection.collect": "scripts/collection/collect.py",
    "cleaning.clean": "scripts/cleaning_enrichment/cleaning.py",
    "enrichment.enrich": "scripts/cleaning_enrichment/enrichment.py",
    "upload.d1": "scripts/deploy/d1_upload.py",
    "deploy.provision": "scripts/deploy/provision_site.py",
}


def run_script(script_name: str, project_id: int, params: dict | None = None) -> dict:
    script_path = SCRIPT_MAP[script_name]
    cmd = ["python", script_path, "--project-id", str(project_id)]
    if params:
        cmd += ["--params", json.dumps(params)]

    started_at = datetime.datetime.utcnow().isoformat()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    finished_at = datetime.datetime.utcnow().isoformat()

    try:
        last_line = proc.stdout.strip().splitlines()[-1]
        output = json.loads(last_line)
    except (IndexError, json.JSONDecodeError):
        output = {"status": "error", "summary": None, "error": proc.stderr}

    conn = sqlite3.connect("runs.db")
    conn.execute(
        "INSERT INTO runs (script_name, project_id, started_at, finished_at, status, summary, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (script_name, project_id, started_at, finished_at,
         output["status"], output.get("summary"), output.get("error")),
    )
    conn.commit()
    conn.close()

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("script_name", choices=SCRIPT_MAP.keys())
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()
    result = run_script(args.script_name, args.project_id, json.loads(args.params))
    print(json.dumps(result, indent=2))
```

Usage from a terminal, before the dashboard exists:
```bash
python runner/run.py collection.collect --project-id=5
```

## `runs.db` schema (the standardized run log) — exact SQL

```sql
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    script_name TEXT NOT NULL,
    project_id INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    status TEXT NOT NULL,
    summary TEXT,
    error TEXT
);
```

| Column | Purpose |
|---|---|
| `id` | Run ID |
| `script_name` | e.g. `collection.collect`, `cleaning.clean`, `deploy.provision` |
| `project_id` | Which directory this run was for |
| `started_at` / `finished_at` | Timestamps |
| `status` | `success` / `error` |
| `summary` | Short human-readable result |
| `error` | Error message, if any |
| `stdout` | Full stdout from the script (Q8, Dashboard-UX-Decisions.md) |
| `stderr` | Full stderr from the script (Q8, Dashboard-UX-Decisions.md) |

> **Schema note:** The `stdout` and `stderr` TEXT columns (above) are added per Dashboard-UX-Decisions.md Q8 to support the dashboard's full-log viewer. The Phase 3 `run.py` INSERT must capture `proc.stdout` and `proc.stderr` into these columns. This is a small schema addition to the Phase 3 table defined here — see Phase 8 task 8.2 for the endpoint that serves it.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 3.1 | Create `runner/contract.py` exactly as shown above | Done | Created `scripts/runner/contract.py` — @script_main decorator with argparse, JSON params, try/except wrapper, exit codes. |
| 3.2 | Create `runs.db` and run the `CREATE TABLE runs` SQL above against it | Done | Created `runner/run.py:init_runs_db()` with CREATE TABLE IF NOT EXISTS. Schema includes stdout/stderr TEXT columns per Q8 schema note. |
| 3.3 | Create `runner/run.py` exactly as shown above | Done | Created `scripts/runner/run.py` with SCRIPT_MAP (5 entries), run_script(), CLI. Fixed from plan spec: uses sys.executable + sys.path resolution, captures stdout/stderr into DB columns, resolves paths dynamically from project root. |
| 3.4 | Test the runner manually with a throwaway script that just returns `{"summary": "test ok"}` — confirm a row lands in `runs.db` | Done | VERIFIED: throwaway script with @script_main, run_script() returned correct JSON, row logged in runs.db with stdout/stderr captured. Error path also tested (exception → status=error logged). |
| 3.5 | Wrap Phase 1 (collection) scripts using the `@script_main` decorator pattern | Done | Created `scripts/collection/collect.py` — thin wrapper that sets up sys.path for flat imports, calls asyncio.run(collect_project(project_id)), reports counts from DB. |
| 3.6 | Wrap Phase 2 (cleaning/enrichment) scripts using the `@script_main` decorator pattern | Done | Added `__main__` blocks to `cleaning.py` and `enrichment.py` with @script_main. cleaning.py reads raw_json from collector.db, writes cleaned_*.jsonl. enrichment.py reads cleaned JSONL, calls enrich_place() via Gemini, writes enriched_*.jsonl with quality scores. |

## Test Process

### Prerequisites
- Ensure deps are installed:
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

### Steps
1. **Test the runner with a throwaway script:**
   ```bash
   cd /home/shanon/web-dev/directory-factory
   cat > /tmp/test_script.py << 'EOF'
   import sys, os
   sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts", "runner"))
   from runner.contract import script_main

   @script_main
   def main(project_id: int, params: dict) -> dict:
       return {"summary": "test ok", "counts": {"project_id": project_id}}

   if __name__ == "__main__":
       main()
   EOF
   PYTHONPATH=scripts/runner python /tmp/test_script.py --project-id 1 --params '{}'
   # Should output: {"status": "success", "summary": "test ok", "counts": {"project_id": 1}, ...}
   ```
2. **Test end-to-end pipeline (cleaning + enrichment):**
   ```bash
   # Insert test data into collector.db (place with raw_json), then:
   python runner/run.py cleaning.clean --project-id=8888 --params='{"dry_run": false}'
   python runner/run.py enrichment.enrich --project-id=8888 --params='{"skip_ai": true}'
   sqlite3 runs.db "SELECT script_name, status, started_at, finished_at, LENGTH(stdout), LENGTH(stderr) FROM runs WHERE project_id=8888 ORDER BY id;"
   cat data/cleaned_8888.jsonl
   cat data/enriched_8888.jsonl
   ```
3. **Test error handling:**
   ```bash
   python runner/run.py collection.collect --project-id=99999  # nonexistent project
   # Should return status=error, exit code 1, error message in output
   sqlite3 runs.db "SELECT status, error FROM runs ORDER BY id DESC LIMIT 1;"
   ```
4. **Test runs.db schema has stdout/stderr columns:**
   ```bash
   sqlite3 runs.db ".schema runs" | grep -E "stdout|stderr"
   ```

### Expected Results
- Throwaway script returns `{"status": "success", ...}` with the provided summary/counts
- Cleaning + enrichment pipeline produces `cleaned_*.jsonl` and `enriched_*.jsonl` with quality scores
- `runs.db` has rows for each run with `status=success`, non-empty `stdout`, and `stderr` populated
- Error case returns `status=error` with error message, exit code 1, and row logged in `runs.db`
- `runs` table schema includes `stdout TEXT` and `stderr TEXT` columns (added per Q8)

---

# Phase 4: Cloudflare D1 Upload Module

## Objective
New build (not a port) — takes cleaned + enriched records and uploads them
to a directory's own D1 database.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 4.1 | Build D1 schema DDL: `businesses`, `business_features`, `business_hours`, `business_notes`, `site_config` | Not Started | |
| 4.2 | Build `scripts/deploy/d1_upload.py` (or similar) — batch upsert, per-directory D1 credentials passed as params | Not Started | |
| 4.3 | Wrap behind the standard script contract (Phase 3) | Not Started | |
| 4.4 | Test against one directory's cleaned/enriched data | Not Started | |

---

# Phase 5: White-Label the Astro Template (`near-me-directory`)

## Objective
Turn `toilets-near-me-au-v2` into a generic, brandable template, pushed to
its own new GitHub repo — this becomes the single codebase every directory
site deploys from.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 5.1 | Copy `OLD_TOILETS_NEAR_ME_V2_PATH` into `NEW_NEAR_ME_DIRECTORY_PATH` | Not Started | |
| 5.2 | Strip toilet-specific naming: rename components/pages to generic business terminology (`ToiletCard` → `BusinessCard`, etc.) | Not Started | |
| 5.3 | Replace the Supabase client with a D1 client (Cloudflare binding) | Not Started | |
| 5.4 | Build the `site_config` loader — reads branding/config from the bound D1 database at build/render time | Not Started | |
| 5.5 | Genericize feature/enrichment display components to read whatever fields Phase 2/4 produce, rather than toilet-specific fields | Not Started | |
| 5.6 | Route legal pages (privacy/terms/contact) to pull copy from `site_config` | Not Started | |
| 5.7 | Push to a new GitHub repo | Not Started | |
| 5.8 | Manual local test: point the template at one real D1 database and confirm it renders correctly | Not Started | |

---

# Phase 6: Deployment Automation

## Objective
A script that takes one directory's populated D1 database and turns it into
a live Cloudflare Pages site built from `near-me-directory`.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 6.1 | Build `scripts/deploy/provision_site.py` — creates a Cloudflare Pages project via the Cloudflare API, connected to the `near-me-directory` GitHub repo | Not Started | |
| 6.2 | Set the Pages project's env vars — D1 connection details only | Not Started | |
| 6.3 | Bind the directory's D1 database to the Pages project | Not Started | |
| 6.4 | Trigger the first deployment | Not Started | |
| 6.5 | Wrap behind the standard script contract (Phase 3) | Not Started | |

## Out of scope (manual, by Shanon)
- Domain registration and DNS attachment
- Writing initial `site_config` row content (branding copy/colors/logo)

---

# Phase 7: Import Tool

## Objective
A one-time (but safely re-runnable) tool to bring existing data from the
old `dataset-collector` into the new system, so nothing already collected
has to be re-fetched from Google Places.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 7.1 | Build `import/import_from_old_collector.py` — reads directly from `OLD_DATASET_COLLECTOR_PATH/data/collector.db` | Not Started | |
| 7.2 | Map old `projects` + `places` records into the new system's storage format | Not Started | |
| 7.3 | Make it idempotent — safe to re-run without duplicating data (match on `project_id` + `place_id`, same as the original dedup logic) | Not Started | |
| 7.4 | Run once against all 11 existing datasets, confirm counts match the source | Not Started | |

---

# Phase 8: Dashboard

## Objective
A thin, generic UI over the standardized runner — one place to trigger any
script, watch its run log, and manage per-site config. See the separate
dashboard design doc for the full page/element breakdown; this phase is
about building it.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 8.1 | Build dashboard backend — FastAPI app serving all routes, reading `runs.db`, wired to the Phase 3 runner (`runner/run.py:run_script`) | Not Started | Backend is the foundation — no page can be built without it. Server binds to `127.0.0.1` only (see Dashboard-UX-Decisions.md Q2). |
| 8.2 | Expose backing API endpoints: trigger script (→ runner), project CRUD (→ collection DB), runs history (paginated/filtered from `runs.db`), run log detail (full stdout/stderr — see Phase 3 schema note), credentials read/write (`.env`), settings test endpoints, places search/filter, Cloudflare Analytics pass-through | Not Started | These endpoints are called by the pages below. The `stdout`/`stderr` columns for full log output are specified in Dashboard-UX-Decisions.md Q8 — this is the Phase 3 schema addition noted below. |
| 8.3 | Build Overview page (`/`) — directory cards grid, status pills, 6-dot pipeline stepper, "+ New Directory" button | Not Started | Layout per Dashboard-UX-Decisions.md wireframes. |
| 8.4 | Build "New Directory" modal — name→slug, niche label, target metros (multi-select), search terms (tag input), field tier | Not Started | Ported from `dataset-collector` create-project modal pattern. |
| 8.5 | Build Directory Detail page shell (`/directories/{id}`) — tab navigation (Collect/Clean/Enrich/Upload/Deploy/Live Stats/Config/Runs), `[Delete...]` confirm dialog | Not Started | Tabs use plain JS show/hide. Default active tab = current pipeline stage. |
| 8.6 | Build Collect tab panel — places table with map, search/filter, completeness-score filter, pagination, `[Retry Failed]` button, recent log feed, run-status pill + progress bar | Not Started | Straight port of `dataset-collector`'s places table (Dashboard-UX-Decisions.md Q12). `[Retry Failed]` re-runs only failed jobs (already exists in collector logic). |
| 8.7 | Build shared Clean/Enrich/Upload/Deploy panel component — status pill + headline metric, `[Re-run]` button, `[View full log ▾]` expandable | Not Started | Whole-stage re-run only (Q5 is open — don't add per-item retry UI without checking with Shanon). While running: pill pulsing, `[Re-run]` disabled, 3-second polling. |
| 8.8 | Build Clean-specific addition — editable feature taxonomy tag list (add/remove/rename) | Not Started | Per Phase 2.4 — reviewed before extraction logic runs. |
| 8.9 | Build Deploy-specific addition — domain text input, `[Deploy]`/`[View Live Site ↗]` button | Not Started | All other deploy params (repo, branch, build command) fixed per "one shared template" decision. |
| 8.10 | Build Live Stats tab — Cloudflare Analytics API pass-through (requests, visitors, cache %, line chart, top pages), empty state before deploy | Not Started | Plain pass-through call, no local storage of stats. |
| 8.11 | Build Config tab — split form + live in-dashboard mock preview, fields per `site_config` schema (site_name, tagline, niche_label, domain, theme_primary_color, theme_secondary_color, logo_url, contact_email, contact_phone, social_links JSON, legal_privacy_copy, legal_terms_copy, og_image_url), `[Save]` to D1 `site_config` table | Not Started | Preview is HTML/CSS re-rendering on JS input events — no Astro dev server. Field list from Dashboard-UX-Decisions.md Q6. |
| 8.12 | Build Runs tab — filterable (script, status, date range), paginated (20 per page), each row expands to full stdout/stderr from `runs.db` | Not Started | Same log-viewer pattern as per-stage panels. Default filter: current directory. |
| 8.13 | Build Settings page (`/settings`) — masked credential fields (Google Places, Gemini, Cloudflare token+account ID, GitHub) with per-field `[Test]` buttons, default field tier, default grid step; `[Save]` to `.env` | Not Started | Each `[Test]` hits the corresponding endpoint from task 8.2. Bottom-right toasts on save (teal success/red error). |
| 8.14 | Build global shell — top bar (logo/name + Overview/Settings nav links), status pill legend, toast notifications (bottom-right, auto-dismiss ~4s) | Not Started | Used across all pages. Desktop-only (no mobile breakpoints). |
| 8.15 | Wire every action button to the runner from Phase 3 — no bespoke script-invocation logic in the dashboard itself | Not Started | All stage runs, deploys, test endpoints go through `runner/run_script`. Dashboard calls the runner API endpoint from task 8.2 only.

---

# Phase 9: End-to-End Test Launch

## Objective
Prove the whole system works, start to finish, on one real directory before
running the rest through it.

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 9.1 | Pick one directory (recommend Mobile Dog Groomers — smaller dataset) | Not Started | |
| 9.2 | Run it through Collect → Clean → Enrich → Upload → Deploy via the dashboard | Not Started | |
| 9.3 | Manually set up domain/DNS | Not Started | |
| 9.4 | Confirm the live site renders correctly with real data and correct branding | Not Started | |
| 9.5 | Once confirmed, run the remaining directories through the same pipeline | Not Started | |

---

# Agent Working Agreement

- **Work order:** phases in sequence, tasks within a phase in order — don't
  jump ahead to Phase 8 (dashboard) before Phase 3 (the standardized runner)
  exists, since the dashboard is just a UI over the runner.
- **Task tracking:** update the Status column in this document directly as
  work happens. Don't mark something `Done` based on your own test run
  alone — Shanon reviews and confirms before a task is closed out.
- **Ports vs. new builds:** Phases 1, 2, and 5 are ports of working code —
  preserve existing behavior, don't "improve" logic while porting. Phases 4,
  6, 7, and 8 are new builds.
- **Credentials:** Google Places, Gemini, Cloudflare (token + account ID),
  and GitHub credentials all live in `NEW_DIRECTORY_FACTORY_PATH/.env` — ask
  Shanon for any that are missing rather than assuming.
- **Open design questions to raise, not assume:**
  - Per-niche feature taxonomy for each directory beyond the first (Phase 2.4)
  - Exact `site_config` schema (Phase 5.4)
  - Whether the import tool (Phase 7) should also trigger cleaning/enrichment automatically after import, or just land raw data in the new system for those stages to pick up manually
