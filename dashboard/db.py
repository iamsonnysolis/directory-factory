"""Database connection helpers and .env / site_config persistence.

All _connect_* functions, _ensure_site_config_table, _get_site_config,
_save_site_config, _read_env, and _write_env live here.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .config import COLLECTION_DB, ENV_PATH, RUNS_DB


def _connect_collector():
    """Connect to the collection DB (collector.db)."""
    return sqlite3.connect(str(COLLECTION_DB))


def _connect_runs():
    """Connect to runs.db."""
    return sqlite3.connect(str(RUNS_DB))


def _ensure_site_config_table():
    """Create site_config table in runs.db if it doesn't exist."""
    from runner.run import init_runs_db  # imported lazily to avoid circular import at module load
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
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
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
    ENV_PATH.write_text("\n".join(lines) + "\n")
