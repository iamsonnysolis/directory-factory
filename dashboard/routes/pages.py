"""Page routes — HTML responses for Overview, Directory Detail, and Settings.

Registered as an APIRouter in app.py.
"""

import sqlite3
import json
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

from ..config import PIPELINE_STAGES
from ..db import _connect_collector, _connect_runs, _get_site_config, _read_env
from ..jinja_setup import _templates
from ..services.directories import (
    build_directory_card,
    _directory_counts,
    _count_enriched_records,
    _avg_quality_score,
    _get_niche_icon,
)
from ..services.pipeline import _compute_pipeline_state, _current_stage_label

# Imported from the runner for SCRIPT_MAP (used in directory_detail template context)
from runner.run import SCRIPT_MAP  # noqa: E402

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def overview(request: Request, view: str = "overview"):
    """Overview page — grid of directories.

    view='overview' -> all directories (default)
    view='pipeline' -> same grid, sorted by current stage
    view='deploy' -> same grid, filtered to Deploy-done-or-later
    """
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    try:
        projects = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, search_step_km, created_at, updated_at "
            "FROM projects WHERE status != 'archived' ORDER BY created_at DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        projects = []
    conn.close()

    # Build directory cards via the consolidated builder
    cards = []
    total_places = 0
    live_count = 0
    for proj in projects:
        card = build_directory_card(proj)
        # Card's place_count == counts["places_collected"] from the internal _directory_counts call
        total_places += card["place_count"]
        if card["status_class"] == "done" and card["current_stage"] == "Live":
            live_count += 1
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
        stat_total_dirs=stat_total_dirs,
        stat_places_collected=stat_places_collected,
        stat_live_sites=stat_live_sites,
        stat_monthly_visits=stat_monthly_visits,
    )
    return HTMLResponse(content=html)


@router.get("/directories/{directory_id}", response_class=HTMLResponse)
async def directory_detail(request: Request, directory_id: int):
    """Directory Detail page — JS-driven UI with a single source of truth.

    The Pipeline tab is rendered by client-side JS from
    GET /api/directories/{id}/pipeline-state (single endpoint, every render).
    Config and Stats tabs use server-rendered data. Logs tab uses
    server-rendered rows.
    """
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

    site_config = _get_site_config(directory_id)

    # Determine current stage for the Stats tab condition
    current_stage_label, status_class = _current_stage_label(directory_id)

    # Fetch recent runs for the server-rendered Logs tab
    conn_runs = _connect_runs()
    conn_runs.row_factory = sqlite3.Row
    try:
        recent_runs = conn_runs.execute(
            "SELECT id, script_name, status, summary, started_at, finished_at, error, stdout, stderr "
            "FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 20",
            (directory_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        recent_runs = []
    conn_runs.close()

    tmpl = _templates.get_template("directory_detail.html")
    html = tmpl.render(
        request=request,
        project={**dict(proj), "niche_icon": _get_niche_icon(proj["name"])},
        directory_id=directory_id,
        site_config=site_config,
        niche_label=site_config.get("niche_label", ""),
        current_stage_label=current_stage_label,
        status_class=status_class,
        PIPELINE_STAGES=PIPELINE_STAGES,
        recent_runs=[dict(r) for r in recent_runs],
    )
    return HTMLResponse(content=html)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings page — credentials and defaults."""
    env_dict = _read_env()
    tmpl = _templates.get_template("settings.html")
    html = tmpl.render(request=request, env=env_dict)
    return HTMLResponse(content=html)
