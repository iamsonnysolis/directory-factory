"""Toilets Near Me – Cleaning (Python port of enrich.js cleaning steps).

Ports the cleaning logic from ``OLD_TOILETSNEARME_DATA_PATH/enrich.js`` and
``OLD_TOILETSNEARME_DATA_PATH/parse-hours.js``, adapted to accept a **Google
Places API response** (``raw_json``) instead of an ABS CSV row.

Cleaning steps (mirroring enrich.js):
  1. Slug generation (``slugify``) → ``python-slugify``
  2. Text normalization (``cleanText``) → whitespace/newline collapsing
  3. Boolean parsing (``parseBool``) → type-list membership check
  4. Coordinate parsing + validation (``parseCoord`` / ``isValidCoord``)
  5. 24-hour detection (``is24Hours``)
  6. Opening-hours parsing (adapted from ``parse-hours.js``)
  7. Feature extraction (replaces CSV→feature-column mapping)

The library functions (``clean_place``, ``clean_text``, etc.) are pure —
no network, no database. The ``__main__`` block at the bottom adds a DB-backed
script entry point via the ``@script_main`` contract for Phase 3 invocation.
"""

import re
import sys
import unicodedata
from datetime import date, datetime
from typing import Any
from urllib.parse import urlparse

from slugify import slugify as _py_slugify


# ─── Helpers (ported from enrich.js) ───────────────────────────────────────────

def slugify(text: str | None) -> str:
    """Generate a URL-safe slug from text.

    Ported from ``enrich.js`` ``slugify()``:
    lowercase → NFD normalize → strip diacritics → keep [a-z0-9\\s-]
    → trim → collapse whitespace/underscores → collapse hyphens →
    strip leading/trailing hyphens.

    Delegates to ``python-slugify`` for the heavy lifting, which handles
    NFD normalization and diacritic stripping automatically.
    """
    if not text or not text.strip():
        return ""
    # python-slugify lowercases, strips accents, replaces spaces with hyphens,
    # and removes non-alphanumeric chars by default — matching enrich.js.
    return _py_slugify(text, lowercase=True, separator="-")


def clean_text(value: Any) -> str | None:
    """Normalize text: collapse newlines to spaces, collapse multiple whitespace.

    Ported from ``enrich.js`` ``cleanText()``::
        val.replace(/[\\r\\n]+/g, ' ').replace(/\\s{2,}/g, ' ').trim()
    Returns ``None`` for empty/whitespace-only input.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.replace("\r", " ").replace("\n", " ")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned if cleaned else None


def parse_bool(value: Any) -> bool:
    """Parse a boolean-like value.

    Ported from ``enrich.js`` ``parseBool()``: only the string ``"true"``
    (case-insensitive, trimmed) is truthy.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def parse_coord(value: Any) -> float | None:
    """Parse a coordinate value to float, returning ``None`` if invalid.

    Ported from ``enrich.js`` ``parseCoord()``.
    """
    if value is None:
        return None
    try:
        n = float(value)
        if _is_nan(n):
            return None
        return n
    except (TypeError, ValueError):
        return None


def _is_nan(n: float) -> bool:
    """Check if a float is NaN (without using ``math.isnan`` at import time)."""
    return n != n  # NaN is the only value where n != n


# Australian bounding box (from enrich.js)
AU_BOUNDS = {"min_lat": -44, "max_lat": -10, "min_lng": 112, "max_lng": 155}


def is_valid_coord(lat: float | None, lng: float | None) -> bool:
    """Check if coordinates fall within Australian bounds.

    Ported from ``enrich.js`` ``isValidCoord()``.
    """
    if lat is None or lng is None:
        return False
    return (
        lat >= AU_BOUNDS["min_lat"]
        and lat <= AU_BOUNDS["max_lat"]
        and lng >= AU_BOUNDS["min_lng"]
        and lng <= AU_BOUNDS["max_lng"]
    )


