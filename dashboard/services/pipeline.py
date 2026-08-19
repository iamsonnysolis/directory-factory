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

    Returns list of {label, state} where state is 'done', 'running', or 'not_started'.
    """
    stage_status = _get_directory_status(project_id)

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
            # Check if it's actually running or errored
            run = stage_status.get(script_name)
            if run:
                state = run["status"]
            else:
                # Mark this stage as "running" (current/active step)
                state = "running"
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


def _stage_last_run(directory_id, script_name):
    """Get the most recent run for a stage (stub — returns None by default)."""
    return None


def _last_traceback_line(error: str) -> str:
    """Extract the last line of a traceback — the actual ExceptionType: message line."""
    if not error:
        return ""
    lines = error.strip().split("\n")
    # Return the last non-empty line (the exception summary, not "Traceback...")
    return lines[-1].strip() if lines else ""


# ─── Jinja2 helper functions (registered as globals in jinja_setup.py) ──────

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
