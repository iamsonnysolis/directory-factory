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
# sys.path. We also need scripts/ (parent) for runner imports.
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
_COLLECTION_DIR = os.path.join(_PROJECT_ROOT, "scripts", "collection")
_RUNNER_DIR = os.path.join(_PROJECT_ROOT, "scripts", "runner")

for p in (_COLLECTION_DIR, _RUNNER_DIR, os.path.dirname(_RUNNER_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from runner.contract import script_main  # noqa: E402
from services.collector import collect_project  # noqa: E402


@script_main
def main(project_id: int, params: dict) -> dict:
    """Run collection for a project.

    Delegates to the ported ``collect_project()`` async function, running it
    in an event loop. Returns a summary with the number of places collected.
    """
    asyncio.run(collect_project(project_id))

    # After collection, count how many places were added by this run.
    # The collector itself tracks counts via job.status, but we report
    # the project totals for the summary.
    from database import AsyncSessionLocal
    from sqlalchemy import select, func
    from models import Place, Job

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
            return place_count, job_count

    place_count, job_count = asyncio.run(_count())

    return {
        "summary": f"Collection complete for project {project_id}: {place_count} places, {job_count} jobs",
        "counts": {
            "places": place_count,
            "jobs": job_count,
        },
    }


if __name__ == "__main__":
    main()
