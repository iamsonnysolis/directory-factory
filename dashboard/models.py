"""Pydantic models for JSON body parsing."""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DirectoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    slug: Optional[str] = None
    niche_label: str = "local_service_business"
    field_tier: str = "Enterprise"
    search_step_km: int = 10
    search_terms: list[str] = []
    target_metros: list[str] = []
    domain: Optional[str] = None

    @field_validator("search_terms")
    @classmethod
    def require_search_terms(cls, v):
        if not v or len(v) == 0:
            raise ValueError("at least one search term is required")
        return v


class RunScriptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    script_name: str
    params: dict = {}
