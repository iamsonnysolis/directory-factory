"""Google Places API client for the Dataset Collection Platform."""

import json
from typing import Optional
import httpx
from config import settings, get_active_fields, FIELD_TIERS


# Field extraction schema with safe defaults
SAFE_FIELD_EXTRACTORS = {
    "id": lambda p: p.get("id"),
    "displayName": lambda p: p.get("displayName", {}).get("text") if isinstance(p.get("displayName"), dict) else p.get("displayName"),
    "formattedAddress": lambda p: p.get("formattedAddress"),
    "location": lambda p: p.get("location"),
    "businessStatus": lambda p: p.get("businessStatus"),
    "types": lambda p: p.get("types", []),
    "primaryType": lambda p: p.get("primaryType"),
}

# Key fields to check for completeness scoring
KEY_FIELDS = [
    "displayName", "formattedAddress", "location", "nationalPhoneNumber",
    "websiteUri", "rating", "userRatingCount", "regularOpeningHours"
]


def _get_fields_for_tier(tier: str) -> list[str]:
    """Get cumulative fields for a tier from FIELD_TIERS config."""
    fields = []
    if tier == "pro":
        fields = FIELD_TIERS["essentials"] + FIELD_TIERS["pro"]
    elif tier == "enterprise":
        fields = FIELD_TIERS["essentials"] + FIELD_TIERS["pro"] + FIELD_TIERS["enterprise"]
    else:  # essentials
        fields = FIELD_TIERS["essentials"]
    return fields


class GooglePlacesClient:
    """Client for Google Places API (New)."""
    
    BASE_URL = "https://places.googleapis.com/v1"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            timeout=settings.REQUEST_TIMEOUT_SECONDS
        )
        self._consecutive_429s = 0
        self._current_delay = 1.0  # Start with 1 second delay
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def _adaptive_sleep(self):
        """Sleep with adaptive backoff based on rate limit hits."""
        import asyncio
        if self._consecutive_429s > 0:
            # Exponential backoff on rate limits
            delay = self._current_delay * (2 ** min(self._consecutive_429s, 5))
            await asyncio.sleep(delay)
    
    def _get_search_headers(self, field_tier_override: Optional[str] = None) -> dict:
        """Get headers for Text Search API requests (requires places. prefix).
        
        If field_tier_override is provided, use that instead of global settings.
        """
        tier = field_tier_override if field_tier_override else settings.PLACES_FIELD_TIER
        fields = _get_fields_for_tier(tier)
        
        fieldmask = ",".join([f"places.{f}" for f in fields])
        return {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": fieldmask,
            "Content-Type": "application/json"
        }
    
    def _get_details_headers(self, field_tier_override: Optional[str] = None) -> dict:
        """Get headers for Place Details API requests (no places. prefix).
        
        If field_tier_override is provided, use that instead of global settings.
        """
        tier = field_tier_override if field_tier_override else settings.PLACES_FIELD_TIER
        fields = _get_fields_for_tier(tier)
        
        return {
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(fields),
            "Content-Type": "application/json"
        }
    
    def _validate_and_extract(self, place: dict) -> dict:
        """Validate place data and extract with safe defaults."""
        validated = {}
        
        # Extract known fields safely
        for field, extractor in SAFE_FIELD_EXTRACTORS.items():
            try:
                validated[field] = extractor(place)
            except Exception:
                validated[field] = None
        
        # Preserve all other fields as raw data
        validated["_raw"] = place
        
        return validated
    
    def calculate_completeness_score(self, place: dict) -> int:
        """Calculate data completeness score (0-100) based on key field presence."""
        if not place:
            return 0
        
        score = 0
        for field in KEY_FIELDS:
            value = place.get(field)
            if value is not None and value != [] and value != {}:
                score += 100 // len(KEY_FIELDS)
        
        return min(score, 100)
    
    def calculate_data_hash(self, place: dict) -> str:
        """Calculate hash of place data for change detection."""
        import hashlib
        # Use stable fields that indicate meaningful changes
        stable_fields = place.get("displayName"), place.get("formattedAddress"), place.get("types")
        data_str = json.dumps(stable_fields, sort_keys=True)
        return hashlib.md5(data_str.encode()).hexdigest()[:16]
    
    async def text_search(self, query: str, page_token: Optional[str] = None, 
                          location_bias: Optional[dict] = None,
                          field_tier_override: Optional[str] = None) -> dict:
        """Execute a text search query with defensive response handling.
        
        Args:
            query: The search term (e.g., "hairdressers")
            page_token: Optional pagination token for next page
            location_bias: Optional dict with "center" {"latitude", "longitude"} and "radius" for circle bias
            field_tier_override: Override the field tier for this request
        """
        url = f"{self.BASE_URL}/places:searchText"
        
        request_body = {"textQuery": query}
        if page_token:
            request_body["pageToken"] = page_token
        
        if location_bias:
            request_body["locationBias"] = location_bias
        
        response = await self.client.post(
            url,
            headers=self._get_search_headers(field_tier_override=field_tier_override),
            json=request_body
        )
        response.raise_for_status()
        
        # Defensive: handle missing 'places' key
        data = response.json()
        if "places" not in data:
            data["places"] = []
        
        return data
    
    async def place_details(self, place_id: str, field_tier_override: Optional[str] = None) -> Optional[dict]:
        """Fetch full details for a place with defensive response handling."""
        url = f"{self.BASE_URL}/places/{place_id}"
        
        response = await self.client.get(
            url,
            headers=self._get_details_headers(field_tier_override=field_tier_override)
        )
        
        if response.status_code == 404:
            return None
        
        if response.status_code != 200:
            response.raise_for_status()
        
        # Return validated response
        return response.json()
    
    async def search_all_pages(self, query: str, max_pages: int = 10) -> list[dict]:
        """Search all pages for a query with error resilience."""
        return await self.search_all_pages_with_bias(query, None, max_pages)
    
    async def search_all_pages_with_bias(self, query: str, location_bias: Optional[dict], 
                                         max_pages: int = 10,
                                         field_tier_override: Optional[str] = None) -> list[dict]:
        """Search all pages for a query with location bias and error resilience."""
        import asyncio
        all_places = []
        page_token = None
        
        for _ in range(max_pages):
            try:
                # Apply adaptive backoff before request
                await self._adaptive_sleep()
                
                result = await self.text_search(query, page_token, location_bias, field_tier_override=field_tier_override)
                places = result.get("places", [])
                all_places.extend(places)
                
                # Reset backoff on success
                self._consecutive_429s = 0
                
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    self._consecutive_429s += 1
                    continue  # Retry after sleep
                # Log error but continue - we'll track failed pages elsewhere
                break
            except Exception as e:
                break
            
            page_token = result.get("nextPageToken")
            if not page_token:
                break
            
            # Wait before next page (API requirement)
            await asyncio.sleep(2)
        
        return all_places