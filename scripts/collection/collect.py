"""Thin wrapper that exposes the ported collection engine via the standard
``@script_main`` contract so ``runner/run.py`` can invoke it.

Usage:
    python runner/run.py collection.collect --project-id=5

The original collection engine (ported from ``dataset-collector``) uses flat
imports (``from config import settings``, ``from services.collector import
collect_project``) that only resolve when ``scripts/collection/`` is on
``sys.path``. This wrapper handles that path setup before importing.
"""

import asyncio
import json
import os
import sys

# ─── Path setup ───────────────────────────────────────────────────────────────
# The collection engine uses flat imports, so scripts/collection/ must be on
# sys.path. The runner/ package lives at the project root level.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
_COLLECTION_DIR = os.path.join(_SCRIPTS_DIR, "collection")

# _PROJECT_ROOT on path → makes `runner` importable as a package
# _SCRIPTS_DIR on path → makes flat imports (from config import) work
# _COLLECTION_DIR on path → direct collection engine imports
for p in (_PROJECT_ROOT, _SCRIPTS_DIR, _COLLECTION_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from config import settings  # noqa: E402
from runner.contract import script_main  # noqa: E402
from services.collector import collect_project  # noqa: E402


def _prepare_project(project_id: int):
    """Generate search jobs and set project status to 'running'.

    Mirrors the old dataset-collector ``POST /{project_id}/start`` endpoint:
    1. Reads search terms from the DB.
    2. Reads ``target_metros`` from site_config in ``runs.db`` (if available).
    3. Generates one job per (search_term × metro × grid_point) and inserts
       into the ``jobs`` table.
    4. Sets ``project.status = 'running'``.

    This must run *before* ``collect_project()``, which exits immediately
    if the project is not in 'running' status and has no pending jobs.
    """
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models import Project, SearchTerm, Job
    from services.search_strategy import generate_search_jobs
    from services.grid_strategy import METRO_AREAS

    async def _do():
        # Read search terms and project overrides
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if not project:
                return 0

            terms_result = await db.execute(
                select(SearchTerm.term).where(SearchTerm.project_id == project_id)
            )
            search_terms = [t[0] for t in terms_result.fetchall()]

            # Read target_metros from site_config (stored in runs.db)
            target_metros = []
            try:
                import sqlite3
                project_root = os.path.dirname(os.path.dirname(_SCRIPTS_DIR))
                runs_db = os.path.join(project_root, "runs.db")
                conn = sqlite3.connect(runs_db)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT config_json FROM site_config WHERE project_id = ?", (project_id,)
                ).fetchone()
                conn.close()
                if row:
                    cfg = json.loads(row["config_json"])
                    target_metros = cfg.get("target_metros", []) or []
            except Exception:
                pass  # site_config optional — fall back to all metros

            # Count existing jobs
            job_count = await db.execute(
                select(Job.id).where(Job.project_id == project_id).limit(1)
            )
            existing = job_count.scalar_one_or_none()

            if not existing and search_terms:
                # Filter metro areas to only target_metros if set
                all_metros = list(METRO_AREAS.keys())
                if target_metros:
                    metro_names = [m for m in target_metros if m in METRO_AREAS]
                else:
                    metro_names = all_metros

                # Generate jobs — but only for target metros
                # generate_search_jobs uses ALL metros, so we generate per-metro
                jobs_to_add = []
                for term in search_terms:
                    for metro_name in metro_names:
                        from services.grid_strategy import generate_grid_points, grid_search_radius_meters
                        grid_points = generate_grid_points(metro_name, project.search_step_km or settings.SEARCH_STEP_KM)
                        radius = grid_search_radius_meters(project.search_step_km or settings.SEARCH_STEP_KM)
                        field_tier = project.field_tier or settings.PLACES_FIELD_TIER
                        for lat, lng in grid_points:
                            jobs_to_add.append({
                                "project_id": project_id,
                                "job_type": "text_search",
                                "status": "pending",
                                "payload": json.dumps({
                                    "query": term,
                                    "term": term,
                                    "metro_name": metro_name,
                                    "center_lat": lat,
                                    "center_lng": lng,
                                    "radius": radius,
                                    "field_tier": field_tier,
                                }),
                            })

                for job_data in jobs_to_add:
                    db.add(Job(**job_data))
                await db.commit()
                jobs_added = len(jobs_to_add)
            else:
                jobs_added = 0

            # Set project status to running so collect_project() picks it up
            project.status = "running"
            await db.commit()
            return jobs_added

    return asyncio.run(_do())


