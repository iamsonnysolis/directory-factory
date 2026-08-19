"""Path constants and pipeline stage configuration loading.

This module is imported first by every other dashboard sub-module.
It loads pipeline-stages.json and exposes the derived constant objects
that routes and services rely on.
"""

import json
import sys
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNNER_DIR = PROJECT_ROOT / "runner"
DASHBOARD_DIR = Path(__file__).resolve().parent
COLLECTION_DB = PROJECT_ROOT / "data" / "collector.db"
RUNS_DB = PROJECT_ROOT / "runs.db"
ENV_PATH = PROJECT_ROOT / ".env"
SITE_CONFIG_DB = RUNS_DB  # site_config stored in runs.db for v1
STAGES_CONFIG_PATH = PROJECT_ROOT / "pipeline-stages.json"

# ── Ensure runner is importable ────────────────────────────────────────────
for p in [PROJECT_ROOT, PROJECT_ROOT / "scripts", RUNNER_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ── Load pipeline stage definitions from config ────────────────────────────
with open(STAGES_CONFIG_PATH, "r") as _f:
    STAGES_CONFIG = json.load(_f)

PIPELINE_STAGES = [
    (s["script_name"], s["label"], s["key"], s.get("icon", "circle"))
    for s in STAGES_CONFIG["pipeline_stages"]
]

# Stage label → script_name for trigger buttons
STAGE_SCRIPTS = {
    s["label"]: s["script_name"] for s in STAGES_CONFIG["pipeline_stages"]
}

# Stage label → action button label
STAGE_ACTION_BUTTONS = {
    s["label"]: s["action_button"] for s in STAGES_CONFIG["pipeline_stages"]
}