def is_24_hours(opening_hours: Any) -> bool:
    """Detect whether opening hours indicate 24-hour operation.

    Ported from ``enrich.js`` ``is24Hours()`` — checks for ``"24 hour"``
    substring. Extended to also check Google Places structured format.
    """
    if not opening_hours:
        return False
    # Raw string check (enrich.js style)
    if isinstance(opening_hours, str):
        return "24 hour" in opening_hours.lower()
    # Google Places structured format
    if isinstance(opening_hours, dict):
        # Check for 24-hour periods in Google's structured opening hours
        periods = opening_hours.get("periods", [])
        if periods:
            for p in periods:
                if p.get("openDay") is not None and p.get("closeDay") is not None:
                    # If open and close are on the same day and span the full day,
                    # it's 24 hours
                    if p.get("openHour", 24) == 0 and p.get("closeHour", 0) == 0:
                        # 00:00 open → 00:00 close next day = 24h
                        return True
        # Fallback: check raw string if present
        raw = opening_hours.get("raw", "")
        if raw and "24 hour" in raw.lower():
            return True
    return False


# ─── Opening Hours Parser (adapted from parse-hours.js) ────────────────────────

# Google Places API uses numeric day indices (0=Sunday, 1=Monday, ... 6=Saturday)
# The ABS format uses text abbreviations (Mon, Tue, ... Sun).
GOOGLE_DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
ABS_DAY_NUM = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
MONTH_NUM = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# Time string regex: "9am", "5:30pm", "12am", "12pm"
_TIME_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?([ap]m)$", re.IGNORECASE)
_TIME_PAIR_RE = re.compile(
    r"^(\d{1,2}(?::\d{2})?[ap]m)-(\d{1,2}(?::\d{2})?[ap]m)$", re.IGNORECASE
)


def _parse_time_to_mins(time_str: str) -> int | None:
    """Parse a time string like ``"9am"`` or ``"5:30pm"`` to minutes from midnight.

    Ported from ``parse-hours.js`` ``parseTimeToMins()``::
        12am → 0, 12pm → 720, 9am → 540, 5:30pm → 1050
    """
    m = _TIME_RE.match(time_str.strip())
    if not m:
        return None
    h = int(m.group(1))
    mins = int(m.group(2) or 0)
    ap = m.group(3).lower()
    if ap == "am":
        if h == 12:
            h = 0  # 12am = midnight
    else:
        if h != 12:
            h += 12  # 1pm→13, 11pm→23; 12pm stays 12
    return h * 60 + mins


def _parse_time_pair(time_str: str) -> dict | None:
    """Parse a ``open-close`` time pair to ``{open, close}`` minutes.

    Ported from ``parse-hours.js`` ``parseTimePair()``.
    Handles next-day overflow (e.g. ``"7am-2:30am"``) and midnight-as-close
    (``close=0`` → ``1440``).
    """
    m = _TIME_PAIR_RE.match(time_str.strip())
    if not m:
        return None
    open_mins = _parse_time_to_mins(m.group(1))
    close_mins = _parse_time_to_mins(m.group(2))
    if open_mins is None or close_mins is None:
        return None
    # 12am as a close time means end-of-day = 1440, not 0
    if close_mins == 0:
        close_mins = 1440
    # If close appears before open, it's a next-day close
    if close_mins < open_mins:
        close_mins += 1440
    return {"open": open_mins, "close": close_mins}


def _expand_days(day_spec: str | None) -> list[int] | None:
    """Expand a day specification to an array of day numbers (0–6).

    Ported from ``parse-hours.js`` ``expandDays()``::
        "Mon"        → [0]
        "Mon-Fri"    → [0,1,2,3,4]
        "Mon,Wed"    → [0,2]
        "Fri-Mon"    (wrap) → [4,5,6,0]
        None/""      → None  (all days)
    """
    if not day_spec or not day_spec.strip():
        return None

    result: set[int] = set()
    chunks = day_spec.split(",")
    for chunk in chunks:
        trimmed = chunk.strip()
        if "-" in trimmed:
            start_str, end_str = trimmed.split("-", 1)
            start = ABS_DAY_NUM.get(start_str.strip())
            end = ABS_DAY_NUM.get(end_str.strip())
            if start is None or end is None:
                continue
            if start <= end:
                for d in range(start, end + 1):
                    result.add(d)
            else:
                # Wrap-around: e.g. Fri-Mon
                for d in range(start, 7):
                    result.add(d)
                for d in range(0, end + 1):
                    result.add(d)
        else:
            d = ABS_DAY_NUM.get(trimmed.strip())
            if d is not None:
                result.add(d)

    return sorted(result) if result else None


