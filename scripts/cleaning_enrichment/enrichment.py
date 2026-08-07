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

The library functions are pure. The ``__main__`` block adds a script entry
point via the ``@script_main`` contract for Phase 3 invocation.
"""

import os
import sys
import asyncio
import json
import logging
import os
import re
from typing import Any

import google.genai as genai

logger = logging.getLogger(__name__)


def _slugify(text: str | None) -> str:
    """Slugify wrapper — delegates to python-slugify if available, else uses cleaning.slugify."""
    if text is None or not text.strip():
        return ""
    try:
        from slugify import slugify as _py_slugify
        return _py_slugify(text, lowercase=True, separator="-")
    except ImportError:
        # Fallback: import from cleaning module
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from cleaning import slugify as _cleaning_slugify
        return _cleaning_slugify(text)

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

    client = genai.Client(api_key=api_key)
    config = {
        "response_mime_type": "application/json",
        "temperature": 0.85,
        "max_output_tokens": 2048,
    }

    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await client.aio.models.generate_content(
                model=model_name,
                contents=prompt,
                config=config,
            )
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


# ─── Script entry point ───────────────────────────────────────────────────────
# Invoked by runner/run.py via @script_main (Phase 3.7 / 2.7).
# Reads per-table cleaned data from data/<project_id>/cleaned/*.jsonl,
# enriches businesses with AI content, writes per-table enriched data
# to data/<project_id>/enriched/*.jsonl plus content.jsonl with AI-generated
# geography-level content.

# Content type sets — align with Data-Model-Spec.md §Content Model
GEO_CONTENT_TYPES = ["about", "local_context", "faq", "tips", "meta_title",
                      "meta_description", "seo_keywords"]
# Business-level content: local_context is geo-only (per Data-Model-Spec.md §Content Model)
BUSINESS_CONTENT_TYPES = ["about", "faq", "tips", "meta_title",
                          "meta_description", "seo_keywords"]


def _build_geo_prompt(entity_type: str, entity_name: str,
                      state_code: str, business_count: int,
                      feature_counts: dict, content_types: list[str]) -> str:
    """Build a Gemini prompt for geography-level EEAT content.

    Ported from ``generate-eeat.js`` ``buildStatePrompt`` /
    ``buildRegionPrompt`` / ``buildSuburbPrompt``, generalized to be
    directory-agnostic (not toilet-specific) and parameterized by
    ``content_types`` (5–7 types per the Data-Model-Spec.md).

    The original prompts were hard-coded for 6 content types per level.
    Here we generate the same set but dynamically, using ``{{placeholder}}``
    tokens resolved at Astro render time (not baked in at enrichment time).
    """
    feature_lines = "\n".join(
        f"  - {k}: {v}" for k, v in sorted(feature_counts.items())
    ) or "  (no feature data)"
    types_str = ", ".join(content_types)
    return f"""You are a local SEO content writer for a directory of local businesses.

Write content for the {entity_type.upper()} level: {entity_name} ({state_code}).

BUSINESS COUNT: {business_count}
FEATURE COUNTS (from cleaned data):
{feature_lines}

CONTENT TO WRITE (return ONLY JSON):
For each of these content types, write a concise, helpful, SEO-optimized piece:
{types_str}

RULES:
- Australian English spelling
- Use {{business_count}} as a placeholder token — do NOT resolve the number
- Keep content generic enough to work for any local business directory
- meta_title: 50-60 chars, include the entity name
- meta_description: 150-160 chars
- seo_keywords: comma-separated string of 8-12 keywords
- faq: JSON array of {{question, answer}} pairs (3-5 items)
- tips: JSON array of 3-5 short tips
- about: 2-3 paragraphs about the area's business landscape
- local_context: 1-2 paragraphs about the area's character, demographics, notable attractions

Return ONLY a JSON object with keys matching the content type names:
{json.dumps({t: "string or structured value" for t in content_types})}"""


def _build_geo_content(entity_type: str, entity_name: str,
                       state_code: str, slug: str,
                       business_count: int,
                       feature_counts: dict, content_types: list[str]) -> list[dict]:
    """Generate geography-level EEAT content and return as content rows.

    Uses Gemini to generate real AI content (not static templates),
    with {{placeholder}} tokens left unresolved for Astro render-time.
    Returns a list of content-row dicts ready for content.jsonl.
    """
    prompt = _build_geo_prompt(
        entity_type, entity_name, state_code, business_count,
        feature_counts, content_types
    )
    try:
        result = asyncio.run(call_gemini(prompt))
    except Exception as e:
        logger.warning(f"Geo content generation failed for {entity_type} '{entity_name}': {e}")
        result = {}

    now = _utcnow_iso()
    rows = []
    if entity_type == "state":
        entity_id = state_code  # states keyed by code (e.g. "QLD")
    else:
        entity_id = f"{slug}:{state_code}"  # region/suburb: slug:state_code
    for ct in content_types:
        body = result.get(ct)
        if not body:
            continue
        # Normalize: arrays stay arrays, strings stay strings
        if isinstance(body, list):
            body_str = json.dumps(body, ensure_ascii=False)
            wc = len(body_str.split())  # word count is the JSON string
        else:
            body_str = str(body)
            wc = len(body_str.split())
        rows.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "content_type": ct,
            "body": body_str,
            "word_count": wc,
            "ai_model": "gemini-2.5-flash-lite",
            "generated_at": now,
        })
    return rows


def _write_jsonl(path: str, records: list) -> None:
    """Write records as JSONL (one JSON object per line)."""
    with open(path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _read_jsonl(path: str) -> list[dict]:
    """Read JSONL file, return list of dicts."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _compute_geo_feature_counts(businesses: list[dict]) -> dict:
    """Compute feature_counts from a list of enriched business records."""
    counts = {}
    for biz in businesses:
        for fk in biz.get("feature_keys", []):
            counts[fk] = counts.get(fk, 0) + 1
    return counts


