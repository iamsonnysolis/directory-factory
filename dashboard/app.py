"""FastAPI dashboard for the Directory Factory.

Phase 8.1 — thin, generic UI over the standardized Phase 3 runner.
Server-rendered pages (FastAPI + Jinja2) with vanilla JS for
in-page interactivity (polling, form previews, log expansion).

Binds to 127.0.0.1 only — no authentication (see Dashboard-UX-Decisions.md Q2).
"""

import json
import os
import re
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader

# ── Path setup ─────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RUNNER_DIR = _PROJECT_ROOT / "runner"
_DASHBOARD_DIR = _PROJECT_ROOT / "dashboard"
_COLLECTION_DB = _PROJECT_ROOT / "data" / "collector.db"
_RUNS_DB = _PROJECT_ROOT / "runs.db"
_ENV_PATH = _PROJECT_ROOT / ".env"
_SITE_CONFIG_DB = _RUNS_DB  # site_config stored in runs.db for v1
_STAGES_CONFIG_PATH = _PROJECT_ROOT / "pipeline-stages.json"

# ── Load pipeline stage definitions from config ──────────────────────────────
with open(_STAGES_CONFIG_PATH, "r") as _f:
    _STAGES_CONFIG = json.load(_f)

PIPELINE_STAGES = [
    (s["script_name"], s["label"], s["key"]) for s in _STAGES_CONFIG["pipeline_stages"]
]

# Stage label → script_name for trigger buttons
STAGE_SCRIPTS = {
    s["label"]: s["script_name"] for s in _STAGES_CONFIG["pipeline_stages"]
}

# Stage label → action button label
STAGE_ACTION_BUTTONS = {
    s["label"]: s["action_button"] for s in _STAGES_CONFIG["pipeline_stages"]
}

for p in [_PROJECT_ROOT, _PROJECT_ROOT / "scripts", _PROJECT_ROOT / "runner"]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from runner.run import run_script, SCRIPT_MAP, init_runs_db  # noqa: E402

# ── Jinja2 setup ───────────────────────────────────────────────────────────
_templates = Environment(
    loader=FileSystemLoader(str(_DASHBOARD_DIR / "templates")),
    autoescape=True,
)
_templates.globals["enumerate"] = enumerate


def _format_int(value):
    """Format an integer with thousands separators (e.g. 42 → '42', 1234 → '1,234')."""
    if value is None:
        return "0"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


_templates.filters["format_int"] = _format_int