def _parse_segment(segment: str, raw_source: str) -> list[dict]:
    """Parse a single opening-hours segment into structured rows.

    Ported from ``parse-hours.js`` ``parseSegment()``.
    A segment has the form: ``[MONTHS] [DAYS] TIME-TIME``.
    Returns one row per (day × season) combination.
    """
    tokens = segment.strip().split(r"\s+")
    # Re-split with regex (the JS splits on whitespace too, but JS uses \\s+ natively)
    tokens = re.split(r"\s+", segment.strip())

    # Collect month tokens
    season_tokens: list[str] = []
    i = 0
    month_re = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", re.IGNORECASE)
    while i < len(tokens):
        t = tokens[i]
        if month_re.match(t) and not re.search(r"[ap]m", t, re.IGNORECASE):
            season_tokens.append(t)
            i += 1
        else:
            break

    # Collect day tokens
    day_tokens: list[str] = []
    day_re = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)", re.IGNORECASE)
    while i < len(tokens):
        t = tokens[i]
        if day_re.match(t) and not re.search(r"[ap]m", t, re.IGNORECASE):
            day_tokens.append(t)
            i += 1
        else:
            break

    # Remaining is the time pair
    time_token = " ".join(tokens[i:])
    time_pair = _parse_time_pair(time_token)
    if not time_pair:
        return [{
            "day_of_week": None,
            "month_start": None,
            "month_end": None,
            "open_mins": None,
            "close_mins": None,
            "is_24_hours": False,
            "is_daylight": False,
            "is_unknown": False,
            "parse_status": "failed",
            "parse_notes": f'Could not parse time: "{time_token}" in segment "{segment}"',
            "raw_source": raw_source,
        }]

    # Parse days
    day_spec = ",".join(day_tokens) if day_tokens else None
    days = _expand_days(day_spec)  # None = all days

    # Parse seasons
    seasons: list[dict | None] = []
    if not season_tokens:
        seasons.append(None)  # all year
    else:
        combined = " ".join(season_tokens)
        range_match = re.match(
            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$",
            combined, re.IGNORECASE
        )
        if range_match:
            seasons.append({
                "start": MONTH_NUM.get(range_match.group(1).title()),
                "end": MONTH_NUM.get(range_match.group(2).title()),
            })
        else:
            # Individual months
            all_parts = ",".join(season_tokens).split(",")
            for part in all_parts:
                p = part.strip().title()
                if p in MONTH_NUM:
                    seasons.append({"start": MONTH_NUM[p], "end": MONTH_NUM[p]})
        if not seasons:
            seasons.append(None)

    # Build output rows: one per (day × season)
    rows = []
    day_list = days if days is not None else [None]
    for season in seasons:
        for day in day_list:
            rows.append({
                "day_of_week": day,
                "month_start": season["start"] if season else None,
                "month_end": season["end"] if season else None,
                "open_mins": time_pair["open"],
                "close_mins": time_pair["close"],
                "is_24_hours": False,
                "is_daylight": False,
                "is_unknown": False,
                "parse_status": "parsed",
                "raw_source": raw_source,
            })
    return rows


def parse_opening_hours(raw: str | None, place_id: int | None = None) -> list[dict]:
    """Parse a full opening-hours string into structured rows.

    Ported from ``parse-hours.js`` ``parseOpeningHours()``.
    Handles all patterns from the ABS dataset plus Google Places string format.
    Each row is ready for insertion into an ``hours`` table.
    """
    if not raw or not raw.strip():
        return []

    str_val = raw.strip()
    source = str_val

    # Special status strings
    if re.search(r"24 hour", str_val, re.IGNORECASE):
        return [{
            "facility_id": place_id,
            "is_24_hours": True,
            "is_daylight": False,
            "is_unknown": False,
            "parse_status": "parsed",
            "raw_source": source,
            "day_of_week": None,
            "month_start": None,
            "month_end": None,
            "open_mins": None,
            "close_mins": None,
        }]
    if re.search(r"daylight", str_val, re.IGNORECASE):
        return [{
            "facility_id": place_id,
            "is_24_hours": False,
            "is_daylight": True,
            "is_unknown": False,
            "parse_status": "parsed",
            "raw_source": source,
            "day_of_week": None,
            "month_start": None,
            "month_end": None,
            "open_mins": None,
            "close_mins": None,
        }]
    if re.search(r"variable|venue hours|currently closed|unknown|closed", str_val, re.IGNORECASE):
        return [{
            "facility_id": place_id,
            "is_24_hours": False,
            "is_daylight": False,
            "is_unknown": True,
            "parse_status": "parsed",
            "raw_source": source,
            "day_of_week": None,
            "month_start": None,
            "month_end": None,
            "open_mins": None,
            "close_mins": None,
        }]

    # Strip "OPEN:" prefix
    body = re.sub(r"^OPEN:\s*", "", str_val, flags=re.IGNORECASE).strip()

    # Split into segments on ", " followed by a capital letter or digit
    raw_segments = re.split(r",\s+(?=[A-Z0-9])", body)

    all_rows = []
    for seg in raw_segments:
        if not seg.strip():
            continue
        seg_rows = _parse_segment(seg, source)
        for row in seg_rows:
            row["facility_id"] = place_id
            all_rows.append(row)

    if not all_rows:
        return [{
            "facility_id": place_id,
            "is_24_hours": False,
            "is_daylight": False,
            "is_unknown": True,
            "parse_status": "failed",
            "raw_source": source,
            "day_of_week": None,
            "month_start": None,
            "month_end": None,
            "open_mins": None,
            "close_mins": None,
            "parse_notes": "No segments parsed",
        }]

    return all_rows


