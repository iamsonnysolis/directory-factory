"""API routes for directories — Overview grid data, CRUD, runs, and data tabs."""

import asyncio
import json
import logging
import re
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import PROJECT_ROOT
from ..db import _connect_collector, _connect_runs, _read_env
from ..models import DirectoryCreate, RunScriptRequest
from ..services.directories import build_directory_card, _directory_counts
from ..services.pipeline import _compute_pipeline_state, _current_stage_label

logger = logging.getLogger("dashboard")

router = APIRouter()


@router.get("/api/directories")
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
    - status_filter: filter by current stage label (e.g. "Collecting", "Live", "Error")
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

    # Build directory cards via the consolidated builder
    directories = [build_directory_card(proj) for proj in rows]

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


@router.get("/api/directories/stats")
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


@router.post("/api/directories")
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
    from ..db import _save_site_config
    _save_site_config(pid, cfg)

    return JSONResponse(content={
        "success": True, "directory_id": pid, "slug": slug,
        "message": f"Created '{name}' ({slug})"
    })


@router.get("/api/directories/{directory_id}")
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


@router.delete("/api/directories/{directory_id}")
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


@router.post("/api/directories/{directory_id}/run")
async def api_run_script(directory_id: int, body: RunScriptRequest):
    """Trigger a standardized script via the Phase 3 runner.

    Body: { "script_name": "collection.collect", "params": {} }

    Runs the script as a background task so the HTTP response returns
    immediately while collection continues server-side. The client
    polls /api/directories/{id} for status updates.
    """
    from runner.run import SCRIPT_MAP, run_script  # imported lazily

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

    # Synchronous validation: check for search terms before starting collection
    if script_name == "collection.collect":
        try:
            conn2 = _connect_collector()
            term_count = conn2.execute(
                "SELECT COUNT(*) FROM search_terms WHERE project_id = ?", (directory_id,)
            ).fetchone()[0]
            conn2.close()
            if term_count == 0:
                return JSONResponse(content={
                    "status": "error",
                    "script_name": script_name,
                    "error": "No search terms configured for this directory. Add search terms in the Config tab before running collection.",
                })
        except sqlite3.OperationalError:
            pass  # search_terms table may not exist yet

    # Run script in background so the HTTP response returns immediately
    async def _run_background():
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: run_script(script_name, directory_id, params))
        except Exception as e:
            logger.error(f"Background run failed for {script_name} on project {directory_id}: {e}")

    asyncio.create_task(_run_background())
    return JSONResponse(content={
        "status": "started",
        "script_name": script_name,
        "message": f"{script_name} started for directory {directory_id}",
    })


@router.get("/api/directories/{directory_id}/places")
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


@router.get("/api/directories/{directory_id}/collection-progress")
async def api_collection_progress(directory_id: int):
    """Collection progress endpoint — returns job counts for real-time progress feedback.

    Returns:
        - total_jobs: total number of jobs for this project
    - pending: jobs waiting to be processed
    - running: jobs currently being processed
    - complete: jobs that finished successfully
    - failed: jobs that failed after all retries
    - places_collected: total places in collector.db for this project
    - project_status: current status from projects table (idle/running/complete)
    - last_log: most recent log entry message
    """
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row

    progress = {
        "total_jobs": 0,
        "pending": 0,
        "running": 0,
        "complete": 0,
        "failed": 0,
        "places_collected": 0,
        "project_status": "idle",
        "last_log": None,
    }

    try:
        # Job counts by status
        progress["total_jobs"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ?", (directory_id,)
        ).fetchone()[0]
        progress["pending"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ? AND status = 'pending'", (directory_id,)
        ).fetchone()[0]
        progress["running"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ? AND status = 'running'", (directory_id,)
        ).fetchone()[0]
        progress["complete"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ? AND status = 'complete'", (directory_id,)
        ).fetchone()[0]
        progress["failed"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE project_id = ? AND status = 'failed'", (directory_id,)
        ).fetchone()[0]

        # Places collected
        progress["places_collected"] = conn.execute(
            "SELECT COUNT(*) FROM places WHERE project_id = ?", (directory_id,)
        ).fetchone()[0]

        # Add percentage for frontend progress display
        if progress["total_jobs"] > 0:
            progress["percentage"] = round(
                progress["complete"] / progress["total_jobs"] * 100
            )
        else:
            progress["percentage"] = 0

        # Project status
        proj = conn.execute(
            "SELECT status FROM projects WHERE id = ?", (directory_id,)
        ).fetchone()
        if proj:
            progress["project_status"] = proj["status"] or "idle"

        # Most recent log entry
        log_row = conn.execute(
            "SELECT level, message, created_at FROM logs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (directory_id,)
        ).fetchone()
        if log_row:
            progress["last_log"] = dict(log_row)
    except sqlite3.OperationalError:
        pass  # Tables may not exist yet

    conn.close()
    return JSONResponse(content=progress)


@router.get("/api/directories/{directory_id}/cleaned")
async def api_cleaned_data(directory_id: int, search: str = "",
                            min_completeness: int = 0, limit: int = 100, offset: int = 0):
    """Cleaned data endpoint — read businesses.jsonl from the cleaned data directory.

    Returns paginated, searchable records from the cleaning stage output.
    """
    base = PROJECT_ROOT / "data" / str(directory_id)
    cleaned_file = base / "cleaned" / "businesses.jsonl"

    if not cleaned_file.exists():
        return JSONResponse(content={
            "records": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        })

    records = []
    try:
        for line in open(cleaned_file):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            # Apply search filter
            if search:
                searchable = (obj.get("name", "") + " " + obj.get("address", "") + " " + obj.get("primary_type", ""))
                if search.lower() not in searchable.lower():
                    continue
            # Apply completeness filter
            if min_completeness:
                cs = obj.get("data_completeness_score", 0) or 0
                if cs < min_completeness:
                    continue
            records.append(obj)
    except Exception:
        pass

    total = len(records)
    records = records[offset:offset + limit]

    return JSONResponse(content={
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.get("/api/directories/{directory_id}/enriched")
async def api_enriched_data(directory_id: int, search: str = "",
                             min_quality: int = 0, limit: int = 100, offset: int = 0):
    """Enriched data endpoint — read businesses.jsonl from the enriched data directory.

    Returns paginated, searchable records from the enrichment stage output,
    including quality scores and AI-generated fields.
    """
    base = PROJECT_ROOT / "data" / str(directory_id)
    enriched_file = base / "enriched" / "businesses.jsonl"

    if not enriched_file.exists():
        return JSONResponse(content={
            "records": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        })

    records = []
    try:
        for line in open(enriched_file):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            # Apply search filter
            if search:
                searchable = (obj.get("name", "") + " " + obj.get("address", "") + " " + obj.get("primary_type", ""))
                if search.lower() not in searchable.lower():
                    continue
            # Apply quality score filter
            if min_quality:
                qs = obj.get("quality_score", 0) or 0
                if qs < min_quality:
                    continue
            records.append(obj)
    except Exception:
        pass

    total = len(records)
    records = records[offset:offset + limit]

    return JSONResponse(content={
        "records": records,
        "total": total,
        "limit": limit,
        "offset": offset,
    })
