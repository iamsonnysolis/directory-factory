"""Grid-based search strategy for comprehensive geographic coverage."""

import json
from typing import Any, Optional
from services.grid_strategy import METRO_AREAS, generate_grid_points, grid_search_radius_meters
from config import settings


def get_project_settings(step_km_override: Optional[int] = None, field_tier_override: Optional[str] = None) -> tuple[int, float, str]:
    """Get collection settings for a project.
    
    Priority: project-level override > .env config > default
    """
    # Project-level step_km override
    step_km = step_km_override
    if step_km is None:
        step_km = getattr(settings, 'SEARCH_STEP_KM', 10)
    
    radius = grid_search_radius_meters(step_km)
    
    # Project-level field_tier override
    field_tier = field_tier_override
    if field_tier is None:
        field_tier = getattr(settings, 'PLACES_FIELD_TIER', 'advanced')
    
    return step_km, radius, field_tier


def generate_search_jobs(project_id: int, search_terms: list[str], 
                         step_km_override: Optional[int] = None, 
                         field_tier_override: Optional[str] = None) -> list[dict[str, Any]]:
    """Generate one job per (search_term, metro_area, grid_point) combination.
    
    This creates significantly better geographic coverage than city-name queries.
    For each metro area with ~20 grid points × 20 results per query = up to 400 candidates
    instead of just 20 results per city-name query.
    """
    jobs = []
    step_km, radius, field_tier = get_project_settings(step_km_override, field_tier_override)
    
    for term in search_terms:
        for metro_name in METRO_AREAS.keys():
            grid_points = generate_grid_points(metro_name, step_km)
            for lat, lng in grid_points:
                jobs.append({
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
                        "field_tier": field_tier
                    })
                })
    
    return jobs


def generate_place_detail_job(project_id: int, place_id: str, search_term: str, metro_name: str) -> dict[str, Any]:
    """Generate a place detail job for a discovered place."""
    return {
        "project_id": project_id,
        "job_type": "place_detail",
        "status": "pending",
        "payload": json.dumps({
            "place_id": place_id,
            "term": search_term,
            "location": metro_name
        })
    }


def calculate_job_count(search_terms: list[str], step_km: int = 10) -> int:
    """Calculate total number of search jobs based on grid density."""
    total = 0
    for metro_name in METRO_AREAS.keys():
        grid_points = generate_grid_points(metro_name, step_km)
        total += len(grid_points)
    return len(search_terms) * total