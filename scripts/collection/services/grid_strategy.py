"""Grid-based search strategy for comprehensive geographic coverage."""

import math


# Australian metro areas as bounding boxes (lat_min, lat_max, lng_min, lng_max)
METRO_AREAS = {
    "Sydney": (-34.20, -33.40, 150.50, 151.35),
    "Melbourne": (-38.20, -37.50, 144.44, 145.55),
    "Brisbane": (-27.90, -27.10, 152.55, 153.55),
    "Perth": (-32.30, -31.55, 115.65, 116.10),
    "Adelaide": (-35.20, -34.65, 138.45, 138.80),
    "Gold Coast": (-28.20, -27.70, 153.20, 153.55),
    "Canberra": (-35.55, -35.10, 148.95, 149.30),
    "Newcastle": (-33.05, -32.75, 151.45, 151.80),
    "Wollongong": (-34.65, -34.35, 150.75, 151.00),
    "Hobart": (-43.00, -42.75, 147.15, 147.45),
    "Sunshine Coast": (-26.85, -26.40, 152.85, 153.20),
    "Cairns": (-17.10, -16.75, 145.65, 145.90),
    "Darwin": (-12.60, -12.25, 130.75, 131.05),
    "Townsville": (-19.40, -19.10, 146.65, 146.95),
    "Geelong": (-38.30, -38.05, 144.20, 144.50),
}


def generate_grid_points(metro_name: str, step_km: int = 5) -> list[tuple[float, float]]:
    """Generate lat/lng grid points covering a metro area.
    
    Uses 1 degree ≈ 111km for latitude, and 111km × cos(lat) for longitude.
    """
    if metro_name not in METRO_AREAS:
        return []
    
    lat_min, lat_max, lng_min, lng_max = METRO_AREAS[metro_name]
    
    # Convert km to degrees
    lat_step = step_km / 111.0
    # Use average latitude for longitude calculation
    avg_lat = (lat_min + lat_max) / 2
    lng_step = step_km / (111.0 * math.cos(math.radians(avg_lat)))
    
    points = []
    lat = lat_min
    while lat <= lat_max:
        lng = lng_min
        while lng <= lng_max:
            points.append((round(lat, 6), round(lng, 6)))
            lng += lng_step
        lat += lat_step
    
    return points


def grid_search_radius_meters(step_km: int) -> float:
    """Return search radius in meters (75% of step distance for overlap)."""
    return step_km * 1000 * 0.75