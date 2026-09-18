"""Pipeline state computation and Jinja2 helper functions for templates."""

import sqlite3

from ..config import PIPELINE_STAGES, STAGES_CONFIG


def _get_directory_status(project_id: int) -> dict:
    """Compute directory-level status from runs.db (last run per stage).

    Returns a dict mapping stage_key -> {status, started_at, summary, counts}
    """
    from ..db import _connect_runs
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
    """Compute the 7-step pipeline stepper state for a directory.

    Returns list of {label, state} where state is 'done', 'running', 'paused', or 'not_started'.

    The state is a UNION of two sources:
      1. runs.db — the last run record per stage (success/error/running)
      2. collector.db projects.status — reflects live pause/cancel requests
    When a run shows "running" but projects.status == "paused", the stage
    is reported as "paused" (not "running") so the UI shows "Resume".
    """
    from ..db import _connect_collector
    stage_status = _get_directory_status(project_id)

    # Read the project's live status from collector.db to detect pause/cancel
    # that hasn't yet been reflected in runs.db
    project_status = "idle"
    try:
        conn = _connect_collector()
        row = conn.execute(
            "SELECT status FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        if row:
            project_status = row[0] or "idle"
        conn.close()
    except sqlite3.OperationalError:
        pass  # projects table may not exist

    # Determine which stages are done vs running
    stage_order = [s[0] for s in PIPELINE_STAGES if s[0] not in ("idea", "live")]
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

    # If no running/error stage was found, determine the current stage.
    # Idea is always "done" (directory exists), so if no real stages are done,
    # the first real stage (Collect) is the current/running step.
    if current_stage is None:
        for script in stage_order:
            if script not in done_stages:
                current_stage = script
                break

    # If the project status is "paused", the current stage should be "paused"
    # (the collector loop exits when it sees projects.status != "running")
    if project_status == "paused" and current_stage:
        pass  # will be handled in the state assignment below

    result = []
    for script_name, label, icon_key, icon_name in PIPELINE_STAGES:
        if script_name == "idea":
            # Idea stage: done whenever the directory exists in collector.db
            # (the directory being defined = the Idea being realized),
            # regardless of whether any pipeline runs have happened yet.
            state = "done"
        elif script_name in done_stages:
            state = "done"
        elif current_stage == script_name:
            # This is the current/active stage — check if it's actually running
            run = stage_status.get(script_name)
            if run and run["status"] in ("running", "paused", "error", "success"):
                state = run["status"]
            else:
                # Stage hasn't been run yet — it's the next step, not "running"
                state = "not_started"

            # Override: if projects.status is "paused" in collector.db,
            # treat as paused even if runs.db still says "running"
            if project_status == "paused" and state == "running":
                state = "paused"
        elif script_name == "live":
            # Live stage
            state = "done" if "deploy.provision" in done_stages else "not_started"
        else:
            state = "not_started"

        result.append({"label": label, "state": state, "icon_key": icon_key,
                       "icon_name": icon_name, "script_name": script_name})

    return result


def _current_stage_label(project_id: int) -> tuple[str, str]:
    """Return (stage_label, status_class) for a directory.

    stage_label matches the spec: Idea / Collecting / Cleaning / Enriching /
    Uploading / Deploying / Live / Error
    status_class matches CSS: not-started / running / done / error
    """
    stages = _compute_pipeline_state(project_id)

    # First pass: check for any running or paused or error stage
    for s in stages:
        if s["state"] == "running":
            return s["label"], "running"
        elif s["state"] == "paused":
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


def _stage_progress_pct(counts_json, total_counts, stage_key):
    """Compute progress percentage for a stage card."""
    if not counts_json:
        return 0
    if stage_key == "collecting":
        done = counts_json.get("places", 0)
    elif stage_key == "cleaning":
        done = counts_json.get("cleaned", 0)
    elif stage_key == "enriching":
        done = counts_json.get("ai_generated", 0) or counts_json.get("feature_rows", 0)
    else:
        done = 0
    total = total_counts.get("places_collected", 0) if total_counts else 0
    if total > 0:
        return round(min(done / total * 100, 100))
    return 0


def _full_page_state(project_id: int) -> dict:
    """Compute the COMPLETE pipeline state for a directory in ONE object.

    This is the single source of truth for the Directory Detail page.
    Every render — initial page load and every polling tick — builds
    its entire visible state from a single call to this function.

    Returns:
    - header: {label, status_class, is_running}
    - stepper: list of {key, label, state} (7 dots)
    - done_count, total_stages
    - stat_tiles: {places_collected, enriched_records, enriched_pct, avg_quality_score, monthly_visits}
    - stages: list of stage card dicts with full detail
    - recent_runs: list of run dicts for the activity feed
    - site_config: dict of config values
    - project: {id, name, slug, niche_icon, niche_label, domain}
    """
    from ..db import _connect_collector, _connect_runs, _get_site_config
    from ..services.directories import _directory_counts, _count_enriched_records, _avg_quality_score, _get_niche_icon

    stages = _compute_pipeline_state(project_id)
    counts = _directory_counts(project_id)
    current_label, status_class = _current_stage_label(project_id)
    stage_status = _get_directory_status(project_id)

    # --- Project info ---
    conn = _connect_collector()
    conn.row_factory = sqlite3.Row
    search_terms = []
    try:
        proj = conn.execute(
            "SELECT id, name, slug, country, status, field_tier, created_at, updated_at FROM projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        # Fetch search terms for this project
        term_rows = conn.execute(
            "SELECT term FROM search_terms WHERE project_id = ? ORDER BY id",
            (project_id,)
        ).fetchall()
        search_terms = [t["term"] for t in term_rows] if term_rows else []
    except sqlite3.OperationalError:
        proj = None
    conn.close()

    project = {
        "id": project_id,
        "name": proj["name"] if proj else "Unknown",
        "slug": proj["slug"] if proj else "",
        "field_tier": proj["field_tier"] if proj else "",
        "niche_icon": _get_niche_icon(proj["name"]) if proj else "store",
        "created_at": proj["created_at"] if proj else "",
    }

    # --- Site config ---
    site_config = _get_site_config(project_id)

    # --- Determine is_running for polling ---
    # Poll when any stage is running OR paused (both expect a UI action)
    is_running = any(s["state"] in ("running", "paused") for s in stages)

    # --- Stat tiles ---
    enriched_count = _count_enriched_records(project_id)
    quality_score_avg = _avg_quality_score(project_id)

    stat_tiles = {
        "places_collected": counts["places_collected"],
        "enriched_records": enriched_count,
        "enriched_pct": round(enriched_count / counts["places_collected"] * 100) if counts["places_collected"] > 0 else 0,
        "avg_quality_score": quality_score_avg,
        "monthly_visits": "—",
    }

    # Show monthly visits only if deployed (Live stage done)
    for s in stages:
        if s["script_name"] == "deploy.provision" and s["state"] == "done":
            stat_tiles["monthly_visits"] = "—"  # placeholder until Cloudflare Analytics integrated
            break

    # --- Build stage cards ---
    detail_stages = _pipeline_stages_for_detail()
    stage_cards = []

    for stage in detail_stages:
        stage_key = stage["key"]
        stage_script = stage["script_name"]
        stage_state = _stage_state(stages, stage_script)
        run = stage_status.get(stage_script)

        # Compute progress for this stage
        if stage_key == "collecting":
            # Use collection-progress data for live job counts
            from ..db import _connect_collector as _cc
            _progress_conn = _cc()
            _progress_conn.row_factory = sqlite3.Row
            try:
                _total = _progress_conn.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ?", (project_id,)).fetchone()[0]
                _complete = _progress_conn.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ? AND status = 'complete'", (project_id,)).fetchone()[0]
                _places = _progress_conn.execute("SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)).fetchone()[0]
                _total_places = _progress_conn.execute("SELECT COUNT(*) FROM jobs WHERE project_id = ?", (project_id,)).fetchone()[0]
                _pct = round(_complete / _total * 100) if _total > 0 else 0
                done = _places
            except sqlite3.OperationalError:
                done = counts.get("places_collected", 0)
                _total = counts.get("places_collected", 0)
                _pct = 100 if stage_state == "done" else 0
            _progress_conn.close()
            pct = _pct
            if stage_state in ("running", "paused"):
                total = _total
                count_text = f"{done} / {total}"
            elif stage_state == "done":
                count_text = f"{counts['places_collected']} / {counts['places_collected']}"
                pct = 100
            else:
                count_text = ""
                pct = 0
        elif stage_key == "cleaning":
            done = counts.get("places_cleaned", 0)
            total = counts.get("places_collected", 0)
            if stage_state in ("running", "paused", "done", "error"):
                if total > 0:
                    pct = round(min(done / total * 100, 100))
                else:
                    pct = 0
                count_text = f"{done} / {total}"
            else:
                pct = 0
                count_text = ""
        elif stage_key == "enriching":
            done = enriched_count
            total = counts.get("places_collected", 0)
            if stage_state in ("running", "paused", "done", "error"):
                if total > 0:
                    pct = round(min(done / total * 100, 100))
                else:
                    pct = 0
                count_text = f"{done} / {total}"
            else:
                pct = 0
                count_text = ""
        elif stage_key == "uploading":
            if stage_state == "done":
                pct = 100
                count_text = "Complete"
            elif stage_state in ("running", "paused"):
                pct = 50
                count_text = "Deploying…"
            else:
                pct = 0
                count_text = ""
        elif stage_key == "deploying":
            if stage_state == "done":
                pct = 100
                count_text = "Complete"
            elif stage_state in ("running", "paused"):
                pct = 50
                count_text = "Provisioning…"
            else:
                pct = 0
                count_text = ""
        else:
            pct = 0
            count_text = ""

        # Determine button label and action
        if stage_state == "not_started":
            button_label = stage.get("action_button", "Start")
            button_action = "run"
        elif stage_state == "running" and run and run.get("status") == "running":
            button_label = "Pause"
            button_action = "pause"
        elif stage_state == "paused" and stage_script == "collection.collect":
            button_label = "Resume"
            button_action = "resume"
        elif stage_state == "running":
            button_label = "Cancel"
            button_action = "cancel"
        elif stage_state == "done":
            button_label = "Re-run"
            button_action = "run"
        elif stage_state == "error":
            button_label = "Retry"
            button_action = "run"
        else:
            button_label = stage.get("action_button", "Start")
            button_action = "run"

        # Timestamp
        started_at = ""
        finished_at = ""
        error_msg = ""
        if run:
            started_at = run.get("started_at", "") or ""
            finished_at = run.get("finished_at", "") or ""
            if run.get("status") == "error":
                error_msg = _last_traceback_line(run.get("error", "") or "")

        stage_cards.append({
            "key": stage_key,
            "script_name": stage_script,
            "label": stage["label"],
            "short_label": _stage_short_label(stage_key),
            "icon": _pipeline_icon_for(stage_script),
            "state": stage_state,
            "pill_label": _stage_pill_label(stage_state, stage["label"]),
            "progress_pct": pct,
            "count_text": count_text,
            "started_at": started_at,
            "finished_at": finished_at,
            "error_msg": error_msg,
            "button_label": button_label,
            "button_action": button_action,
            "has_expand_content": stage_key in ("collecting", "cleaning", "enriching", "uploading", "deploying"),
            "expand_type": "places" if stage_key == "collecting" else "log",
            "description": stage.get("description", ""),
        })

    # --- Recent runs for activity feed ---
    conn_runs = _connect_runs()
    conn_runs.row_factory = sqlite3.Row
    try:
        run_rows = conn_runs.execute(
            "SELECT id, script_name, status, started_at, finished_at, summary, error, stdout, stderr "
            "FROM runs WHERE project_id = ? ORDER BY started_at DESC LIMIT 5",
            (project_id,)
        ).fetchall()
        recent_runs = [dict(r) for r in run_rows]
    except Exception:
        recent_runs = []
    conn_runs.close()

    # Format recent runs for the activity feed
    activity_items = []
    for run in recent_runs:
        activity_items.append({
            "script_name": run["script_name"],
            "status": run["status"],
            "started_at": run["started_at"],
            "time": run["started_at"].split("T")[1][:5] if run["started_at"] else "—",
            "summary": run["summary"] or run["status"],
        })

    # --- Header pill ---
    has_error = any(s["state"] == "error" for s in stages)
    header_label = "Error" if has_error else current_label
    header_class = "error" if has_error else status_class

    # Build a sublabel for the secondary status text below the pill
    if has_error:
        sublabel = "One or more stages had errors"
    elif current_label == "Collecting":
        sublabel = f"{counts.get('places_collected', 0)} places collected"
    elif current_label == "Cleaning":
        sublabel = f"{counts.get('places_cleaned', 0)} / {counts.get('places_collected', 0)} cleaned"
    elif current_label == "Enriching":
        sublabel = f"{enriched_count} / {counts.get('places_collected', 0)} enriched"
    elif status_class == "done":
        sublabel = "All stages complete"
    else:
        sublabel = ""

    done_count = _done_count(stages)

    # Build stepper
    stepper = []
    for s in stages:
        stepper.append({
            "key": s["icon_key"],
            "label": _stage_short_label(s["icon_key"]),
            "state": s["state"],
        })

    return {
        "header": {
            "label": header_label,
            "sublabel": sublabel,
            "status_class": header_class,
            "is_running": is_running,
        },
        "stepper": stepper,
        "done_count": done_count,
        "total_stages": len(stages),
        "stat_tiles": stat_tiles,
        "stage_cards": stage_cards,
        "activity_items": activity_items,
        "site_config": {
            "domain": site_config.get("domain", ""),
            "site_name": site_config.get("site_name", proj["name"] if proj else "Directory"),
            "theme_primary_color": site_config.get("theme_primary_color", "#14b8a3"),
            "theme_secondary_color": site_config.get("theme_secondary_color", "#1e293b"),
            "logo_url": site_config.get("logo_url", ""),
            "tagline": site_config.get("tagline", ""),
            "niche_label": site_config.get("niche_label", "local_service_business"),
            "contact_email": site_config.get("contact_email", ""),
            "contact_phone": site_config.get("contact_phone", ""),
            "social_links": site_config.get("social_links", ""),
            "legal_privacy_copy": site_config.get("legal_privacy_copy", ""),
            "legal_terms_copy": site_config.get("legal_terms_copy", ""),
            "og_image_url": site_config.get("og_image_url", ""),
        },
        "project": project,
        "search_terms": search_terms,
        "directory_id": project_id,
    }



def _last_traceback_line(error: str) -> str:
    """Extract the last line of a traceback — the actual ExceptionType: message line."""
    if not error:
        return ""
    lines = error.strip().split("\n")
    # Return the last non-empty line (the exception summary, not "Traceback...")
    return lines[-1].strip() if lines else ""


# ─── Jinja2 helper functions (registered as globals in jinja_setup.py) ──────

def _stage_last_run(project_id: int, script_name: str) -> dict | None:
    """Get the most recent run for a stage from runs.db.

    Returns a dict with started_at/finished_at/summary/status/error or None.
    """
    from ..db import _connect_runs
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, script_name, status, started_at, finished_at, summary, error, stdout, stderr "
            "FROM runs WHERE project_id = ? AND script_name = ? ORDER BY started_at DESC LIMIT 1",
            (project_id, script_name),
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    conn.close()
    return dict(row) if row else None


def _stage_state(stages, script_name):
    """Find the state of a stage by script_name."""
    for s in stages:
        if s["script_name"] == script_name:
            return s["state"]
    return "not_started"


def _stage_pill_label(state, label):
    """Map pipeline state to human-readable pill text."""
    return {
        "done": "Done",
        "running": "Running",
        "paused": "Paused",
        "not_started": "Not started",
        "error": "Error",
    }.get(state, label)


def _done_count(stages):
    """Count stages that are done."""
    return sum(1 for s in stages if s["state"] == "done")


def _pipeline_stages_for_detail():
    """Return pipeline stages excluding idea/live for the stage cards."""
    return [s for s in STAGES_CONFIG["pipeline_stages"] if s["key"] not in ("idea", "live")]


def _pipeline_stages_label(script_name):
    """Map a script_name to its stage label."""
    for s in STAGES_CONFIG["pipeline_stages"]:
        if s["script_name"] == script_name:
            return s["label"]
    return script_name.replace(".", " ").title()


def _pipeline_icon_for(script_name):
    """Map a script_name to its icon name for the detail page stage cards."""
    icon_map = {
        "collection.collect": "map-pin",
        "cleaning.clean": "sparkles",
        "enrichment.enrich": "shirt",
        "upload.d1": "cloud",
        "deploy.provision": "rocket",
        "idea": "lightbulb",
        "live": "globe",
    }
    return icon_map.get(script_name, "store")


def _stage_short_label(stage_key: str) -> str:
    """Map a stage key to the short label used in the Overview card stepper."""
    short_map = {
        "idea": "Idea",
        "collecting": "Collect",
        "cleaning": "Clean",
        "enriching": "Enrich",
        "uploading": "Upload",
        "deploying": "Deploy",
        "live": "Live",
    }
    return short_map.get(stage_key, stage_key)
