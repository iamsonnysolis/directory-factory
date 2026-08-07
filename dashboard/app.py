"""FastAPI dashboard for the Directory Factory.

Phase 8 — a thin, generic UI over the standardized runner.
Server-rendered pages (FastAPI + Jinja2) with vanilla JS for
in-page interactivity (polling, form previews, log expansion).

Binds to 127.0.0.1 only — no authentication (see Dashboard-UX-Decisions.md Q2).
"""

import json
import os
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

for p in [_PROJECT_ROOT, _PROJECT_ROOT / "scripts"]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from runner.run import run_script, SCRIPT_MAP  # noqa: E402
from runner.contract import script_main  # noqa: E402

# ── Jinja2 setup ───────────────────────────────────────────────────────────
_templates = Environment(
    loader=FileSystemLoader(str(_DASHBOARD_DIR / "templates")),
    autoescape=True,
)
_templates.globals["enumerate"] = enumerate

app = FastAPI(title="Directory Factory Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(_DASHBOARD_DIR / "static")), name="static")


# ── Database helpers ───────────────────────────────────────────────────────
def _connect_collector():
    """Connect to the collection DB (SQLite via SQLAlchemy)."""
    return sqlite3.connect(str(_COLLECTION_DB))


def _connect_runs():
    """Connect to runs.db."""
    return sqlite3.connect(str(_RUNS_DB))


# ── .env helpers ───────────────────────────────────────────────────────────
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


# ── Pipeline stage helpers ──────────────────────────────────────────────────
PIPELINE_STAGES = [
    ("collection.collect", "Collect", "🟦"),
    ("cleaning.clean", "Clean", "🟩"),
    ("enrichment.enrich", "Enrich", "🟨"),
    ("upload.d1", "Upload", "🟥"),
]


def _get_project_status(project_id: int) -> dict:
    """Compute directory-level status from runs.db (last run per stage)."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT script_name, status, started_at FROM runs "
        "WHERE project_id = ? ORDER BY started_at DESC",
        (project_id,),
    )
    rows = cursor.fetchall()
    conn.close()

    last_by_stage = {}
    for row in rows:
        name = row["script_name"]
        if name not in last_by_stage:
            last_by_stage[name] = row

    return last_by_stage


# ── API Endpoints ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def overview(request: Request):
    """Directory cards grid — the Overview page."""
    env_dict = _read_env()

    # Read projects from collector.db
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        projects = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, created_at, updated_at "
            "FROM projects ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        projects = []
    conn.close()

    # Build project status info
    project_cards = []
    for proj in projects:
        pid = proj["id"]
        stage_status = _get_project_status(pid)

        # Determine current stage and counts
        counts = {}
        conn2 = _connect_collector()
        try:
            counts["places"] = conn2.execute(
                "SELECT COUNT(*) FROM places WHERE project_id = ?", (pid,)
            ).fetchone()[0]
        except Exception:
            counts["places"] = 0
        conn2.close()

        project_cards.append({
            "id": pid,
            "name": proj["name"],
            "slug": proj["slug"],
            "country": proj["country"],
            "status": proj["status"] or "idle",
            "field_tier": proj["field_tier"] or "Essentials",
            "created_at": proj["created_at"],
            "place_count": counts["places"],
            "stages": stage_status,
        })

    tmpl = _templates.get_template("overview.html")
    html = tmpl.render(
        request=request,
        projects=project_cards,
        env=env_dict,
    )
    return HTMLResponse(content=html)


@app.get("/directories/{project_id}", response_class=HTMLResponse)
async def directory_detail(request: Request, project_id: int):
    """Directory Detail page with tabbed interface."""
    # Verify project exists
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        proj = conn.execute(
            "SELECT id, name, slug, country, status FROM projects WHERE id = ?",
            (project_id,),
        ).fetchone()
    except sqlite3.OperationalError:
        proj = None
    conn.close()

    if not proj:
        raise HTTPException(status_code=404, detail="Directory not found")

    # Get stage status
    stage_status = _get_project_status(project_id)

    # Get place count + job stats
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        place_count = conn.execute(
            "SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    except Exception:
        place_count = 0

    try:
        job_stats = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM jobs WHERE project_id = ? GROUP BY status",
            (project_id,),
        ).fetchall()
    except Exception:
        job_stats = []
    conn.close()

    job_counts = {row["status"]: row["cnt"] for row in job_stats}

    # Get recent runs for this directory
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    recent_runs = conn.execute(
        "SELECT id, script_name, status, summary, started_at, finished_at, error "
        "FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT(20)",
        (project_id,),
    ).fetchall()
    conn.close()

    tmpl = _templates.get_template("directory_detail.html")
    html = tmpl.render(
        request=request,
        project=dict(proj),
        stage_status=stage_status,
        place_count=place_count,
        job_counts=job_counts,
        recent_runs=[dict(r) for r in recent_runs],
        pipeline_stages=PIPELINE_STAGES,
        script_map=SCRIPT_MAP,
    )
    return HTMLResponse(content=html)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page — credentials and defaults."""
    env_dict = _read_env()
    tmpl = _templates.get_template("settings.html")
    html = tmpl.render(request=request, env=env_dict)
    return HTMLResponse(content=html)


# ── API: Trigger script ────────────────────────────────────────────────────

@app.post("/api/run")
async def api_run_script(script_name: str, project_id: int, params: str = "{}"):
    """Trigger a standardized script via the runner.

    This is the single entry point for all pipeline actions from the dashboard.
    """
    if script_name not in SCRIPT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown script: {script_name}. Available: {list(SCRIPT_MAP.keys())}",
        )
    try:
        params_dict = json.loads(params)
    except json.JSONDecodeError:
        params_dict = {}

    result = run_script(script_name, project_id, params_dict)
    return JSONResponse(content=result)


