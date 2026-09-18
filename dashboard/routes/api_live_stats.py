"""API routes for live stats — Cloudflare Analytics pass-through."""

from datetime import datetime, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import _read_env

router = APIRouter()


@router.get("/api/directories/{directory_id}/live-stats")
async def api_live_stats(directory_id: int):
    """Live Stats tab — pass-through to Cloudflare Analytics API."""
    env = _read_env()
    token = env.get("CLOUDFLARE_API_TOKEN")
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID")

    if not token or not account_id:
        return JSONResponse(content={
            "error": "Cloudflare credentials not configured",
            "requests": 0, "visitors": 0, "cache_hit_rate": 0,
            "top_pages": [],
        })

    try:
        import httpx
        # Cloudflare Analytics — last 7 days
        end = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        start = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {"Authorization": f"Bearer {token}"}
        url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/events"
        resp = httpx.get(url, headers=headers, timeout=10)

        cf_data = resp.json() if resp.status_code == 200 else {}

        return JSONResponse(content={
            "requests": cf_data.get("total", 0),
            "visitors": cf_data.get("unique_visitors", 0),
            "cache_hit_rate": cf_data.get("cache_hit_rate", 0),
            "top_pages": cf_data.get("top_pages", []),
        })
    except Exception as e:
        return JSONResponse(content={
            "error": str(e),
            "requests": 0, "visitors": 0, "cache_hit_rate": 0,
            "top_pages": [],
        })