def parse_google_opening_hours(regular_opening_hours: dict) -> list[dict]:
    """Parse Google Places structured opening hours into the same row format
    as :func:`parse_opening_hours`.

    Google's API returns periods like:
    ``{"openDay": 1, "openHour": 9, "openMinute": 0,
      "closeDay": 1, "closeHour": 17, "closeMinute": 0}``
    where day 0 = Sunday, 1 = Monday, etc.
    """
    rows = []
    periods = regular_opening_hours.get("periods", [])
    for p in periods:
        open_day = p.get("openDay")
        close_day = p.get("closeDay")
        open_hour = p.get("openHour", 0)
        open_minute = p.get("openMinute", 0)
        close_hour = p.get("closeHour", 0)
        close_minute = p.get("closeMinute", 0)

        open_mins = open_hour * 60 + open_minute
        close_mins = close_hour * 60 + close_minute

        # If open and close are on different days, close is next day
        if close_day is not None and open_day is not None and close_day != open_day:
            # Determine days in range
            days = []
            d = open_day
            while True:
                days.append(d)
                if d == close_day:
                    break
                d = (d + 1) % 7
            for d in days:
                rows.append({
                    "facility_id": None,
                    "day_of_week": d,
                    "month_start": None,
                    "month_end": None,
                    "open_mins": open_mins,
                    "close_mins": close_mins,
                    "is_24_hours": False,
                    "is_daylight": False,
                    "is_unknown": False,
                    "parse_status": "parsed",
                    "raw_source": None,
                })
        elif open_day is not None:
            rows.append({
                "facility_id": None,
                "day_of_week": open_day,
                "month_start": None,
                "month_end": None,
                "open_mins": open_mins,
                "close_mins": close_mins,
                "is_24_hours": False,
                "is_daylight": False,
                "is_unknown": False,
                "parse_status": "parsed",
                "raw_source": None,
            })
    return rows


# ─── Feature extraction ──────────────────────────────────────────────────────

# Google Places types → directory feature keys.
# In the original enrich.js this was a fixed CSV-to-feature map for toilets.
# Here we map Google Places types to generic feature keys that work across
# all niches. The per-niche taxonomy (Phase 2.3) will refine this.
GOOGLE_TYPE_MAP = {
    # Accessibility
    "wheelchair_accessible": "accessible",
    "accessible": "accessible",
    # Business type features (generic, applicable to all niches)
    "restaurant": "has_dining",
    "cafe": "has_dining",
    "bar": "has_dining",
    "bakery": "has_food",
    "meal_delivery": "has_delivery",
    "meal_takeaway": "has_takeaway",
    # Parking
    "parking": "parking",
    "parking_24_hours": "parking_24h",
    # Payment
    "credit_card_accepted": "credit_card",
    "cash": "cash_only",
    "payment_ewallet": "digital_payments",
    # Online services
    "online_consultation": "online_booking",
    "appointment_required": "appointment_only",
    # Amenities
    "child_friendly": "child_friendly",
    "dog_friendly": "dog_friendly",
    "pet_friendly": "pet_friendly",
    "outdoor_seating": "outdoor_seating",
    "wheelchair": "accessible",
}


def _extract_features_from_types(types: list[str]) -> list[str]:
    """Map Google Places ``types`` to feature keys.

    Replaces the CSV_TO_FEATURE column mapping from ``enrich.js``.
    """
    features = []
    seen = set()
    for t in types:
        key = GOOGLE_TYPE_MAP.get(t)
        if key and key not in seen:
            features.append(key)
            seen.add(key)
    return features