def _set_project_status(project_id: int, status: str):
    """Set project status (used after collection completes)."""
    from database import AsyncSessionLocal
    from sqlalchemy import select
    from models import Project

    async def _do():
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            if project:
                project.status = status
                await db.commit()

    asyncio.run(_do())


@script_main
def main(project_id: int, params: dict) -> dict:
    """Run collection for a project.

    Prepares the project by generating search jobs and setting status to
    'running', then delegates to the ported ``collect_project()`` async
    function. Returns a summary with the number of places collected.

    Progress is logged at key milestones for real-time monitoring.
    """
    from database import AsyncSessionLocal
    from sqlalchemy import select, func
    from models import Place, Job, SearchTerm
    print(f"[collection.collect] Starting collection for project {project_id}")

    # Step 1: Generate jobs + set status to running (mirrors dataset-collector's /start endpoint)
    print(f"[collection.collect] Preparing project {project_id}...")
    jobs_added = _prepare_project(project_id)

    print(f"[collection.collect] Jobs generated: {jobs_added}")

    # Check if any search terms exist — if not, collection will produce 0 results
    if jobs_added == 0:
        # Check if search terms exist — jobs may already exist from a prior run
        async def _check_search_terms():
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(SearchTerm.term).where(SearchTerm.project_id == project_id))
                terms = [t[0] for t in result.fetchall()]
                result2 = await db.execute(select(func.count(Job.id)).where(Job.project_id == project_id))
                existing_jobs = result2.scalar() or 0
                return terms, existing_jobs
        search_terms, existing_jobs = asyncio.run(_check_search_terms())
        if not search_terms:
            print(f"[collection.collect] ERROR: No search terms configured for project {project_id}")
            return {
                "status": "error",
                "summary": None,
                "counts": {},
                "error": "No search terms configured for this project. Add search terms in the Config tab before running collection.",
            }
        if existing_jobs > 0:
            print(f"[collection.collect] Jobs already exist ({existing_jobs}), skipping generation")

    # Log project details
    async def _log_details():
        async with AsyncSessionLocal() as db:
            terms = await db.execute(select(SearchTerm.term).where(SearchTerm.project_id == project_id))
            search_terms = [t[0] for t in terms.fetchall()]
            print(f"[collection.collect] Search terms: {search_terms}")
    asyncio.run(_log_details())

    # Step 2: Run collection
    print(f"[collection.collect] Starting background collection engine...")
    asyncio.run(collect_project(project_id))

    # Step 3: Set status to complete
    print(f"[collection.collect] Collection engine finished, setting project status to 'complete'")
    _set_project_status(project_id, "complete")

    # Step 4: Count results
    async def _count():
        async with AsyncSessionLocal() as db:
            place_result = await db.execute(
                select(func.count(Place.id)).where(Place.project_id == project_id)
            )
            place_count = place_result.scalar() or 0
            job_result = await db.execute(
                select(func.count(Job.id)).where(Job.project_id == project_id)
            )
            job_count = job_result.scalar() or 0

            # Count by status
            complete_jobs = await db.execute(
                select(func.count(Job.id)).where(Job.project_id == project_id, Job.status == "complete")
            )
            failed_jobs = await db.execute(
                select(func.count(Job.id)).where(Job.project_id == project_id, Job.status == "failed")
            )

            print(f"[collection.collect] Results: {place_count} places collected from {complete_jobs.scalar() or 0} successful jobs ({failed_jobs.scalar() or 0} failed, {job_count} total)")
            return place_count, job_count

    place_count, job_count = asyncio.run(_count())

    print(f"[collection.collect] Collection complete for project {project_id}")

    return {
        "summary": f"Collection complete for project {project_id}: {place_count} places, {job_count} jobs ({jobs_added} new jobs added)",
        "counts": {
            "places": place_count,
            "jobs": job_count,
        },
    }


if __name__ == "__main__":
    main()