# ── API: Project CRUD ────────────────────────────────────────────────────────

@app.post("/api/projects")
async def api_create_project(
    name: str,
    niche_label: Optional[str] = "local_service_business",
    country: Optional[str] = "Australia",
    field_tier: Optional[str] = "Enterprise",
    search_step_km: Optional[str] = "10",
    search_terms: Optional[str] = "[]",
    target_metros: Optional[str] = "[]",
):
    """Create a new directory project (port of dataset-collector pattern)."""
    import re as re_mod
    slug = re_mod.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "new-directory"

    try:
        terms_list = json.loads(search_terms) if search_terms else []
        metros_list = json.loads(target_metros) if target_metros else []
    except json.JSONDecodeError:
        terms_list = []
        metros_list = []

    conn = _connect_collector()
    try:
        cursor = conn.execute(
            "INSERT INTO projects (name, slug, country, status, field_tier, search_step_km) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, slug, country, "idle", field_tier, int(search_step_km) if search_step_km else None),
        )
        pid = cursor.lastrowid
        conn.commit()

        # Insert search terms
        for term in terms_list:
            conn.execute(
                "INSERT INTO search_terms (project_id, term) VALUES (?, ?)",
                (pid, term),
            )
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "project_id": pid, "slug": slug, "message": f"Created '{name}' ({slug})"}


@app.put("/api/projects/{project_id}")
async def api_update_project(project_id: int, name: Optional[str] = None,
                             slug: Optional[str] = None,
                             niche_label: Optional[str] = None,
                             field_tier: Optional[str] = None):
    """Update a directory project."""
    updates = {}
    if name:
        updates["name"] = name
    if slug:
        updates["slug"] = slug
    if field_tier:
        updates["field_tier"] = field_tier

    if not updates:
        return {"success": False, "message": "No fields to update"}

    conn = _connect_collector()
    try:
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        params = list(updates.values()) + [project_id]
        conn.execute(f"UPDATE projects SET {set_clause} WHERE id = ?", params)
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "message": f"Updated project {project_id}"}


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: int):
    """Delete a directory project (cascade deletes jobs, places, search_terms, logs)."""
    conn = _connect_collector()
    try:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
    finally:
        conn.close()

    return {"success": True, "message": f"Deleted project {project_id}"}


# ── API: Runs history ────────────────────────────────────────────────────────