def _extract_features_from_accessibility(accessibility_options: dict | None) -> list[str]:
    """Extract feature keys from Google Places ``accessibilityOptions``.

    Google Places API (New) returns accessibility options as a dict:
    ``{"wheelchairAccessible": true, "wheelchairAccessibleEntrance": true}``
    """
    if not accessibility_options:
        return []
    features = []
    if accessibility_options.get("wheelchairAccessible"):
        features.append("accessible")
    if accessibility_options.get("wheelchairAccessibleEntrance"):
        features.append("accessible_entrance")
    if accessibility_options.get("wheelchairAccessibleParking"):
        features.append("accessible_parking")
    return features


def _extract_features_from_pricing(price_level: str | None) -> list[str]:
    """Extract feature keys from Google Places ``priceLevel``."""
    if not price_level:
        return []
    mapping = {
        "PRICE_LEVEL_FREE": "free",
        "PRICE_LEVEL_INEXPENSIVE": "inexpensive",
        "PRICE_LEVEL_MODERATE": "moderate",
        "PRICE_LEVEL_EXPENSIVE": "expensive",
        "PRICE_LEVEL_VERY_EXPENSIVE": "very_expensive",
    }
    key = mapping.get(price_level)
    return [key] if key else []


def derive_features(raw_json: dict, taxonomy: dict | None = None) -> list[dict]:
    """Derive feature records for a place.

    This is the directory-factory equivalent of ``enrich.js`` ``buildFeatures()``,
    which mapped CSV boolean columns to feature keys. In the new system,
    features come from the Google Places API response ``types`` array and
    ``accessibilityOptions``, filtered/adjusted by the per-niche ``taxonomy``.

    Args:
        raw_json: Google Places API response dict.
        taxonomy: Optional per-niche feature taxonomy (Phase 2.3).
            If provided, only features listed in the taxonomy are returned,
            and any taxonomy feature not present in the place is omitted.

    Returns:
        List of feature dicts: ``{"feature_key": str, "source": str}``
    """
    features: list[dict] = []
    seen: set[str] = set()

    def _add(key: str, source: str) -> None:
        if key and key not in seen:
            features.append({"feature_key": key, "source": source})
            seen.add(key)

    # From types array
    types = raw_json.get("types", [])
    if isinstance(types, list):
        for f in _extract_features_from_types(types):
            _add(f, "types")

    # From accessibility options
    for f in _extract_features_from_accessibility(raw_json.get("accessibilityOptions")):
        _add(f, "accessibility")

    # From pricing
    for f in _extract_features_from_pricing(raw_json.get("priceLevel")):
        _add(f, "pricing")

    # From business status — operational status as a feature
    status = raw_json.get("businessStatus")
    if status:
        _add(f"business_status_{status.lower()}", "business_status")

    # 24-hour flag
    if is_24_hours(raw_json.get("regularOpeningHours")):
        _add("open_24_hours", "opening_hours")

    # If taxonomy is provided, filter to only taxonomy features
    if taxonomy:
        allowed = set(taxonomy.get("features", taxonomy.get("feature_keys", [])))
        if allowed:
            features = [f for f in features if f["feature_key"] in allowed]

    return features


# ─── Notes extraction ─────────────────────────────────────────────────────────

def derive_notes(raw_json: dict) -> list[dict]:
    """Extract note records from a place (equivalent to ``enrich.js`` ``buildNotes()``).

    In the original, notes were CSV columns (ToiletNote, AccessNote, etc.).
    Here we extract from Google Places response fields that contain textual
    supplementary information.
    """
    notes: list[dict] = []

    editorial_summaries = raw_json.get("editorialSummaries")
    if editorial_summaries:
        for i, summary in enumerate(editorial_summaries):
            if isinstance(summary, dict):
                text = summary.get("text") or summary.get("overview")
            else:
                text = str(summary)
            if text and text.strip():
                notes.append({"note_type": "editorial", "note": text})

    # Address components as notes (useful for structured address info)
    address_components = raw_json.get("addressComponents")
    if address_components:
        for comp in address_components:
            types = comp.get("types", [])
            long_name = comp.get("longText", "") or comp.get("long_name", "")
            if "street_address" in types or "route" in types and long_name:
                notes.append({"note_type": "address_detail", "note": long_name})

    return notes


