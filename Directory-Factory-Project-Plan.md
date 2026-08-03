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
| 1.3 | Wrap `collect_project()` and friends behind the standard script entry point defined in Phase 3 | Not Started | Do this after Phase 3's contract is defined |
| 1.4 | Confirm no functional changes were introduced — this is a port, not a rewrite | Not Started | |
| 1.5 | Update `requirements.txt` / merge into the new system's dependency list | Not Started | |

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
| 2.1 | Read `OLD_TOILETSNEARME_DATA_PATH/enrich.js` in full. Write a short plain-English summary of its cleaning steps (address normalization, phone normalization, slug generation, category normalization, opening-hours parsing) before writing any Python | Not Started | Do this understanding step first — don't translate line-by-line |
| 2.2 | Write `cleaning.py` in Python implementing the same steps, using `phonenumbers` for phone normalization, `python-slugify` for slugs, `urllib.parse` for URLs. Function signature: `clean_place(raw_json: dict) -> dict` returning a cleaned record | Not Started | |
| 2.3 | Design a per-niche feature taxonomy step (replaces the fixed 21-key toilet taxonomy in `enrich.js`) — draft the first taxonomy against a sample dataset (e.g. Mobile Dog Groomers) and get it reviewed before building extraction logic. Add as `derive_features(raw_json: dict, taxonomy: dict) -> list[dict]` in `cleaning.py` | Not Started | Open design task — review with Shanon before building |
| 2.4 | Read `OLD_TOILETSNEARME_DATA_PATH/generate-eeat.js` in full. Write a short plain-English summary of its prompt structure and content types before writing any Python | Not Started | |
| 2.5 | Write `enrichment.py` in Python using `google-generativeai`, generating: business description, services list, specialties, SEO keywords, SEO meta description — generic content types instead of toilet-specific EEAT categories. Function signature: `enrich_place(cleaned_record: dict) -> dict` | Not Started | |
| 2.6 | Read `OLD_TOILETSNEARME_DATA_PATH/generate-stats.js` for its composite-score approach, then add a `compute_quality_score(cleaned_record: dict, enriched_record: dict) -> int` function to `enrichment.py` | Not Started | |
| 2.7 | Wrap `cleaning.py` and `enrichment.py` behind the standard script entry point from Phase 3 (see the `@script_main` pattern there) | Not Started | Do this after Phase 3 exists |

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

## Tasks

| ID | Task | Status | Notes |
|---|---|---|---|
| 3.1 | Create `runner/contract.py` exactly as shown above | Not Started | |
| 3.2 | Create `runs.db` and run the `CREATE TABLE runs` SQL above against it | Not Started | |
| 3.3 | Create `runner/run.py` exactly as shown above | Not Started | |
| 3.4 | Test the runner manually with a throwaway script that just returns `{"summary": "test ok"}` — confirm a row lands in `runs.db` | Not Started | Do this before wiring in real scripts |
| 3.5 | Wrap Phase 1 (collection) scripts using the `@script_main` decorator pattern | Not Started | Depends on 3.1 |
| 3.6 | Wrap Phase 2 (cleaning/enrichment) scripts using the `@script_main` decorator pattern | Not Started | Depends on 3.1 |

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
| 8.1 | Build the dashboard backend — reads `runs.db`, exposes endpoints to trigger any script via the runner (Phase 3) | Not Started | |
| 8.2 | Build the Overview page (directory cards, status pills, pipeline stepper) | Not Started | |
| 8.3 | Build the Directory Detail page (per-stage panels: Collect/Clean/Enrich/Upload/Deploy) | Not Started | |
| 8.4 | Build the Config panel — `site_config` editor with live preview | Not Started | |
| 8.5 | Build the Live Stats panel — pulls from the Cloudflare Analytics API once a site is deployed | Not Started | |
| 8.6 | Wire every action button to the runner from Phase 3 — no bespoke logic in the dashboard itself | Not Started | |

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
