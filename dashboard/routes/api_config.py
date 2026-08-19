"""API routes for directory config — site_config read/write."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..db import _get_site_config, _save_site_config, _read_env

router = APIRouter()


@router.get("/api/directories/{directory_id}/config")
async def api_directory_config(directory_id: int):
    """Config tab load — reads site_config from runs.db."""
    config = _get_site_config(directory_id)
    env = _read_env()

    # Merge in defaults
    defaults = {
        "site_name": config.get("site_name", ""),
        "tagline": config.get("tagline", ""),
        "niche_label": config.get("niche_label", env.get("DEFAULT_NICHE_LABEL", "local_service_business")),
        "domain": config.get("domain", ""),
        "theme_primary_color": config.get("theme_primary_color", "#14b8a3"),
        "theme_secondary_color": config.get("theme_secondary_color", "#1e293b"),
        "logo_url": config.get("logo_url", ""),
        "contact_email": config.get("contact_email", ""),
        "contact_phone": config.get("contact_phone", ""),
        "social_links": config.get("social_links", {}),
        "legal_privacy_copy": config.get("legal_privacy_copy", ""),
        "legal_terms_copy": config.get("legal_terms_copy", ""),
        "og_image_url": config.get("og_image_url", ""),
    }
    return JSONResponse(content={"config": defaults})


@router.put("/api/directories/{directory_id}/config")
async def api_update_directory_config(directory_id: int, config: dict):
    """Config tab save — persists to site_config in runs.db."""
    _save_site_config(directory_id, config)
    return JSONResponse(content={"success": True, "message": "Config saved"})
