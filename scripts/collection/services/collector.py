"""Collection orchestrator for managing Google Places data collection."""

import asyncio
import json
from datetime import datetime
from typing import Any
from sqlalchemy import select, update, func as sql_func
from sqlalchemy.ext.asyncio import AsyncSession
from models import Job, Place, Log, Project
from services.google_places import GooglePlacesClient
from config import settings


async def collect_project(project_id: int):
    """
    Main collection orchestrator.

    Creates its own database session to avoid conflicts with HTTP handlers.
    Processes jobs sequentially to avoid SQLite locking issues.
    """
    from database import AsyncSessionLocal
    
    client = None
    try:
        client = GooglePlacesClient(settings.GOOGLE_PLACES_API_KEY)
        
        # Get project
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Project).where(Project.id == project_id))
            project = result.scalar_one_or_none()
            
            if not project:
                # Log failure and exit
                async with AsyncSessionLocal() as log_db:
                    log = Log(project_id=project_id, level="error",
                              message=f"Project {project_id} not found")
                    log_db.add(log)
                    await log_db.commit()
                return
        
        while True:
            # Check project status in its own transaction
            async with AsyncSessionLocal() as db:
                result = await db.execute(select(Project).where(Project.id == project_id))
                project = result.scalar_one_or_none()
                
                if not project or project.status != "running":
                    break
            
            # Get one pending job at a time
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Job).where(
                        Job.project_id == project_id,
                        Job.status == "pending"
                    ).limit(1)
                )
                job = result.scalar_one_or_none()
                
                if not job:
                    # Check if any running jobs remain
                    async with AsyncSessionLocal() as check_db:
                        result = await check_db.execute(
                            select(Job).where(
                                Job.project_id == project_id,
                                Job.status == "running"
                            ).limit(1)
                        )
                        running = result.scalar_one_or_none()
                        
                        if not running:
                            # Mark project complete
                            async with AsyncSessionLocal() as complete_db:
                                result = await complete_db.execute(
                                    select(Project).where(Project.id == project_id))
                                project = result.scalar_one_or_none()
                                if project:
                                    project.status = "complete"
                                    await complete_db.commit()
                            break
                    await asyncio.sleep(1)
                    continue
                
                # Mark job running
                job.status = "running"
                job.attempts = (job.attempts or 0) + 1
                await db.commit()
                
                # Execute job
                try:
                    if job.job_type == "text_search":
                        result_data = await _execute_text_search(project_id, job, client)
                        job.status = "complete"
                        job.result_count = result_data["places_found"]
                    else:
                        job.status = "complete"
                        job.result_count = 0
                    await db.commit()
                except Exception as e:
                    job.error_message = str(e)[:500]
                    if job.attempts < settings.RETRY_COUNT:
                        job.status = "pending"
                        await db.commit()
                        delay = settings.RETRY_DELAY_SECONDS * job.attempts
                        await asyncio.sleep(delay)
                    else:
                        job.status = "failed"
                        await db.commit()
                        # Log error in separate transaction
                        async with AsyncSessionLocal() as log_db:
                            log = Log(project_id=project_id, level="error",
                                      message=f"Job {job.id} failed after {job.attempts} attempts")
                            log_db.add(log)
                            await log_db.commit()
            
            await asyncio.sleep(0.2)
            
    finally:
        if client:
            await client.close()


async def _execute_text_search(project_id: int, job: Job, client: GooglePlacesClient) -> dict:
    """Execute a text search job and return counts of new/unchanged places.
    
    Uses location bias for grid-based coverage if available in payload.
    
    Returns dict with places_found and places_skipped_unchanged counts.
    """
    from database import AsyncSessionLocal
    
    payload = json.loads(job.payload)
    query = payload["query"]
    term = payload["term"]
    
    # Get location info - support both old format (location) and new format (metro_name + grid point)
    location = payload.get("location", payload.get("metro_name", "unknown"))
    
    # Build location bias if grid point data is available
    location_bias = None
    if "center_lat" in payload and "center_lng" in payload:
        location_bias = {
            "circle": {
                "center": {
                    "latitude": payload["center_lat"],
                    "longitude": payload["center_lng"]
                },
                "radius": payload["radius"]
            }
        }
    
    places_found = 0
    places_skipped_unchanged = 0
    
    try:
        field_tier = payload.get("field_tier", None)
        all_places = await client.search_all_pages_with_bias(query, location_bias, max_pages=5, field_tier_override=field_tier)
        
        for place in all_places:
            place_id = place.get("id")
            if not place_id:
                continue
            
            # Calculate data hash for upsert logic
            data_hash = client.calculate_data_hash(place)
            validated = client._validate_and_extract(place)
            completeness = client.calculate_completeness_score(place)
            
            # Check if place exists AND has unchanged data (smart upsert)
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(Place).where(
                        Place.project_id == project_id,
                        Place.place_id == place_id
                    )
                )
                existing_place = result.scalar_one_or_none()
                
                if existing_place and existing_place.data_hash == data_hash:
                    # Data unchanged - skip to avoid timestamp churn
                    places_skipped_unchanged += 1
                    continue
                
                if existing_place:
                    # Place exists but data changed - update it (upsert)
                    existing_place.raw_json = json.dumps(place)
                    existing_place.display_name = validated.get("displayName")
                    existing_place.formatted_address = validated.get("formattedAddress")
                    existing_place.data_completeness_score = completeness
                    existing_place.data_hash = data_hash
                    existing_place.last_fetched_at = datetime.utcnow()
                    await db.commit()
                    continue
                
                # New place - add to database
                new_place = Place(
                    project_id=project_id,
                    place_id=place_id,
                    search_term=term,
                    search_location=location,
                    raw_json=json.dumps(place),
                    display_name=validated.get("displayName"),
                    formatted_address=validated.get("formattedAddress"),
                    data_completeness_score=completeness,
                    data_hash=data_hash,
                    last_fetched_at=datetime.utcnow()
                )
                db.add(new_place)
                await db.commit()
                places_found += 1
                
    except Exception as e:
        # Log error in separate transaction
        async with AsyncSessionLocal() as db:
            log = Log(project_id=project_id, level="error",
                      message=f"Search job failed: {str(e)[:200]}")
            db.add(log)
            await db.commit()
        raise
    
    return {"places_found": places_found, "places_skipped_unchanged": places_skipped_unchanged}


async def start_collection_background(project_id: int):
    """Entry point for background task."""
    await collect_project(project_id)