# ─── Main cleaning function ──────────────────────────────────────────────────

def clean_place(raw_json: dict) -> dict:
    """Clean a raw Google Places API response into a normalized record.

    Ported from the cleaning logic in ``enrich.js``:
    ``slugify()``, ``cleanText()``, ``parseCoord()``, ``isValidCoord()``,
    ``is24Hours()``, plus the structured field extraction from
    ``buildToilets()`` and ``buildFeatures()``.

    Args:
        raw_json: A Google Places API (New) response dict, as stored in
            the ``places.raw_json`` column.

    Returns:
        A cleaned dict with normalized fields:

        ``name``, ``slug``, ``address``, ``locality``, ``suburb_name``,
        ``region_name``, ``state_code``/``state_long``, ``postal_code``, ``country``,
        ``lat``, ``lng``, ``phone``,\n        ``national_phone``, ``website``, ``place_id``, ``primary_type``,\n        ``business_status``, ``rating``, ``user_rating_count``, ``is_24_hours``,\n        ``opening_hours_raw``, ``opening_hours_note``, ``feature_keys``,\n        ``notes``, ``hours_rows``, ``data_completeness_score``
    """
    raw = raw_json if isinstance(raw_json, dict) else {}
    _raw = raw.get("_raw", raw)  # unwrap if already validated

    # ── Basic identity ──────────────────────────────────────────
    place_id = _raw.get("id") or _raw.get("place_id") or _raw.get("fs_id")
    display_name = _raw.get("displayName")
    if isinstance(display_name, dict):
        name = clean_text(display_name.get("text"))
    else:
        name = clean_text(display_name)
    if not name:
        name = "Public Toilet"  # fallback from enrich.js buildToilets: cleanText(row.Name) ?? 'Public Toilet'

    # ── Slug generation (enrich.js slugify + toilet slug dedupe concept)
    name_slug = slugify(name) or slugify("public-toilet")

    # ── Address normalization ─────────────────────────────────────
    address = clean_text(_raw.get("formattedAddress") or _raw.get("formatted_address"))

    # Parse address components for structured fields
    # Per Data-Model-Spec.md: resolve suburb (locality), region
    # (administrative_area_level_2), and state (administrative_area_level_1)
    # from addressComponents during cleaning — no spatial/shapefile logic.
    locality = None
    region_name = None
    state_code = None
    state_long = None
    postal_code = None
    country = None
    address_components = _raw.get("addressComponents") or _raw.get("address_components") or []
    if isinstance(address_components, list):
        for comp in address_components:
            comp_types = comp.get("types", [])
            if isinstance(comp_types, list) and comp_types:
                first_type = comp_types[0]
                long_name = comp.get("longText") or comp.get("long_name") or ""
                short_name = comp.get("shortText") or comp.get("short_name") or ""
                if first_type == "locality":
                    locality = clean_text(long_name)
                elif first_type == "administrative_area_level_2":
                    region_name = clean_text(long_name)
                elif first_type == "administrative_area_level_1":
                    # short_name is the state code (e.g. "QLD"), long_name is full name
                    state_code = clean_text(short_name) or clean_text(long_name)
                    state_long = clean_text(long_name)
                elif first_type == "postal_code":
                    postal_code = clean_text(long_name)
                elif first_type == "country":
                    country = clean_text(long_name)

    # ── Coordinates ─────────────────────────────────────────────
    location = _raw.get("location") or {}
    lat = parse_coord(location.get("latitude") or location.get("lat"))
    lng = parse_coord(location.get("longitude") or location.get("lng"))

    # ── Phone normalization (requires phonenumbers lib) ──────────
    national_phone = None
    international_phone = None
    raw_national = _raw.get("nationalPhoneNumber") or _raw.get("national_phone_number")
    raw_international = _raw.get("internationalPhoneNumber") or _raw.get("international_phone_number")
    if raw_national:
        national_phone = clean_text(raw_national)
    if raw_international:
        international_phone = clean_text(raw_international)

    # ── Website (urllib.parse for validation) ────────────────────
    website = _raw.get("websiteUri") or _raw.get("websiteUri") or _raw.get("website")
    website = clean_text(website)
    if website:
        parsed = urlparse(website)
        if not parsed.scheme:
            website = f"https://{website}"

    # ── Classification ───────────────────────────────────────────
    primary_type = clean_text(_raw.get("primaryType") or _raw.get("primary_type"))
    types = _raw.get("types", [])
    if not isinstance(types, list):
        types = []
    business_status = clean_text(_raw.get("businessStatus") or _raw.get("business_status"))

    # ── Ratings ──────────────────────────────────────────────────
    rating = _raw.get("rating")
    if rating is not None:
        try:
            rating = float(rating)
        except (TypeError, ValueError):
            rating = None
    user_rating_count = _raw.get("userRatingCount")
    if user_rating_count is not None:
        try:
            user_rating_count = int(user_rating_count)
        except (TypeError, ValueError):
            user_rating_count = None

    # ── Opening hours ────────────────────────────────────────────
    opening_hours = _raw.get("regularOpeningHours") or _raw.get("regular_opening_hours")
    opening_hours_raw = None
    opening_hours_note = None
    is_24h = False
    hours_rows: list[dict] = []

    if isinstance(opening_hours, dict):
        is_24h = is_24_hours(opening_hours)
        # Build a raw string representation for display
        periods = opening_hours.get("periods", [])
        if periods:
            parts = []
            for p in periods[:7]:
                open_day = p.get("openDay")
                if open_day is not None:
                    day_name = GOOGLE_DAY_NAMES[open_day % 7] if open_day < 7 else "?"
                    oh_parts = []
                    if p.get("openHour") is not None:
                        oh_parts.append(f"{p['openHour']:02d}:{p.get('openMinute', 0):02d}")
                    if p.get("closeHour") is not None:
                        oh_parts.append(f"{p['closeHour']:02d}:{p.get('closeMinute', 0):02d}")
                    time_str = "-".join(oh_parts) if oh_parts else "open"
                    parts.append(f"{day_name}: {time_str}")
            opening_hours_raw = "; ".join(parts)
        # Parse structured hours into rows
        hours_rows = parse_google_opening_hours(opening_hours)
    elif isinstance(opening_hours, str):
        opening_hours_raw = clean_text(opening_hours)
        is_24h = is_24_hours(opening_hours)
        # Try to parse string-format hours (ABS-style "OPEN:" prefix)
        hours_rows = parse_opening_hours(opening_hours, place_id)

    # Also check for 24-hour indication in opening hours text
    if not is_24h and opening_hours_raw:
        is_24h = bool(re.search(r"24 ?hour", opening_hours_raw, re.IGNORECASE))

    # ── Feature extraction (enrich.js buildFeatures equivalent) ──
    feature_keys = [f["feature_key"] for f in derive_features(_raw)]

    # ── Notes (enrich.js buildNotes equivalent) ──────────────────
    notes = derive_notes(_raw)
    if notes:
        opening_hours_note = "; ".join(n["note"][:200] for n in notes[:3])

    # ── Completeness score (ported from google_places.py) ────────
    key_fields = [
        "displayName", "formattedAddress", "location", "nationalPhoneNumber",
        "websiteUri", "rating", "userRatingCount", "regularOpeningHours",
    ]
    present = sum(1 for f in key_fields if _raw.get(f) is not None)
    completeness = min(int(present / len(key_fields) * 100), 100)

    return {
        "place_id": place_id,
        "name": name,
        "slug": f"{name_slug}-{place_id[-8:]}" if place_id else name_slug,
        "address": address,
        "locality": locality,
        "suburb_name": locality,      # Per Data-Model-Spec.md: locality maps to suburb for D1 upload
        "region_name": region_name,   # Per Data-Model-Spec.md: administrative_area_level_2
        "state_code": state_code,
        "state_long": state_long,     # Full state name (e.g. "Queensland") for display
        "postal_code": postal_code,
        "country": country,
        "lat": lat,
        "lng": lng,
        "phone": national_phone,
        "national_phone": national_phone,
        "international_phone": international_phone,
        "website": website,
        "primary_type": primary_type,
        "types": types,
        "business_status": business_status,
        "rating": rating,
        "user_rating_count": user_rating_count,
        "is_24_hours": is_24h,
        "opening_hours_raw": opening_hours_raw,
        "opening_hours_note": opening_hours_note,
        "feature_keys": feature_keys,
        "notes": notes,
        "hours_rows": hours_rows,
        "data_completeness_score": completeness,
        "cleaned_at": datetime.utcnow().isoformat(),
    }


