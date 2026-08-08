"""Configuration loader with Google Places API field tiers."""

import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    GOOGLE_PLACES_API_KEY: str = ""
    WORKER_CONCURRENCY: int = 3
    REQUEST_TIMEOUT_SECONDS: int = 10
    RETRY_COUNT: int = 3
    RETRY_DELAY_SECONDS: int = 2
    DATABASE_URL: str = "sqlite:///./data/collector.db"
    HOST: str = "localhost"
    PORT: int = 8000
    PLACES_FIELD_TIER: str = "enterprise"
    SEARCH_STEP_KM: int = 10
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


FIELD_TIERS = {
    # Text Search Essentials (IDs Only)
    "essentials": [
        "id",
    ],

    # Text Search Pro
    "pro": [
        "accessibilityOptions",
        "addressComponents",
        "addressDescriptor",
        "adrFormatAddress",
        "businessStatus",
        "containingPlaces",
        "displayName",
        "formattedAddress",
        "googleMapsLinks",
        "googleMapsUri",
        "iconBackgroundColor",
        "iconMaskBaseUri",
        "location",
        "photos",
        "plusCode",
        "postalAddress",
        "primaryType",
        "primaryTypeDisplayName",
        "pureServiceAreaBusiness",
        "shortFormattedAddress",
        "subDestinations",
        "timeZone",
        "types",
        "utcOffsetMinutes",
        "viewport",
    ],

    # Text Search Enterprise ONLY
    # (No Enterprise + Atmosphere fields)
    "enterprise": [
        "currentOpeningHours",
        "currentSecondaryOpeningHours",
        "internationalPhoneNumber",
        "nationalPhoneNumber",
        "priceLevel",
        "priceRange",
        "rating",
        "regularOpeningHours",
        "regularSecondaryOpeningHours",
        "transitStation",
        "userRatingCount",
        "websiteUri",
    ],
    "pay_per_image": [
        "photos",  # Billed per photo asset downloaded, not per API text response
    ]
}


def get_active_field_tier() -> str:
    """Get the active field tier from environment."""
    tier = os.getenv("PLACES_FIELD_TIER", "enterprise")
    if tier not in FIELD_TIERS:
        tier = "enterprise"
    return tier


def get_active_fields() -> list[str]:
    """Get the list of fields for the active tier (cumulative)."""
    tier = get_active_field_tier()
    fields = []
    if tier == "pro":
        fields = FIELD_TIERS["essentials"] + FIELD_TIERS["pro"]
    elif tier == "enterprise":
        fields = FIELD_TIERS["essentials"] + FIELD_TIERS["pro"] + FIELD_TIERS["enterprise"]
    else:  # essentials
        fields = FIELD_TIERS["essentials"]
    return fields


# Australian cities/regions for search expansion
AUSTRALIAN_LOCATIONS = [
    # Major cities
    "Sydney NSW",
    "Melbourne VIC",
    "Brisbane QLD",
    "Perth WA",
    "Adelaide SA",
    "Canberra ACT",
    "Hobart TAS",
    "Darwin NT",
    "Gold Coast QLD",
    "Newcastle NSW",
    "Wollongong NSW",
    "Sunshine Coast QLD",
    "Cairns QLD",
    "Townsville QLD",
    "Geelong VIC",
    "Ballarat VIC",
    "Bendigo VIC",
    "Toowoomba QLD",
    "Launceston TAS",
    "Mackay QLD",
    "Rockhampton QLD",
    "Bundaberg QLD",
    "Hervey Bay QLD",
    "Wagga Wagga NSW",
    "Albury NSW",
    "Mildura VIC",
    "Shepparton VIC",
    "Gladstone QLD",
    "Tamworth NSW",
    "Orange NSW",
    "Dubbo NSW",
    "Geraldton WA",
    "Kalgoorlie WA",
    "Mandurah WA",
    "Bunbury WA",
    "Albany WA",
    "Mount Gambier SA",
    "Whyalla SA",
    "Murray Bridge SA",
    "Port Augusta SA",
    "Alice Springs NT",
    "Palmerston NT",
]

# Instantiate settings
settings = Settings()
