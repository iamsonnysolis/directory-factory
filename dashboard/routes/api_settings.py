"""API routes for settings — credential read/write and testing."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import _read_env, _write_env
from ..services.credentials import test_credential

router = APIRouter()


@router.get("/api/settings")
async def api_get_settings():
    """Settings page — read all credentials from .env."""
    return JSONResponse(content=_read_env())


@router.put("/api/settings")
async def api_update_settings(settings: dict):
    """Settings page — save credentials to .env."""
    env = _read_env()
    env.update(settings)
    _write_env(env)
    return JSONResponse(content={"success": True, "message": "Settings saved to .env"})


@router.post("/api/settings/test/{credential}")
async def api_test_credential(credential: str):
    """Test a single credential by making a trivial API call.

    The actual testing logic lives in services/credentials.py, which is
    imported here as test_credential.  This route delegates to it.
    """
    env = _read_env()
    value = env.get(credential, "")

    if not value:
        return JSONResponse(content={
            "tested": credential, "valid": False, "message": "Not set in .env"
        })

    try:
        ok, message = test_credential(credential, value)
        return JSONResponse(content={
            "tested": credential, "valid": ok, "message": message
        })
    except Exception as e:
        return JSONResponse(content={
            "tested": credential, "valid": False, "message": str(e)
        })