app = FastAPI(title="Directory Factory Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR / "static")), name="static")


# ── Pydantic models for JSON body parsing ────────────────────────────────────
from pydantic import BaseModel as _BaseModel, Field as _Field, ConfigDict


class DirectoryCreate(_BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    slug: Optional[str] = None
    niche_label: str = "local_service_business"
    field_tier: str = "Enterprise"
    search_step_km: int = 10
    search_terms: list[str] = []
    target_metros: list[str] = []
    domain: Optional[str] = None


class RunScriptRequest(_BaseModel):
    model_config = ConfigDict(extra="forbid")
    script_name: str
    params: dict = {}


# ─── Database helpers ───────────────────────────────────────────────────────
def _connect_collector():
    """Connect to the collection DB (collector.db)."""
    return sqlite3.connect(str(_COLLECTION_DB))


def _connect_runs():
    """Connect to runs.db."""
    return sqlite3.connect(str(_RUNS_DB))


def _ensure_site_config_table():
    """Create site_config table in runs.db if it doesn't exist."""
    init_runs_db()
    conn = _connect_runs()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_config (
            project_id INTEGER PRIMARY KEY,
            config_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def _get_site_config(project_id: int) -> dict:
    """Read site_config for a project from runs.db. Returns empty dict if not set."""
    _ensure_site_config_table()
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT config_json FROM site_config WHERE project_id = ?", (project_id,)
    ).fetchone()
    conn.close()
    if row:
        return json.loads(row["config_json"])
    return {}


def _save_site_config(project_id: int, config: dict) -> None:
    """Save site_config for a project to runs.db."""
    from datetime import datetime
    _ensure_site_config_table()
    conn = _connect_runs()
    conn.execute(
        "INSERT OR REPLACE INTO site_config (project_id, config_json, updated_at) VALUES (?, ?, ?)",
        (project_id, json.dumps(config), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


# ─── .env helpers ───────────────────────────────────────────────────────────
def _read_env():
    """Read .env file into a dict."""
    env = {}
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def _write_env(env: dict):
    """Write .env dict back to file (preserves key order + adds new keys)."""
    existing = _read_env()
    for k, v in env.items():
        existing[k] = v
    lines = []
    for k, v in existing.items():
        lines.append(f"{k}={v}")
    _ENV_PATH.write_text("\n".join(lines) + "\n")



def _get_directory_status(project_id: int) -> dict:
    """Compute directory-level status from runs.db (last run per stage).

    Returns a dict mapping stage_key -> {status, started_at, summary, counts}
    """
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT script_name, status, started_at, finished_at, summary, counts_json, stdout, stderr "
        "FROM runs WHERE project_id = ? ORDER BY started_at DESC",
        (project_id,),
    ).fetchall()
    conn.close()

    last_by_stage = {}
    for row in rows:
        name = row["script_name"]
        if name not in last_by_stage:
            last_by_stage[name] = dict(row)

    return last_by_stage


def _compute_pipeline_state(project_id: int) -> list[dict]:
    """Compute the 6-dot pipeline stepper state for a directory.

    Returns list of {label, state} where state is 'done', 'running', or 'not_started'.
    """
    stage_status = _get_directory_status(project_id)

    # Determine which stages are done vs running
    stage_order = ["collection.collect", "cleaning.clean", "enrichment.enrich",
                    "upload.d1", "deploy.provision"]
    done_stages = set()
    current_stage = None

    for script in stage_order:
        run = stage_status.get(script)
        if run and run["status"] == "success":
            done_stages.add(script)
        elif run and run["status"] == "running":
            current_stage = script
            break
        elif run and run["status"] == "error":
            # Stage errored — mark as error and stop
            current_stage = script
            break
        elif run is None and current_stage is None:
            # Not started yet, and no running stage
            pass

    result = []
    # If no running/error stage was found, mark the first not-done stage as running (current)
    if current_stage is None and done_stages:
        for script in stage_order:
            if script not in done_stages:
                current_stage = script
                break
    # If no running/error stage and no done stages — directory hasn't started, mark as Idea/not-started
    # current_stage stays None, all stages will be "not_started" in the loop below
    if current_stage is None and not done_stages:
        pass  # Leave current_stage as None — all stages become not_started

    result = []
    for script_name, label, icon_key in PIPELINE_STAGES:
        if script_name in done_stages:
            state = "done"
        elif current_stage == script_name:
            # Check if it's actually running or errored
            run = stage_status.get(script_name)
            if run:
                state = run["status"]
            else:
                # Mark this stage as "running" (current/active step)
                state = "running"
        elif current_stage is None and script_name not in done_stages:
            state = "not_started"
        else:
            # If a later stage is current_stage, earlier not-done stages should also be not_started
            # unless they are done
            state = "not_started"

        result.append({"label": label, "state": state, "icon_key": icon_key,
                       "script_name": script_name})

    # Check if deploy is done → Live stage
    if "deploy.provision" in done_stages:
        result[-1] = {"label": "Live", "state": "done", "icon_key": "live",
                      "script_name": "live"}

    return result


def _current_stage_label(project_id: int) -> tuple[str, str]:
    """Return (stage_label, status_class) for a directory.

    stage_label matches the spec: Idea / Collecting / Cleaning / Enriching /
    Uploading / Deploying / Live / Error
    status_class matches CSS: not-started / running / done / error
    """
    stages = _compute_pipeline_state(project_id)

    # First pass: check for any running or error stage
    for s in stages:
        if s["state"] == "running":
            return s["label"], "running"
        elif s["state"] == "error":
            return "Error", "error"

    # No running or error stage — find the last completed stage
    last_done = None
    for s in stages:
        if s["state"] == "done":
            last_done = s

    if last_done:
        # At least one stage is done — show the last completed stage with done status
        # (this handles pipeline gaps where a later stage ran without an earlier one)
        return last_done["label"], "done"

    # No stages done at all — directory hasn't started
    return "Idea", "not-started"


def _directory_counts(project_id: int) -> dict:
    """Get place/feature counts from cleaned/enriched data files."""
    counts = {"places_collected": 0, "places_cleaned": 0, "features_enriched": 0}
    base = _PROJECT_ROOT / "data" / str(project_id)

    # Count collected places from collector.db
    conn = _connect_collector()
    try:
        counts["places_collected"] = conn.execute(
            "SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    except Exception:
        pass
    conn.close()

    # Count cleaned/enriched from flat files
    cleaned_file = base / "cleaned" / "businesses.jsonl"
    if cleaned_file.exists():
        counts["places_cleaned"] = sum(1 for _ in open(cleaned_file))

    enriched_file = base / "enriched" / "business_features.jsonl"
    if enriched_file.exists():
        counts["features_enriched"] = sum(1 for _ in open(enriched_file))

    return counts


# ─── Page routes ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def overview(request: Request, view: str = "overview"):
    """Overview page — grid of directories.

    view='overview' → all directories (default)
    view='pipeline' → same grid, sorted by current stage
    view='deploy' → same grid, filtered to Deploy-done-or-later
    """
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        projects = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, search_step_km, created_at, updated_at "
            "FROM projects ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        projects = []
    conn.close()

    # Build directory cards
    cards = []
    total_places = 0
    live_count = 0
    for proj in projects:
        pid = proj["id"]
        stages = _compute_pipeline_state(pid)
        counts = _directory_counts(pid)
        current_stage_label, status_class = _current_stage_label(pid)
        total_places += counts["places_collected"]
        if status_class == "done" and current_stage_label == "Live":
            live_count += 1

        card = {
            "id": pid,
            "name": proj["name"],
            "slug": proj["slug"],
            "place_count": counts["places_collected"],
            "current_stage": current_stage_label,
            "status_class": status_class,
            "stages": stages,
            "created_at": proj["created_at"] or "",
            "updated_at": proj["updated_at"] or "",
            "action_button_label": "View Project",
        }
        cards.append(card)

    # Apply view filter (IA simplification: Pipeline/Deploy = same grid, different filter/sort)
    if view == "pipeline":
        # Sort by current stage
        stage_order_map = {s[1]: i for i, s in enumerate(PIPELINE_STAGES)}
        cards.sort(key=lambda c: stage_order_map.get(c["current_stage"], 99))
    elif view == "deploy":
        # Filter to Upload-done-or-later (directories that have completed the
        # Upload stage or beyond). This includes directories showing their last
        # completed stage as Upload/Deploy/Live.
        deploy_stages = {"Uploading", "Deploying", "Live"}
        cards = [c for c in cards if c["current_stage"] in deploy_stages]

    # Stat tiles data
    stat_total_dirs = len(cards)
    stat_places_collected = total_places
    stat_live_sites = live_count
    stat_monthly_visits = 0  # placeholder until Cloudflare Analytics integrated

    tmpl = _templates.get_template("overview.html")
    html = tmpl.render(
        request=request,
        directories=cards,
        view=view,
        search_param=request.query_params.get("search", ""),
        stat_total_dirs=stat_total_dirs,
        stat_places_collected=stat_places_collected,
        stat_live_sites=stat_live_sites,
        stat_monthly_visits=stat_monthly_visits,
    )
    return HTMLResponse(content=html)


@app.get("/directories/{directory_id}", response_class=HTMLResponse)
async def directory_detail(request: Request, directory_id: int):
    """Directory Detail page — tabbed interface."""
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        proj = conn.execute(
            "SELECT id, name, slug, country, status, field_tier FROM projects WHERE id = ?",
            (directory_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        proj = None
    conn.close()

    if not proj:
        raise HTTPException(status_code=404, detail="Directory not found")

    stages = _compute_pipeline_state(directory_id)
    counts = _directory_counts(directory_id)
    site_config = _get_site_config(directory_id)

    # Get recent runs for the Runs tab
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    recent_runs = conn.execute(
        "SELECT id, script_name, status, summary, started_at, finished_at, error "
        "FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 20",
        (directory_id,),
    ).fetchall()
    conn.close()

    tmpl = _templates.get_template("directory_detail.html")
    html = tmpl.render(
        request=request,
        project=dict(proj),
        directory_id=directory_id,
        stages=stages,
        counts=counts,
        site_config=site_config,
        recent_runs=[dict(r) for r in recent_runs],
        script_map=SCRIPT_MAP,
        PIPELINE_STAGES=PIPELINE_STAGES,
    )
    return HTMLResponse(content=html)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page — credentials and defaults."""
    env_dict = _read_env()
    tmpl = _templates.get_template("settings.html")
    html = tmpl.render(request=request, env=env_dict)
    return HTMLResponse(content=html)


# ─── API: Directories ────────────────────────────────────────────────────────

@app.get("/api/directories")
async def api_directories(
    search: str = "",
    min_places: int = 0,
    status_filter: str = "",
    sort_by: str = "created_at",
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
):
    """Overview grid data — all directories with optional filters/sort.

    query params:
    - search: search by name or slug
    - min_places: minimum place count filter
    - status_filter: filter by current stage label (e.g. \"Collecting\", \"Live\", \"Error\")
    - sort_by: created_at, name, place_count, current_stage
    - sort_order: asc or desc
    - limit/offset: pagination
    """
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, search_step_km, created_at, updated_at "
            "FROM projects ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    conn.close()

    directories = []
    for proj in rows:
        pid = proj["id"]
        stages = _compute_pipeline_state(pid)
        counts = _directory_counts(pid)
        current_stage_label, status_class = _current_stage_label(pid)

        directories.append({
            "id": pid,
            "name": proj["name"],
            "slug": proj["slug"],
            "country": proj["country"],
            "status": proj["status"] or "idle",
            "field_tier": proj["field_tier"] or "Essentials",
            "place_count": counts["places_collected"],
            "current_stage": current_stage_label,
            "status_class": status_class,
            "stages": stages,
            "created_at": proj["created_at"] or "",
            "updated_at": proj["updated_at"] or "",
            "action_button_label": "View Project",
        })

    # Apply filters
    if search:
        directories = [d for d in directories
                       if search.lower() in d["name"].lower()
                       or search.lower() in d["slug"].lower()]
    if min_places:
        directories = [d for d in directories if d["place_count"] >= min_places]
    if status_filter:
        directories = [d for d in directories if d["current_stage"].lower() == status_filter.lower()]

    # Sort
    if sort_by == "place_count":
        directories.sort(key=lambda d: d["place_count"], reverse=(sort_order == "desc"))
    elif sort_by == "name":
        directories.sort(key=lambda d: d["name"].lower(), reverse=(sort_order == "desc"))
    elif sort_by == "current_stage":
        directories.sort(key=lambda d: d["current_stage"], reverse=(sort_order == "desc"))
    else:
        directories.sort(key=lambda d: d.get("updated_at", d.get("created_at", "")),
                         reverse=(sort_order == "desc"))

    # Pagination
    total = len(directories)
    directories = directories[offset:offset + limit]

    return JSONResponse(content={"directories": directories, "total": total})


@app.get("/api/directories/stats")
async def api_directory_stats():
    """Summary stats for the Overview stat tiles.

    Returns:
    - total_directories: count of all directories
    - places_collected: sum of collected places across all directories
    - live_sites: count of directories at Live stage
    - monthly_visits: estimate (placeholder until Cloudflare Analytics integrated)
    """
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        total_dirs = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0] or 0
        total_places = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] or 0
    except sqlite3.OperationalError:
        total_dirs = 0
        total_places = 0
    conn.close()

    # Count live directories from runs.db
    conn_runs = _connect_runs()
    conn_runs.row_factory = sqlite3.Row
    try:
        live_rows = conn_runs.execute(
            "SELECT DISTINCT project_id FROM runs WHERE script_name = 'deploy.provision' AND status = 'success'"
        ).fetchall()
        live_count = len(live_rows)
    except sqlite3.OperationalError:
        live_count = 0
    conn_runs.close()

    # Monthly visits — placeholder until Cloudflare Analytics integration
    monthly_visits = 0
    env_dict = _read_env()
    if env_dict.get("cloudflare_api_token"):
        # Would call Cloudflare Analytics API here
        monthly_visits = 0  # placeholder

    return JSONResponse(content={
        "total_directories": total_dirs,
        "places_collected": total_places,
        "live_sites": live_count,
        "monthly_visits": monthly_visits,
    })



@app.post("/api/directories")
async def api_create_directory(payload: DirectoryCreate):
    """New Directory wizard submit."""
    name = payload.name
    slug = payload.slug
    niche_label = payload.niche_label
    field_tier = payload.field_tier
    search_step_km = payload.search_step_km
    search_terms = payload.search_terms
    target_metros = payload.target_metros or []
    domain = payload.domain

    if not slug:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "new-directory"

    terms_list = search_terms if search_terms else []
    metros_list = target_metros if target_metros else []

    conn = _connect_collector()
    try:
        cursor = conn.execute(
            "INSERT INTO projects (name, slug, country, status, field_tier, search_step_km) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, slug, "Australia", "idle", field_tier, search_step_km),
        )
        pid = cursor.lastrowid
        conn.commit()

        if pid is None:
            raise HTTPException(status_code=500, detail="Failed to create directory")

        for term in terms_list:
            conn.execute(
                "INSERT INTO search_terms (project_id, term) VALUES (?, ?)",
                (pid, term),
            )
        conn.commit()
    finally:
        conn.close()

    # Save default site_config
    cfg = {
        "site_name": name,
        "tagline": "",
        "niche_label": niche_label or "local_service_business",
        "domain": domain or "",
        "target_metros": metros_list,
        "search_terms": terms_list,
    }
    _save_site_config(pid, cfg)

    return JSONResponse(content={
        "success": True, "directory_id": pid, "slug": slug,
        "message": f"Created '{name}' ({slug})"
    })


@app.get("/api/directories/{directory_id}")
async def api_directory_detail(directory_id: int):
    """Directory Detail header + current stage."""
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        proj = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, created_at, updated_at "
            "FROM projects WHERE id = ?", (directory_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        proj = None
    conn.close()

    if not proj:
        raise HTTPException(status_code=404, detail="Directory not found")

    stages = _compute_pipeline_state(directory_id)
    counts = _directory_counts(directory_id)

    return JSONResponse(content={
        "id": directory_id,
        "name": proj["name"],
        "slug": proj["slug"],
        "country": proj["country"],
        "status": proj["status"] or "idle",
        "field_tier": proj["field_tier"] or "Essentials",
        "current_stage": _current_stage_label(directory_id)[0],
        "status_class": _current_stage_label(directory_id)[1],
        "place_count": counts["places_collected"],
        "cleaned_count": counts["places_cleaned"],
        "feature_count": counts["features_enriched"],
        "stages": stages,
        "created_at": proj["created_at"] or "",
    })


@app.delete("/api/directories/{directory_id}")
async def api_delete_directory(directory_id: int):
    """Delete a directory (after confirm dialog)."""
    conn = _connect_collector()
    try:
        conn.execute("DELETE FROM projects WHERE id = ?", (directory_id,))
        conn.commit()
    finally:
        conn.close()

    # Also clean up runs in runs.db
    try:
        conn_runs = _connect_runs()
        conn_runs.execute("DELETE FROM runs WHERE project_id = ?", (directory_id,))
        conn_runs.commit()
        conn_runs.close()
    except Exception:
        pass

    return JSONResponse(content={"success": True, "message": f"Deleted directory {directory_id}"})


@app.post("/api/directories/{directory_id}/run")
async def api_run_script(directory_id: int, body: RunScriptRequest):
    """Trigger a standardized script via the Phase 3 runner.

    Body: { "script_name": "enrichment.enrich", "params": {"skip_ai": true} }
    Returns immediately with the run result (scripts are synchronous in this v1).
    """
    script_name = body.script_name
    params = body.params

    if script_name not in SCRIPT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown script: {script_name}. Available: {list(SCRIPT_MAP.keys())}",
        )

    # Verify project exists
    conn = _connect_collector()
    try:
        proj = conn.execute(
            "SELECT id FROM projects WHERE id = ?", (directory_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        proj = None
    conn.close()

    if not proj:
        raise HTTPException(status_code=404, detail="Directory not found")

    result = run_script(script_name, directory_id, params)
    return JSONResponse(content=result)


@app.get("/api/directories/{directory_id}/places")
async def api_places(directory_id: int, search: str = "",
                     min_completeness: int = 0, limit: int = 100, offset: int = 0):
    """Collect tab places table — search/filter/pagination."""
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row

    query = (
        "SELECT id, place_id, display_name, formatted_address, "
        "data_completeness_score, search_term, created_at "
        "FROM places WHERE project_id = ?"
    )
    params = [directory_id]
    if search:
        query += " AND (display_name LIKE ? OR formatted_address LIKE ? OR search_term LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term])
    if min_completeness:
        query += " AND data_completeness_score >= ?"
        params.append(min_completeness)

    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    total = conn.execute(
        "SELECT COUNT(*) FROM places WHERE project_id = ?", (directory_id,)
    ).fetchone()[0]

    conn.close()

    return JSONResponse(content={
        "places": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


# ─── API: Runs history ───────────────────────────────────────────────────────

@app.get("/api/runs")
async def api_runs(project_id: Optional[int] = None, script_name: Optional[str] = "all",
                   status: Optional[str] = "all", limit: int = 50, offset: int = 0):
    """Runs tab — paginated + filtered."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row

    query = "SELECT id, script_name, project_id, status, summary, error, started_at, finished_at FROM runs"
    where_clauses = []
    params: list = []

    if project_id:
        where_clauses.append("project_id = ?")
        params.append(project_id)
    if script_name != "all":
        where_clauses.append("script_name = ?")
        params.append(script_name)
    if status != "all":
        where_clauses.append("status = ?")
        params.append(status)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    count_params = list(params)

    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM runs" + (" WHERE " + " AND ".join(where_clauses) if where_clauses else ""),
        count_params,
    ).fetchone()[0]

    conn.close()

    return JSONResponse(content={
        "runs": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: int):
    """Full stdout/stderr for one run (Q8 log viewer)."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    return JSONResponse(content=dict(row))


# ─── API: Config ────────────────────────────────────────────────────────────

@app.get("/api/directories/{directory_id}/config")
async def api_directory_config(directory_id: int):
    """Config tab load — reads site_config from runs.db."""
    config = _get_site_config(directory_id)
    env = _read_env()

    # Merge in defaults
    defaults = {
        "site_name": config.get("site_name", ""),
        "tagline": config.get("tagline", ""),
        "niche_label": config.get("niche_label", env.get("DEFAULT_NICHE_LABEL", "local_service_business")),
        "domain": config.get("domain", ""),
        "theme_primary_color": config.get("theme_primary_color", "#14b8a3"),
        "theme_secondary_color": config.get("theme_secondary_color", "#1e293b"),
        "logo_url": config.get("logo_url", ""),
        "contact_email": config.get("contact_email", ""),
        "contact_phone": config.get("contact_phone", ""),
        "social_links": config.get("social_links", {}),
        "legal_privacy_copy": config.get("legal_privacy_copy", ""),
        "legal_terms_copy": config.get("legal_terms_copy", ""),
        "og_image_url": config.get("og_image_url", ""),
    }
    return JSONResponse(content={"config": defaults})


@app.put("/api/directories/{directory_id}/config")
async def api_update_directory_config(directory_id: int, config: dict):
    """Config tab save — persists to site_config in runs.db."""
    _save_site_config(directory_id, config)
    return JSONResponse(content={"success": True, "message": "Config saved"})


# ─── API: Live Stats (Cloudflare Analytics pass-through) ────────────────────

@app.get("/api/directories/{directory_id}/live-stats")
async def api_live_stats(directory_id: int):
    """Live Stats tab — pass-through to Cloudflare Analytics API."""
    from datetime import datetime, timedelta

    env = _read_env()
    token = env.get("CLOUDFLARE_API_TOKEN")
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID")

    if not token or not account_id:
        return JSONResponse(content={
            "error": "Cloudflare credentials not configured",
            "requests": 0, "visitors": 0, "cache_hit_rate": 0,
            "top_pages": [],
        })

    try:
        import httpx
        # Cloudflare Analytics — last 7 days
        end = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/events"
        resp = httpx.get(url, headers=headers, timeout=10)

        cf_data = resp.json() if resp.status_code == 200 else {}

        return JSONResponse(content={
            "requests": cf_data.get("total", 0),
            "visitors": cf_data.get("unique_visitors", 0),
            "cache_hit_rate": cf_data.get("cache_hit_rate", 0),
            "top_pages": cf_data.get("top_pages", []),
        })
    except Exception as e:
        return JSONResponse(content={
            "error": str(e),
            "requests": 0, "visitors": 0, "cache_hit_rate": 0,
            "top_pages": [],
        })


# ─── API: Settings ──────────────────────────────────────────────────────────

@app.get("/api/settings")
async def api_get_settings():
    """Settings page — read all credentials from .env."""
    return JSONResponse(content=_read_env())


@app.put("/api/settings")
async def api_update_settings(settings: dict):
    """Settings page — save credentials to .env."""
    env = _read_env()
    env.update(settings)
    _write_env(env)
    return JSONResponse(content={"success": True, "message": "Settings saved to .env"})


@app.post("/api/settings/test/{credential}")
async def api_test_credential(credential: str):
    """Test a single credential by making a trivial API call."""
    env = _read_env()
    value = env.get(credential, "")

    if not value:
        return JSONResponse(content={
            "tested": credential, "valid": False, "message": "Not set in .env"
        })

    try:
        if credential == "GOOGLE_PLACES_API_KEY":
            import httpx
            resp = httpx.get(
                "https://places.googleapis.com/v1/places:searchText",
                params={"text": "test"},
                headers={"X-Goog-Api-Key": value},
                timeout=10,
            )
            ok = resp.status_code == 200
        elif credential == "GEMINI_API_KEY":
            import google.genai as genai
            client = genai.Client(api_key=value)
            models = list(client.models.list())
            ok = len(models) > 0
        elif credential == "CLOUDFLARE_API_TOKEN":
            import httpx
            resp = httpx.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {value}"},
                timeout=10,
            )
            ok = resp.status_code == 200
        elif credential == "GITHUB_TOKEN":
            import httpx
            resp = httpx.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {value}"},
                timeout=10,
            )
            ok = resp.status_code == 200
        else:
            ok = False
            return JSONResponse(content={
                "tested": credential, "valid": False, "message": f"Unknown credential: {credential}"
            })

        return JSONResponse(content={
            "tested": credential, "valid": ok,
            "message": "OK" if ok else "Test failed"
        })
    except Exception as e:
        return JSONResponse(content={
            "tested": credential, "valid": False, "message": str(e)
        })


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="Directory Factory Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=args.reload)
