"""Directory data helpers and consolidated card builder.

This module contains the single build_directory_card() function that
both the Overview page route and the /api/directories JSON API route
call, eliminating the duplicated card-building logic that existed in
the original monolithic app.py.
"""

import json
from ..config import PROJECT_ROOT, STAGES_CONFIG


def _directory_counts(project_id: int) -> dict:
    """Get place/feature counts from cleaned/enriched data files."""
    counts = {"places_collected": 0, "places_cleaned": 0, "features_enriched": 0}
    base = PROJECT_ROOT / "data" / str(project_id)

    # Count collected places from collector.db
    from ..db import _connect_collector
    conn = _connect_collector()
    try:
        counts["places_collected"] = conn.execute(
            "SELECT COUNT(*) FROM places WHERE project_id = ?", (project_id,)
        ).fetchone()[0]
    except Exception:
        pass
    conn.close()

    # Count cleaned/enriched from flat files
    cleaned_file = base / "cleaned" / "businesses.jsonl"
    if cleaned_file.exists():
        counts["places_cleaned"] = sum(1 for _ in open(cleaned_file))
    enriched_file = base / "enriched" / "business_features.jsonl"
    if enriched_file.exists():
        counts["features_enriched"] = sum(1 for _ in open(enriched_file))

    return counts


def _count_enriched_records(project_id: int) -> int:
    """Count enriched business records from the enriched directory."""
    base = PROJECT_ROOT / "data" / str(project_id)
    businesses_file = base / "enriched" / "businesses.jsonl"
    if businesses_file.exists():
        try:
            return sum(1 for line in open(businesses_file) if line.strip())
        except Exception:
            pass
    return 0


def _avg_quality_score(project_id: int) -> float:
    """Compute the average quality_score from enriched businesses.jsonl."""
    base = PROJECT_ROOT / "data" / str(project_id)
    businesses_file = base / "enriched" / "businesses.jsonl"
    if not businesses_file.exists():
        return 0.0
    scores = []
    try:
        for line in open(businesses_file):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            qs = obj.get("quality_score")
            if qs is not None:
                scores.append(float(qs))
    except Exception:
        pass
    return round(sum(scores) / len(scores), 1) if scores else 0.0


def _get_niche_icon(directory_name: str) -> str:
    """Return the Lucide icon name for a directory's niche, or fallback.

    Matches by exact name first, then falls back to substring matching
    against the keys in the niche_icons map (so 'Mobile Dog Grooming'
    still matches the 'Mobile Dog Groomers' entry). Uses 'store' as the
    final fallback for any niche not in the table.
    """
    niche_map = STAGES_CONFIG.get("niche_icons", {})
    if not niche_map:
        return "store"
    # Exact match first
    if directory_name in niche_map:
        return niche_map[directory_name]
    # Substring match: check if the directory name contains a known niche keyword
    name_lower = directory_name.lower()
    for niche_key, icon_name in niche_map.items():
        if niche_key == "default":
            continue
        if niche_key.lower() in name_lower:
            return icon_name
    return niche_map.get("default", "store")


# ─── Consolidated card builder ─────────────────────────────────────────────

def build_directory_card(proj) -> dict:
    """Build a single directory card dict from a project row.

    This is the single source of truth for the card shape used by BOTH:
      - overview() page route (rendered into overview.html)
      - api_directories() JSON API route

    The proj argument can be a sqlite3.Row or a dict-like object with keys:
    id, name, slug, country, status, field_tier, created_at, updated_at.

    The returned dict is a superset of both original implementations:
    it includes ``country``, ``status``, and ``field_tier`` (needed by the
    JSON API consumer / frontend filters) even though the HTML template
    only reads id, name, slug, niche_icon, place_count, current_stage,
    status_class, stages, created_at, and updated_at.  Extra keys are
    harmlessly ignored by Jinja2's dot/bracket access.
    """
    from ..services.pipeline import _compute_pipeline_state, _current_stage_label

    pid = proj["id"]
    stages = _compute_pipeline_state(pid)
    counts = _directory_counts(pid)
    current_stage_label, status_class = _current_stage_label(pid)

    card = {
        "id": pid,
        "name": proj["name"],
        "slug": proj["slug"],
        "country": proj["country"],
        "status": proj["status"] or "idle",
        "field_tier": proj["field_tier"] or "Essentials",
        "niche_icon": _get_niche_icon(proj["name"]),
        "place_count": counts["places_collected"],
        "current_stage": current_stage_label,
        "status_class": status_class,
        "stages": stages,
        "created_at": proj["created_at"] or "",
        "updated_at": proj["updated_at"] or "",
        "action_button_label": "View Project",
    }
    return card
