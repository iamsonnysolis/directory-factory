"""API routes for runs history — paginated, filtered run records."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..db import _connect_runs

router = APIRouter()


@router.get("/api/runs")
async def api_runs(project_id: Optional[int] = None, script_name: Optional[str] = "all",
                   status: Optional[str] = "all", limit: int = 50, offset: int = 0):
    """Runs tab — paginated + filtered."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row

    query = "SELECT id, script_name, project_id, status, summary, error, started_at, finished_at FROM runs"
    where_clauses = []
    params: list = []

    if project_id:
        where_clauses.append("project_id = ?")
        params.append(project_id)
    if script_name != "all":
        where_clauses.append("script_name = ?")
        params.append(script_name)
    if status != "all":
        where_clauses.append("status = ?")
        params.append(status)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    count_params = list(params)

    query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM runs" + (" WHERE " + " AND ".join(where_clauses) if where_clauses else ""),
        count_params,
    ).fetchone()[0]

    conn.close()

    return JSONResponse(content={
        "runs": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
    })


@router.get("/api/runs/{run_id}")
async def api_run_detail(run_id: int):
    """Full stdout/stderr for one run (Q8 log viewer)."""
    conn = _connect_runs()
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Run not found")

    return JSONResponse(content=dict(row))