# ─── Script entry point (Phase 3.6 / 2.7) ─────────────────────────────────────
# This block allows the file to be invoked directly by runner/run.py via the
# @script_main contract. It reads raw JSON from the collection engine's DB,
# cleans each place, and writes cleaned records to a JSONL file.

if __name__ == "__main__":
    import json
    import os
    import sqlite3

    # Set up paths so we can import runner.contract and the collection DB models
    # __file__ = directory-factory/scripts/cleaning_enrichment/cleaning.py
    #   dirname(1) = scripts/cleaning_enrichment
    #   dirname(2) = scripts  ← _SCRIPTS_DIR
    #   dirname(3) = directory-factory  ← _PROJECT_ROOT
    _SCRIPTS_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    _PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
    _SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")
    _RUNNER_DIR = os.path.join(_PROJECT_ROOT, "runner")
    _COLLECTION_DIR = os.path.join(_SCRIPTS_DIR, "collection")

    # _PROJECT_ROOT on path → makes `runner` importable as a package
    # _SCRIPTS_DIR on path → makes flat imports (from config import) work
    # _COLLECTION_DIR on path → for direct collection engine imports
    for p in (_PROJECT_ROOT, _SCRIPTS_DIR, _COLLECTION_DIR):
        if p not in sys.path:
            sys.path.insert(0, p)

    from runner.contract import script_main

    # Resolve collector DB path — respects DATABASE_URL env var (same pattern
    # as scripts/collection/database.py) so cleaning.py and collection engine
    # always read from the same DB file, regardless of which script invoked.
    db_url = os.getenv("DATABASE_URL", "sqlite:///./data/collector.db")
    if db_url.startswith("sqlite:///"):
        _COLLECTOR_DB = db_url.replace("sqlite:///", "")
        if not os.path.isabs(_COLLECTOR_DB):
            _COLLECTOR_DB = os.path.join(os.getcwd(), _COLLECTOR_DB)
    else:
        _COLLECTOR_DB = os.path.join(_SCRIPTS_DIR, "collection", "data", "collector.db")
    _DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

    @script_main
    def main(project_id: int, params: dict) -> dict:
        """Clean all raw places for a project.

        Reads raw_json from the collection DB's ``places`` table, runs
        ``clean_place()`` on each, and writes cleaned records to
        ``data/cleaned_<project_id>.jsonl``.

        Args:
            project_id: The collection project ID.
            params: Optional parameters:
                - ``taxonomy_path``: Path to a per-niche feature taxonomy JSON.
                - ``dry_run``: If True, don't write output file.
        """
        import datetime as _dt

        if not os.path.isfile(_COLLECTOR_DB):
            raise FileNotFoundError(
                f"Collector DB not found at {_COLLECTOR_DB}. "
                "Run collection.collect first."
            )

        dry_run = params.get("dry_run", False)
        taxonomy = None
        taxonomy_path = params.get("taxonomy_path")
        if taxonomy_path and os.path.isfile(taxonomy_path):
            with open(taxonomy_path) as f:
                taxonomy = json.load(f)

        conn = sqlite3.connect(_COLLECTOR_DB)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, place_id, raw_json FROM places WHERE project_id = ? ORDER BY id",
            (project_id,)
        )
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                "summary": f"No raw places found for project {project_id}",
                "counts": {"places": 0, "cleaned": 0},
            }

        cleaned_records = []
        skipped = 0
        for row in rows:
            try:
                raw_json = json.loads(row["raw_json"])
                cleaned = clean_place(raw_json)
                # Inject taxonomy-filtered features if provided
                if taxonomy:
                    cleaned["feature_keys"] = [
                        f["feature_key"] for f in derive_features(raw_json, taxonomy)
                    ]
                cleaned["source_place_db_id"] = row["id"]
                cleaned_records.append(cleaned)
            except Exception:
                skipped += 1

        if not dry_run:
            output_dir = os.path.join(_PROJECT_ROOT, "data")
            os.makedirs(output_dir, exist_ok=True)
            output_path = os.path.join(output_dir, f"cleaned_{project_id}.jsonl")
            with open(output_path, "w") as f:
                for record in cleaned_records:
                    f.write(json.dumps(record) + "\n")

        return {
            "summary": f"Cleaned {len(cleaned_records)} places for project {project_id} "
                       f"({skipped} skipped)",
            "counts": {
                "places": len(rows),
                "cleaned": len(cleaned_records),
                "skipped": skipped,
                "output_file": f"data/cleaned_{project_id}.jsonl" if not dry_run else None,
            },
        }

    main()

