"""Toilets Near Me – Enrichment module (Python port of generate-eeat.js +
generate-stats.js composite scores).

Generates AI content for a single place using Google Gemini, then computes
a composite quality score from the composite-score functions in
``generate-stats.js``.

Content types (generic — not toilet-specific, per Phase 2.5):
  - description:     business description / overview
  - services:        services list
  - specialties:     specialties (what makes this place unique)
  - seo_keywords:    SEO keywords
  - seo_meta_desc:   SEO meta description

Quality score (ported from ``generate-stats.js``):
  Uses the four composite score functions adapted for per-place data.
  Returns a single 0–100 integer.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

import google.generativeai as genai

logger = logging.getLogger(__name__)

# ─── Constants (ported from generate-eeat.js) ────────────────────────────────────

MAX_RETRIES = 3
BASE_RETRY_DELAY = 2.0  # seconds (exponential backoff in generate-eeat.js)
REQUEST_INTERVAL_MS = 120  # 500 RPM target → 120ms between requests


# ─── Prompt builders (ported + generalized from generate-eeat.js) ─────────────────

# The original prompts are toilet-specific (states, regions, suburbs).
# For the directory factory, we need per-PLACE prompts that are generic
# across all niches (dog groomers, plumbers, restaurants, etc.).
# Each prompt generates: description, services, specialties, seo_keywords, seo_meta_desc.

PLACE_PROMPT = """You are writing SEO-optimized content for a local business directory.

BUSINESS: {name}
TYPE: {primary_type}
ADDRESS: {address}
PHONE: {phone}
WEBSITE: {website}
RATING: {rating}/5 ({user_rating_count} reviews)
24HOURS: {is_24_hours}
FEATURES: {features}
OPENING_HOURS: {opening_hours}

CONTENT TO WRITE (return ONLY JSON):

1. description — 2–3 sentences about what this business does, its vibe, and
   why someone would choose it. Mention the primary type and address area.

2. services — A JSON array of up to 5 services this business offers.
   Infer from the type, features, and any available data.
   e.g. ["Haircuts", "Beard trims", "Colouring", "Straightening", "Kids' cuts"]

3. specialties — A JSON array of up to 3 things this place is known for or
   does particularly well. e.g. ["Senior discounts", "Eco-friendly products", "Walk-ins welcome"]

4. seo_keywords — A JSON array of 8–12 SEO keywords specific to this business
   and location. Include long-tail keywords.
   e.g. ["dog grooming Sydney", "mobile dog wash near me", "pet spa services"]

5. seo_meta_desc — A 150–160 character meta description for this business page,
   including the name, primary type, and location.

RULES:
- Australian English spelling
- No invented phone numbers, websites, or addresses
- Keep services and specialties realistic for this business type
- SEO keywords should be location-relevant if address/locality is known

Return ONLY a JSON object:
{{"description": "...", "services": ["..."], "specialties": ["..."], "seo_keywords": ["..."], "seo_meta_desc": "..."}}"""


def build_place_prompt(cleaned_record: dict) -> str:
    """Build a Gemini prompt for a single place (ported + generalized from
    generate-eeat.js prompt builders).
    """
    features = ", ".join(cleaned_record.get("feature_keys", [])) or "none"
    opening_hours = cleaned_record.get("opening_hours_raw") or "not specified"

    rating_str = "N/A"
    if cleaned_record.get("rating") is not None:
        rating_str = f"{cleaned_record['rating']}"

    user_rating_count = cleaned_record.get("user_rating_count") or 0

    return PLACE_PROMPT.format(
        name=cleaned_record.get("name", "this business"),
        primary_type=cleaned_record.get("primary_type", "local business"),
        address=cleaned_record.get("address", "address not available"),
        phone=cleaned_record.get("phone") or cleaned_record.get("national_phone") or "not listed",
        website=cleaned_record.get("website") or "not listed",
        rating=rating_str,
        user_rating_count=user_rating_count,
        is_24_hours="yes" if cleaned_record.get("is_24_hours") else "no",
        features=features,
        opening_hours=opening_hours,
    )


async def call_gemini(prompt: str, model_name: str = "gemini-2.5-flash-lite") -> dict:
    """Call Gemini to generate content, with retry + exponential backoff.

    Ported from ``generate-eeat.js`` ``callGemini()``:
    - Up to MAX_RETRIES attempts
    - Exponential backoff (2s, 4s, 8s)
    - Strips markdown code fences
    - Parses JSON response
    - Validates required fields
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name=model_name,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.85,
            "max_output_tokens": 2048,
        },
    )

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await model.generate_content_async(prompt)
            raw_text = result.text.strip()
            # Strip markdown code fences (port from generate-eeat.js)
            json_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE)
            json_text = re.sub(r"\s*```$", "", json_text, flags=re.IGNORECASE)
            json_text = json_text.strip()

            parsed = json.loads(json_text)

            # Validate required fields
            required = ["description", "services", "specialties", "seo_keywords", "seo_meta_desc"]
            missing = [k for k in required if k not in parsed or not parsed[k]]
            if missing:
                raise ValueError(f"Response missing fields: {', '.join(missing)}")

            # Validate types
            if not isinstance(parsed["services"], list):
                raise ValueError("services must be a JSON array")
            if not isinstance(parsed["specialties"], list):
                raise ValueError("specialties must be a JSON array")
            if not isinstance(parsed["seo_keywords"], list):
                raise ValueError("seo_keywords must be a JSON array")

            return parsed

        except (json.JSONDecodeError, ValueError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Gemini attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = BASE_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Gemini attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)

    raise RuntimeError(f"Gemini failed after {MAX_RETRIES} attempts: {last_error}")


