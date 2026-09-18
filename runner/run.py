"""Standardized script runner for the Directory Factory.

One consistent way to invoke and log *every* script in the system —
collection, cleaning, enrichment, upload, deploy — regardless of what
language it's written in.

Usage (before the dashboard exists):
    python runner/run.py collection.collect --project-id=5

Scripts must follow the ``@script_main`` contract from ``runner/contract.py``
and print a single JSON line as their last stdout line:
    {"status": "success", "summary": "...", "counts": {...}, "error": null}

This runner:
  1. Invokes the script via subprocess
  2. Parses the JSON output
  3. Records the run (including full stdout and stderr) in runs.db
"""

import argparse
import datetime
import json
import os
import sqlite3
import subprocess
import sys

# All script paths are relative to the project root (parent of runner/).
# We resolve them dynamically so the runner works from any CWD.
# __file__ = directory-factory/runner/run.py
#   dirname(1) = runner/
#   dirname(2) = directory-factory  ← _PROJECT_ROOT
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

SCRIPT_MAP = {
    "collection.collect": "scripts/collection/collect.py",
    "cleaning.clean": "scripts/cleaning_enrichment/cleaning.py",
    "enrichment.enrich": "scripts/cleaning_enrichment/enrichment.py",
    "upload.d1": "scripts/deploy/d1_upload.py",
    "deploy.provision": "scripts/deploy/provision_site.py",
}

# Path to runs.db — lives at the project root
RUNS_DB_PATH = os.path.join(_PROJECT_ROOT, "runs.db")


def _load_env_file():
    """Load .env into os.environ so subprocesses (scripts) inherit credentials.

    Uses setdefault so real environment variables always take precedence
    over .env values.  This ensures d1_upload.py can call os.getenv() and
    get CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, D1_DATABASE_ID, etc.
    """
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE (strip surrounding quotes if present)
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                # Don't override existing env vars
                os.environ.setdefault(key, value)


def init_runs_db(db_path: str = RUNS_DB_PATH) -> None:
    """Create ``runs.db`` and the ``runs`` table if they don't exist.

    Schema includes ``stdout`` and ``stderr`` TEXT columns per
    Dashboard-UX-Decisions.md Q8 (log viewer needs full stdout/stderr).
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            script_name TEXT NOT NULL,
            project_id INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            status TEXT NOT NULL,
            summary TEXT,
            error TEXT,
            stdout TEXT,
            stderr TEXT
        )
    """)
    conn.commit()
    conn.close()


def run_script(script_name: str, project_id: int, params: dict | None = None) -> dict:
    """Run a standardized script and log the result to ``runs.db``.

    Args:
        script_name: Key in ``SCRIPT_MAP`` (e.g. ``"collection.collect"``).
        project_id: The directory project ID to pass via ``--project-id``.
        params: Optional dict of extra parameters (passed via ``--params``).

    Returns:
        The parsed JSON output dict from the script:
        ``{"status": "success"|"error", "summary": str, "counts": dict,
           "error": str|None}``
    """
    if script_name not in SCRIPT_MAP:
        raise ValueError(f"Unknown script: {script_name}. Available: {list(SCRIPT_MAP.keys())}")

    # Load .env into os.environ so scripts can access env vars (e.g. CLOUDFLARE_API_TOKEN)
    _load_env_file()

    script_path = os.path.join(_PROJECT_ROOT, SCRIPT_MAP[script_name])
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")

    cmd = [sys.executable, script_path, "--project-id", str(project_id)]
    if params:
        cmd += ["--params", json.dumps(params)]

    started_at = datetime.datetime.utcnow().isoformat()

    # ─── Insert a 'running' row BEFORE subprocess starts ─────────────────────
    # This makes in-progress runs visible in the Logs tab immediately,
    # not just after the subprocess completes (Dashboard-UX-Decisions Q8).
    init_runs_db()
    # Ensure counts_json column exists
    conn = sqlite3.connect(RUNS_DB_PATH)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(runs)").fetchall()]
    if "counts_json" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN counts_json TEXT")
        conn.commit()
    cursor = conn.execute(
        "INSERT INTO runs "
        "(script_name, project_id, started_at, finished_at, status, summary, error, stdout, stderr, counts_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            script_name, project_id, started_at, started_at,
            "running", None, None, "", "", "{}",
        ),
    )
    run_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # ─── Run the actual script ───────────────────────────────────────────────
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=_PROJECT_ROOT)
    finished_at = datetime.datetime.utcnow().isoformat()

    # Parse the script's JSON output (last non-empty stdout line)
    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    try:
        last_line = stdout.strip().splitlines()[-1]
        output = json.loads(last_line)
    except (IndexError, json.JSONDecodeError):
        output = {
            "status": "error",
            "summary": None,
            "counts": {},
            "error": stderr.strip() or f"Script exited with code {proc.returncode} and produced no JSON output",
        }

    # Ensure all expected keys present
    output.setdefault("summary", None)
    output.setdefault("counts", {})
    output.setdefault("error", None)

    # Log to runs.db (with stdout/stderr per Q8 schema)
    # Update the 'running' row we inserted before the subprocess started
    init_runs_db()
    conn = sqlite3.connect(RUNS_DB_PATH)
    cols = [c[1] for c in conn.execute("PRAGMA table_info(runs)").fetchall()]
    if "counts_json" not in cols:
        conn.execute("ALTER TABLE runs ADD COLUMN counts_json TEXT")
        conn.commit()
    conn.execute(
        "UPDATE runs SET finished_at = ?, status = ?, summary = ?, error = ?, "
        "stdout = ?, stderr = ?, counts_json = ? "
        "WHERE id = ?",
        (
            finished_at,
            output["status"],
            output.get("summary"),
            output.get("error"),
            stdout,
            stderr,
            json.dumps(output.get("counts", {})),
            run_id,
        ),
    )
    conn.commit()
    conn.close()

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a standardized Directory Factory script and log to runs.db"
    )
    parser.add_argument("script_name", choices=list(SCRIPT_MAP.keys()))
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()

    result = run_script(args.script_name, args.project_id, json.loads(args.params))
    print(json.dumps(result, indent=2))