@app.get("/api/runs")
async def api_runs(project_id: Optional[int] = None, script_name: Optional[str] = "all",
                   status: Optional[str] = "all", limit: int = 50, offset: int = 0):
    """Get runs history, filtered and paginated."""
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

    # Get total count for pagination
    count_query = "SELECT COUNT(*) FROM runs"
    if where_clauses:
        count_query += " WHERE " + " AND ".join(where_clauses)
    total = conn.execute(count_query, count_params).fetchone()[0]

    conn.close()

    return {
        "runs": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/runs/{run_id}")
async def api_run_detail(run_id: int):
    """Get full stdout/stderr for a specific run (Q8 log viewer)."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM runs WHERE id = ?", (run_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    return dict(row)


# ── API: Places search/filter ───────────────────────────────────────────────

@app.get("/api/projects/{project_id}/places")
async def api_places(project_id: int, search: str = "", min_completeness: int = 0,
                     limit: int = 100, offset: int = 0):
    """Search/filter places for a project (ported from dataset-collector)."""
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row

    query = (
        "SELECT id, place_id, display_name, formatted_address, "
        "data_completeness_score, search_term, created_at "
        "FROM places WHERE project_id = ?"
    )
    params = [project_id]
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
        "SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)
    ).fetchone()[0]

    conn.close()

    return {
        "places": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ── API: Cloudflare Analytics pass-through (Phase 8.10) ─────────────────────

@app.get("/api/analytics")
async def api_analytics(account_id: Optional[str] = None, database_id: Optional[str] = None,
                        d1_token: Optional[str] = None):
    """Pass-through to Cloudflare Analytics API.

    Fetches requests, visitors, cache percentage, and top pages for a site.
    """
    import os as _os
    token = d1_token or _os.getenv("CLOUDFLARE_API_TOKEN")
    acct = account_id or _os.getenv("CLOUDFLARE_ACCOUNT_ID")

    if not token or not acct:
        raise HTTPException(
            status_code=401,
            detail="Cloudflare credentials not available",
        )

    headers = {"Authorization": f"Bearer {token}"}
    import requests as req
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/events"
    resp = req.get(url, headers=headers, timeout=10)

    return JSONResponse(content={"cloudflare_response": resp.json()})


# ── API: Credential testing (Phase 8.13 Settings) ───────────────────────────

@app.post("/api/settings/test")
async def api_test_credential(key: Optional[str] = None):
    """Test a single credential by making a trivial API call."""
    env = _read_env()
    value = env.get(key, "")

    if not value:
        return {"tested": key, "valid": False, "message": "Not set in .env"}

    try:
        if key == "GOOGLE_PLACES_API_KEY":
            import httpx
            resp = httpx.get(
                "https://places.googleapis.com/v1/places:searchText",
                params={"text": "test"},
                headers={"X-Goog-Api-Key": value},
                timeout=10,
            )
            ok = resp.status_code == 200
        elif key == "GEMINI_API_KEY":
            import google.genai as genai
            client = genai.Client(api_key=value)
            models = list(client.models.list())  # noqa
            ok = len(models) > 0
        elif key == "CLOUDFLARE_API_TOKEN":
            import requests as req
            resp = req.get(
                "https://api.cloudflare.com/client/v4/user/tokens/verify",
                headers={"Authorization": f"Bearer {value}"},
                timeout=10,
            )
            ok = resp.status_code == 200
        elif key == "GITHUB_TOKEN":
            import requests as req
            resp = req.get(
                "https://api.github.com/user",
                headers={"Authorization": f"token {value}"},
                timeout=10,
            )
            ok = resp.status_code == 200
        else:
            ok = False
        return {"tested": key, "valid": ok, "message": "OK" if ok else "Test failed"}
    except Exception as e:
        return {"tested": key, "valid": False, "message": str(e)}


@app.post("/api/settings/save")
async def api_save_settings(settings: str):
    """Save settings to .env"""
    try:
        settings_dict = json.loads(settings)
    except json.JSONDecodeError:
        settings_dict = {}

    env = _read_env()
    env.update(settings_dict)
    _write_env(env)

    return {"success": True, "message": "Settings saved to .env"}


# ── API: Project status for pipeline stepper ─────────────────────────────────

@app.get("/api/projects/{project_id}/status")
async def api_project_status(project_id: int):
    """Get pipeline status for a project — one headline per stage."""
    stage_status = _get_project_status(project_id)
    status_info = {}
    for script_name, label, icon in PIPELINE_STAGES:
        run = stage_status.get(script_name)
        status_info[script_name] = {
            "label": label,
            "icon": icon,
            "status": run["status"] if run else "not_started",
            "started_at": run["started_at"] if run else None,
        }

    # Get place count
    conn = _connect_collector()
    try:
        place_count = conn.execute(
            "SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    except Exception:
        place_count = 0
    conn.close()

    # Get project name
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        proj = conn.execute(
            "SELECT name, slug FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    except Exception:
        proj = None
    conn.close()

    return {
        "project_id": project_id,
        "project_name": proj["name"] if proj else "",
        "project_slug": proj["slug"] if proj else "",
        "place_count": place_count,
        "stages": status_info,
    }


# ── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import argparse as _argparse

    parser = _argparse.ArgumentParser(description="Directory Factory Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=args.reload)

