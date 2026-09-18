"""FastAPI dashboard for the Directory Factory.

Phase 8.1 — thin, generic UI over the standardized Phase 3 runner.
Server-rendered pages (FastAPI + Jinja2) with vanilla JS for
in-page interactivity (polling, form previews, log expansion).

Binds to 127.0.0.1 only — no authentication (see Dashboard-UX-Decisions.md Q2).

Structural refactor: app.py is now a thin entry point.  All routes,
helpers, models, config, and Jinja setup live in dedicated modules:
  - config.py        — path constants, pipeline-stages.json loading
  - db.py            — DB connection helpers, .env / site_config persistence
  - models.py        — Pydantic request body models
  - jinja_setup.py   — Jinja2 Environment + all globals/filters registration
  - services/        — pipeline.py, directories.py, credentials.py (business logic)
  - routes/          — pages.py, api_directories.py, api_runs.py,
                       api_config.py, api_live_stats.py, api_settings.py

The consolidated build_directory_card() in services/directories.py is the
single source of truth for directory card shape, used by both the Overview
page route and the /api/directories JSON API route.
"""

import logging

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import DASHBOARD_DIR

logger = logging.getLogger("dashboard")

# ── Jinja2 setup (registers all template globals/filters at import time) ─────
# Importing jinja_setup ensures _templates.globals and _templates.filters are
# populated BEFORE any route renders a template.
from . import jinja_setup  # noqa: F401  -- side-effect import

# ── FastAPI app instance ──────────────────────────────────────────────────────
app = FastAPI(title="Directory Factory Dashboard", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")

# ── Router registration ───────────────────────────────────────────────────────
from .routes.pages import router as pages_router
from .routes.api_directories import router as api_directories_router
from .routes.api_runs import router as api_runs_router
from .routes.api_config import router as api_config_router
from .routes.api_live_stats import router as api_live_stats_router
from .routes.api_settings import router as api_settings_router

app.include_router(pages_router)
app.include_router(api_directories_router)
app.include_router(api_runs_router)
app.include_router(api_config_router)
app.include_router(api_live_stats_router)
app.include_router(api_settings_router)


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