if __name__ == "__main__":
    # __file__ = directory-factory/scripts/cleaning_enrichment/enrichment.py
    _SCRIPTS_DIR = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
    _PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
    _SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")

    for p in (_PROJECT_ROOT, _SCRIPTS_DIR):
        if p not in sys.path:
            sys.path.insert(0, p)

    from runner.contract import script_main

    _DATA_DIR = os.path.join(_PROJECT_ROOT, "data")

    @script_main
    def main(project_id: int, params: dict) -> dict:
        """Enrich cleaned place records with AI content and quality scores.

        Reads per-table cleaned data from ``data/<project_id>/cleaned/*.jsonl``,
        enriches businesses, generates geography-level EEAT content, and
        writes to ``data/<project_id>/enriched/*.jsonl``.

        Args:
            project_id: The collection project ID.
            params: Optional parameters:
                - ``max_places``: Limit number of places to enrich (for testing).
                - ``skip_ai``: If True, skip Gemini calls, use fallback content.
                - ``model``: Gemini model name to use.
                - ``skip_geo_content``: If True, skip geography-level content generation.
        """
        from runner.contract import script_main

        cleaned_dir = os.path.join(_DATA_DIR, str(project_id), "cleaned")
        biz_path = os.path.join(cleaned_dir, "businesses.jsonl")
        if not os.path.isfile(biz_path):
            raise FileNotFoundError(
                f"Cleaned businesses not found at {biz_path}. "
                "Run cleaning.clean first."
            )

        max_places = params.get("max_places")
        skip_ai = params.get("skip_ai", False)
        model_name = params.get("model", "gemini-2.5-flash-lite")
        skip_geo_content = params.get("skip_geo_content", False)

        # Load cleaned data
        businesses = _read_jsonl(biz_path)
        states = _read_jsonl(os.path.join(cleaned_dir, "states.jsonl")) if os.path.isfile(os.path.join(cleaned_dir, "states.jsonl")) else []
        regions = _read_jsonl(os.path.join(cleaned_dir, "regions.jsonl")) if os.path.isfile(os.path.join(cleaned_dir, "regions.jsonl")) else []
        suburbs = _read_jsonl(os.path.join(cleaned_dir, "suburbs.jsonl")) if os.path.isfile(os.path.join(cleaned_dir, "suburbs.jsonl")) else []

        if max_places:
            businesses = businesses[:max_places]

        # ── Business-level enrichment ──────────────────────────────────────────
        enriched_businesses = []
        feature_rows = []
        hours_rows = []
        services_rows = []
        content_rows = []  # business-level content → content.jsonl

        for biz in businesses:
            # Compute quality score
            score = compute_quality_score(biz, None)
            biz["quality_score"] = score
            biz["enriched_at"] = _utcnow_iso()

            # AI content
            if skip_ai:
                biz["ai_generated"] = False
            else:
                try:
                    content = asyncio.run(enrich_place(biz))
                    biz["enrichment"] = content
                    biz["ai_generated"] = True
                except Exception as e:
                    biz["enrichment_error"] = str(e)
                    biz["ai_generated"] = False

                # Write business content rows to content.jsonl later
                if "enrichment" in biz:
                    now = biz["enrichment"].get("generated_at", _utcnow_iso())
                    entity_id = biz.get("place_id") or ""
                    content_types = BUSINESS_CONTENT_TYPES
                    for ct in content_types:
                        val = biz["enrichment"].get(ct)
                        if not val:
                            continue
                        if isinstance(val, list):
                            body_str = json.dumps(val, ensure_ascii=False)
                        else:
                            body_str = str(val)
                        content_rows.append({
                            "entity_type": "business",
                            "entity_id": entity_id,
                            "content_type": ct,
                            "body": body_str,
                            "word_count": len(body_str.split()) if isinstance(val, str) else len(val),
                            "ai_model": "gemini-2.5-flash-lite",
                            "generated_at": now,
                        })

            # Extract feature rows
            for fk in biz.get("feature_keys", []):
                feature_rows.append({
                    "place_id": biz.get("place_id"),
                    "feature_key": fk,
                })

            # Extract hours rows
            for hr in biz.get("hours_rows", []):
                hours_rows.append({
                    "place_id": biz.get("place_id"),
                    **{k: v for k, v in hr.items() if k != "facility_id"},
                })

            # Extract services rows (from enrichment if available)
            if biz.get("enrichment") and "services" in biz["enrichment"]:
                for svc in biz["enrichment"]["services"]:
                    services_rows.append({
                        "place_id": biz.get("place_id"),
                        "service_name": svc,
                    })

            enriched_businesses.append(biz)

        # ── Geography-level content generation ─────────────────────────────────
        # Build a lookup: businesses grouped by state / region / suburb slug
        if not skip_geo_content:
            # Group businesses for each geography level
            biz_by_state = {}
            biz_by_region = {}
            biz_by_suburb = {}
            for biz in enriched_businesses:
                sc = biz.get("state_code", "")
                biz_by_state.setdefault(sc, []).append(biz)

                rslug = biz.get("region_slug")
                if rslug:
                    biz_by_region.setdefault((rslug, sc), []).append(biz)
                sslug = biz.get("suburb_slug")
                if sslug:
                    biz_by_suburb.setdefault((sslug, sc), []).append(biz)

            # Generate state-level content
            for st in states:
                code = st.get("code", "")
                bcount = st.get("business_count") or len(biz_by_state.get(code, []))
                fcounts = _compute_geo_feature_counts(biz_by_state.get(code, []))
                # Map state_code (e.g. "QLD") to state_long for the prompt name
                name = st.get("name", code)
                content_rows.extend(_build_geo_content(
                    "state", name, code, st.get("slug", ""), bcount, fcounts,
                    GEO_CONTENT_TYPES,
                ))

            # Generate region-level content
            for reg in regions:
                sc = reg.get("state_code", "")
                rkey = (reg.get("slug", ""), sc)
                bcount = reg.get("business_count") or len(biz_by_region.get(rkey, []))
                fcounts = _compute_geo_feature_counts(biz_by_region.get(rkey, []))
                name = reg.get("name", reg.get("slug", ""))
                content_rows.extend(_build_geo_content(
                    "region", name, sc, reg.get("slug", ""), bcount, fcounts,
                    GEO_CONTENT_TYPES,
                ))

            # Generate suburb-level content
            for sub in suburbs:
                sc = sub.get("state_code", "")
                skey = (sub.get("slug", ""), sc)
                bcount = sub.get("business_count") or len(biz_by_suburb.get(skey, []))
                fcounts = _compute_geo_feature_counts(biz_by_suburb.get(skey, []))
                name = sub.get("name", sub.get("slug", ""))
                content_rows.extend(_build_geo_content(
                    "suburb", name, sc, sub.get("slug", ""), bcount, fcounts,
                    GEO_CONTENT_TYPES,
                ))

        # ── Write all enriched data ────────────────────────────────────────────
        enriched_dir = os.path.join(_DATA_DIR, str(project_id), "enriched")
        os.makedirs(enriched_dir, exist_ok=True)

        _write_jsonl(os.path.join(enriched_dir, "businesses.jsonl"), enriched_businesses)
        _write_jsonl(os.path.join(enriched_dir, "states.jsonl"), states)
        _write_jsonl(os.path.join(enriched_dir, "regions.jsonl"), regions)
        _write_jsonl(os.path.join(enriched_dir, "suburbs.jsonl"), suburbs)
        _write_jsonl(os.path.join(enriched_dir, "content.jsonl"), content_rows)
        _write_jsonl(os.path.join(enriched_dir, "business_features.jsonl"), feature_rows)
        _write_jsonl(os.path.join(enriched_dir, "business_hours.jsonl"), hours_rows)
        _write_jsonl(os.path.join(enriched_dir, "business_services.jsonl"), services_rows)

        ai_count = sum(1 for r in enriched_businesses if r.get("ai_generated"))
        error_count = sum(1 for r in enriched_businesses if "enrichment_error" in r)

        return {
            "summary": f"Enriched {len(enriched_businesses)} places for project {project_id} "
                       f"({ai_count} AI-generated, {error_count} AI errors). "
                       f"Generated {len(content_rows)} content rows across "
                       f"{len(states)} states, {len(regions)} regions, {len(suburbs)} suburbs.",
            "counts": {
                "businesses": len(enriched_businesses),
                "ai_generated": ai_count,
                "ai_errors": error_count,
                "states": len(states),
                "regions": len(regions),
                "suburbs": len(suburbs),
                "content_rows": len(content_rows),
                "feature_rows": len(feature_rows),
                "hours_rows": len(hours_rows),
                "services_rows": len(services_rows),
                "output_dir": f"data/{project_id}/enriched/",
            },
        }

    main()