async def enrich_place(cleaned_record: dict) -> dict:
    """Enrich a cleaned place record with AI-generated content.

    Ported + generalized from ``generate-eeat.js``:
    - The original built prompts per entity type (state/region/suburb).
    - Here we build a per-place prompt using generic content types:
      description, services, specialties, seo_keywords, seo_meta_desc.
    - The original stored results in a Supabase ``content`` table.
    - Here we return the enriched dict for the caller to persist.

    Args:
        cleaned_record: Output of :func:`cleaning.clean_place()`.

    Returns:
        A dict with keys: ``description``, ``services``, ``specialties``,
        ``seo_keywords``, ``seo_meta_desc``, ``ai_model``, ``generated_at``.
    """
    prompt = build_place_prompt(cleaned_record)
    generated = await call_gemini(prompt)

    return {
        **generated,
        "ai_model": "gemini-2.5-flash-lite",
        "generated_at": _utcnow_iso(),
    }


def _utcnow_iso() -> str:
    """Return current UTC time in ISO format."""
    from datetime import datetime
    return datetime.utcnow().isoformat()


# ─── Quality Score (ported from generate-stats.js) ──────────────────────────────

def calc_accessibility_score(metrics: dict) -> int:
    """Compute accessibility score (0–100).

    Ported from ``generate-stats.js`` ``calcAccessibilityScore()``::
        score = (accessible_pct * 0.50)
              + min(changing_places_count, 5) / 5 * 20
              + (mlak_count > 0 ? 15 : 0)
              + (ambulant_count > 0 ? 15 : 0)
              → capped at 100, rounded

    For per-place data, we adapt:
    - accessible_pct is derived from feature_keys presence (0 or 100)
    - changing_places_count → 1 if "accessible" feature present
    - mlak_count → 1 if "mlak" or "key_required" feature present
    - ambulant_count → 1 if "accessible_entrance" feature present
    """
    features = set(metrics.get("feature_keys", []))

    # Per-place: accessible_pct is 100 if accessible feature present
    accessible_pct = 100 if "accessible" in features else 0

    # changing_places_count → use accessible feature as proxy
    changing_places_count = 1 if "accessible" in features else 0

    # mlak_count → key access features
    mlak_count = 1 if ("mlak" in features or "key_required" in features) else 0

    # ambulant_count → accessible entrance
    ambulant_count = 1 if "accessible_entrance" in features else 0

    score = 0
    score += accessible_pct * 0.50
    score += min(changing_places_count, 5) / 5 * 20
    score += 15 if mlak_count > 0 else 0
    score += 15 if ambulant_count > 0 else 0

    return min(round(score), 100)


def calc_family_score(metrics: dict) -> int:
    """Compute family-friendliness score (0–100).

    Ported from ``generate-stats.js`` ``calcFamilyScore()``::
        score = (baby_change_pct * 0.50)
              + (baby_care_room_count > 0 ? 25 : 0)
              + (parking_accessible_count > 0 ? 25 : 0)

    For per-place: baby_change if child-friendly, parking_accessible if
    accessible_parking feature present.
    """
    features = set(metrics.get("feature_keys", []))

    baby_change_pct = 100 if "child_friendly" in features else 0
    baby_care_room_count = 1 if "child_friendly" in features else 0
    parking_accessible_count = 1 if "accessible_parking" in features else 0

    score = 0
    score += baby_change_pct * 0.50
    score += 25 if baby_care_room_count > 0 else 0
    score += 25 if parking_accessible_count > 0 else 0

    return min(round(score), 100)


def calc_traveller_score(metrics: dict) -> int:
    """Compute traveller-friendliness score (0–100).

    Ported from ``generate-stats.js`` ``calcTravellerScore()``::
        score = min(dump_point_count, 10) / 10 * 40
              + (open_24h_pct * 0.40)
              + (shower_count > 0 ? 20 : 0)

    For per-place: 24h operation and on-site parking are the most relevant
    traveller features. Dump points and showers are niche-specific.
    """
    features = set(metrics.get("feature_keys", []))

    # open_24h_pct → 100 if open 24 hours
    open_24h_pct = 100 if metrics.get("is_24_hours") else 0

    # dump_point_count → check for dump_point feature (niche-specific)
    dump_point_count = 1 if "dump_point" in features else 0

    # shower_count → check for shower feature
    shower_count = 1 if "shower" in features else 0

    score = 0
    score += min(dump_point_count, 10) / 10 * 40
    score += open_24h_pct * 0.40
    score += 20 if shower_count > 0 else 0

    return min(round(score), 100)


def calc_provision_score(metrics: dict) -> int:
    """Compute provision/accessibility score (0–100).

    Ported from ``generate-stats.js`` ``calcProvisionScore()``::
        score = min(toilets_per_10k_equiv, 20) / 20 * 40
              + min(accessible_per_10k_equiv, 10) / 10 * 40
              + (open_24h_pct * 0.20)

    For per-place: we use the overall completeness score as a proxy for
    "toilets_per_10k" (data richness) and the accessible feature for the
    "accessible_per_10k" component. The 24h percentage maps to is_24_hours.
    """
    features = set(metrics.get("feature_keys", []))
    completeness = metrics.get("data_completeness_score", 0)

    # toilets_per_10k_equiv → completeness score (0-100 mapped to 0-20 scale)
    toilets_per_10k_equiv = completeness / 5.0  # maps 100 → 20

    # accessible_per_10k_equiv → 10 if accessible feature present
    accessible_per_10k_equiv = 10 if "accessible" in features else 0

    open_24h_pct = 100 if metrics.get("is_24_hours") else 0

    score = 0
    score += min(toilets_per_10k_equiv, 20) / 20 * 40
    score += min(accessible_per_10k_equiv, 10) / 10 * 40
    score += open_24h_pct * 0.20

    return min(round(score), 100)


def compute_quality_score(cleaned_record: dict, enriched_record: dict | None = None) -> int:
    """Compute a composite quality score (0–100) for a place.

    Ported from ``generate-stats.js`` composite score functions:
    ``calcAccessibilityScore``, ``calcFamilyScore``, ``calcTravellerScore``,
    ``calcProvisionScore``.

    The four component scores are averaged to produce a single quality score.
    In ``generate-stats.js``, these were computed at state/region/nation level
    using aggregate statistics. Here, adapted for per-place data:

    - **Accessibility** (45% weight): physical accessibility features
    - **Family** (25% weight): child/baby-friendly amenities
    - **Traveller** (15% weight): 24h, parking, dump points, showers
    - **Provision** (15% weight): data completeness, rating, features

    Args:
        cleaned_record: Output of :func:`cleaning.clean_place()`.
        enriched_record: Optional output of :func:`enrich_place()`.
            Used for any enrichment-derived signals (currently reserved
            for future use — rating and review counts also come from
            cleaned_record).

    Returns:
        Integer 0–100 quality score.
    """
    # Merge enriched data if available (enrichment may add features)
    combined = dict(cleaned_record)
    if enriched_record:
        # Enrichment could add feature_keys from content analysis in future
        pass

    accessibility = calc_accessibility_score(combined)
    family = calc_family_score(combined)
    traveller = calc_traveller_score(combined)
    provision = calc_provision_score(combined)

    # Weighted average (weights from generate-stats.js proportions)
    # accessibility=0.45, family=0.25, traveller=0.15, provision=0.15
    score = (
        accessibility * 0.45
        + family * 0.25
        + traveller * 0.15
        + provision * 0.15
    )

    return min(round(score), 100)
