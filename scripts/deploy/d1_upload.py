"""D1 Upload Module (Phase 4)

Takes cleaned + enriched records from ``data/<project_id>/enriched/*.jsonl``
and uploads them into a per-directory Cloudflare D1 database via the
Cloudflare REST API, using the exact schema defined in ``Data-Model-Spec.md``.

Per the architecture decision in the plan doc, **one D1 database per
directory** — credentials are NOT in ``.env`` but passed at runtime
as params (D1_ACCOUNT_ID, D1_DATABASE_ID). The Cloudflare API token
comes from the environment (``CLOUDFLARE_API_TOKEN``).

**Upload order (FK-safe, per Data-Model-Spec.md):**
  states → regions → suburbs → businesses →
  business_features / business_hours / business_services →
  content (content last, since business-level rows need `business.id`)

**Recomputes `business_count`** on states/regions/suburbs as part of
the upload pass (simple COUNT grouped by the relevant FK).

Usage via the Phase 3 runner:
    python runner/run.py upload.d1 --project-id=5 \
        --params='{"d1_account_id": "...", "d1_database_id": "...", "site_name": "Test"}'

The script:
  1. Reads the D1 schema DDL and runs it (CREATE TABLE IF NOT EXISTS)
  2. Reads enriched JSONL records
  3. Upserts states → regions → suburbs → businesses (in order)
  4. Upserts business_features, business_hours, business_services
  5. Upserts content rows (geography-level + business-level)
  6. Recomputes business_count on states/regions/suburbs
  7. Inserts/updates site_config branding rows
"""

import json
import os
import sys
import logging
from datetime import datetime, timezone

import requests

logger = logging.getLogger(__name__)

# ─── Path setup (Phase 3 pattern) ──────────────────────────────────────────────
# __file__ = directory-factory/scripts/deploy/d1_upload.py
#   dirname(1) = scripts/deploy
#   dirname(2) = scripts  ← _SCRIPTS_DIR
#   dirname(3) = directory-factory  ← _PROJECT_ROOT
_SCRIPTS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_SCRIPTS_DIR)
_SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "scripts")

# _PROJECT_ROOT on path → makes `runner` importable as a package
for p in (_PROJECT_ROOT, _SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from runner.contract import script_main

_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_SCHEMA_PATH = os.path.join(_SCRIPTS_DIR, "deploy", "d1_schema.sql")

# Cloudflare D1 REST API endpoint
D1_API_BASE = "https://api.cloudflare.com/client/v4"


# ─── Cloudflare D1 API ─────────────────────────────────────────────────────────

def d1_execute(
    account_id: str,
    database_id: str,
    sql_statements: str,
    api_token: str | None = None,
) -> list:
    """Execute SQL statements against a Cloudflare D1 database via REST API.

    Uses the ``/accounts/{account_id}/d1/database/{database_id}/execute``
    endpoint which accepts a JSON payload with ``jsonql_statements`` key.

    Args:
        account_id: Cloudflare account ID.
        database_id: D1 database ID (UUID format).
        sql_statements: One or more SQL statements separated by semicolons.
        api_token: Cloudflare API token. Falls back to
            ``CLOUDFLARE_API_TOKEN`` env var.

    Returns:
        The ``result`` array from the Cloudflare API response. Each element
        corresponds to one executed statement and has a ``results`` key
        for SELECT queries.

    Raises:
        RuntimeError on API-level errors or missing token.
        requests.HTTPError on non-2xx responses.
    """
    token = api_token or os.getenv("CLOUDFLARE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "CLOUDFLARE_API_TOKEN environment variable is not set. "
            "Pass it as params.d1_api_token, or set the env var. "
            "Requires D1 write access."
        )

    url = f"{D1_API_BASE}/accounts/{account_id}/d1/database/{database_id}/execute"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {"jsonql_statements": sql_statements}

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("success"):
        errors = data.get("errors", [])
        raise RuntimeError(f"Cloudflare API error: {errors}")

    result = data.get("result", [])
    # D1 returns result as an array of statement results:
    # [{"stmt_id": 0, "success": true, "results": [...], "meta": {...}}, ...]
    # For SELECT, "results" is a list of row dicts. For INSERT/UPDATE,
    # "results" may be None or absent.
    # Normalize to always return a list of dicts (for single-statement SELECT,
    # return the first statement's results list).
    if isinstance(result, list):
        if len(result) == 1 and isinstance(result[0], dict):
            first = result[0]
            if "results" in first and isinstance(first["results"], list):
                return first["results"]
            return result
    return result


def d1_execute_batch(
    account_id: str,
    database_id: str,
    statements: list[str],
    api_token: str | None = None,
    batch_size: int = 100,
) -> None:
    """Execute a list of SQL statements in batches.

    Cloudflare D1 has limits on the number of statements per request
    and on payload size. This splits the statements into batches.

    Args:
        account_id: Cloudflare account ID.
        database_id: D1 database ID.
        statements: List of full SQL statements (INSERT/UPDATE/etc.).
        api_token: Cloudflare API token.
        batch_size: Max statements per API call (default 100).
    """
    for i in range(0, len(statements), batch_size):
        batch = statements[i : i + batch_size]
        sql = "; ".join(batch) + ";"
        d1_execute(account_id, database_id, sql, api_token)


# ─── SQL value escaping ────────────────────────────────────────────────────────

def sql_str(value) -> str:
    """Escape a Python value for safe inline SQL insertion in D1 (SQLite).

    D1 supports parameterized queries via ``params``, but for bulk inserts
    with hundreds of rows, inline escaping is simpler and faster.
    We escape by doubling single quotes (SQL standard).
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    # String: escape single quotes, wrap in single quotes
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def sql_json(value) -> str:
    """Serialize a Python object as a JSON string literal for SQL."""
    if value is None:
        return "NULL"
    escaped = json.dumps(value).replace("'", "''")
    return f"'{escaped}'"


def compute_word_count(body: str) -> int:
    """Compute word count for content body (per Data-Model-Spec.md:
    `len(body.split())` in Python, since D1/SQLite has no regexp functions)."""
    if body is None:
        return 0
    return len(body.split())


# ─── Record → SQL builders (upload order: states → regions → suburbs → businesses → features/hours/services → content) ─
# ─── Phase 0: Schema ─────────────────────────────────────────────────────────────

def build_schema_sql() -> str:
    """Load and return the D1 schema DDL from d1_schema.sql."""
    if not os.path.isfile(_SCHEMA_PATH):
        raise FileNotFoundError(f"D1 schema not found at {_SCHEMA_PATH}")
    with open(_SCHEMA_PATH) as f:
        return f.read().rstrip(";")


# ─── Phase 1: site_config ──────────────────────────────────────────────────────

def build_site_config_upserts(site_name: str, params: dict) -> list[str]:
    """Build INSERT OR REPLACE statements for the site_config table."""
    now = datetime.now(timezone.utc).isoformat()
    site_slug = params.get("site_slug", site_name.lower().replace(" ", "-").replace("_", "-"))

    rows = [
        ("site_name", site_name, "text", "general", 1),
        ("tagline", params.get("tagline", ""), "text", "general", 1),
        ("niche_label", params.get("niche_label", ""), "text", "general", 1),
        ("domain", params.get("domain", ""), "text", "general", 1),
        ("contact_email", params.get("contact_email", ""), "text", "contact", 1),
        ("contact_phone", params.get("contact_phone", ""), "text", "contact", 1),
        ("social_links", json.dumps(params.get("social_links", [])), "json", "contact", 1),
        ("theme_primary_color", params.get("theme_primary_color", ""), "text", "appearance", 1),
        ("theme_secondary_color", params.get("theme_secondary_color", ""), "text", "appearance", 1),
        ("logo_url", params.get("logo_url", ""), "text", "appearance", 1),
        ("og_image_url", params.get("og_image_url", ""), "text", "seo", 1),
        ("legal_privacy_copy", params.get("legal_privacy_copy", ""), "text", "legal", 1),
        ("legal_terms_copy", params.get("legal_terms_copy", ""), "text", "legal", 1),
        ("created_at", now, "text", "general", 0),
    ]

    statements = []
    for key, value, vtype, group, is_public in rows:
        statements.append(
            f"INSERT OR REPLACE INTO site_config (key, value, value_type, config_group, is_public, updated_at) "
            f"VALUES ({sql_str(key)}, {sql_str(value)}, {sql_str(vtype)}, {sql_str(group)}, {sql_str(is_public)}, {sql_str(now)})"
        )
    return statements


# ─── Phase 2: States ──────────────────────────────────────────────────────────

def build_state_upsert(record: dict) -> str | None:
    """Build an UPSERT for a state row from a cleaned record's state_code."""
    code = record.get("state_code")
    if not code:
        return None
    # Derive state name and slug from code (Australian states)
    state_names = {
        "NSW": ("New South Wales", "nsw"),
        "VIC": ("Victoria", "vic"),
        "QLD": ("Queensland", "qld"),
        "WA": ("Western Australia", "wa"),
        "SA": ("South Australia", "sa"),
        "TAS": ("Tasmania", "tas"),
        "ACT": ("Australian Capital Territory", "act"),
        "NT": ("Northern Territory", "nt"),
    }
    if code in state_names:
        name, slug = state_names[code]
    else:
        name = code
        slug = code.lower()

    now = datetime.now(timezone.utc).isoformat()
    return (
        f"INSERT INTO states (code, name, slug, business_count, updated_at) "
        f"VALUES ({sql_str(code)}, {sql_str(name)}, {sql_str(slug)}, 0, {sql_str(now)}) "
        f"ON CONFLICT(code) DO UPDATE SET name=excluded.name, slug=excluded.slug, updated_at=excluded.updated_at"
    )


# ─── Phase 3: Regions ─────────────────────────────────────────────────────────

def build_region_upsert(record: dict) -> str | None:
    """Build an UPSERT for a region row from a cleaned record."""
    region_name = record.get("region_name")
    state_code = record.get("state_code")
    if not region_name or not state_code:
        return None

    slug = region_name.lower().replace(" ", "-").replace("_", "-")
    now = datetime.now(timezone.utc).isoformat()

    return (
        f"INSERT INTO regions (name, slug, state_code, business_count, updated_at) "
        f"VALUES ({sql_str(region_name)}, {sql_str(slug)}, {sql_str(state_code)}, 0, {sql_str(now)}) "
        f"ON CONFLICT(slug, state_code) DO UPDATE SET name=excluded.name, updated_at=excluded.updated_at"
    )


# ─── Phase 4: Suburbs ─────────────────────────────────────────────────────────

def build_suburb_upsert(record: dict) -> str | None:
    """Build an UPSERT for a suburb row from a cleaned record."""
    suburb_name = record.get("suburb_name")
    state_code = record.get("state_code")
    region_name = record.get("region_name")
    postcode = record.get("postal_code")
    if not suburb_name or not state_code:
        return None

    slug = suburb_name.lower().replace(" ", "-").replace("_", "-")
    now = datetime.now(timezone.utc).isoformat()

    # Suburb references region_id — we need to look it up by (slug, state_code)
    region_slug = region_name.lower().replace(" ", "-").replace("_", "-") if region_name else None
    return (
        f"INSERT INTO suburbs (name, slug, state_code, postcode, business_count, updated_at) "
        f"VALUES ({sql_str(suburb_name)}, {sql_str(slug)}, {sql_str(state_code)}, {sql_str(postcode)}, 0, {sql_str(now)}) "
        f"ON CONFLICT(slug, state_code) DO UPDATE SET "
        f"name=excluded.name, postcode=excluded.postcode, updated_at=excluded.updated_at"
    )


# ─── Phase 5: Businesses ────────────────────────────────────────────────────────

def build_business_upsert_sql(record: dict) -> str:
    """Build an UPSERT statement for a business record.

    Maps cleaned/enriched JSONL fields to the D1 `businesses` table schema
    per Data-Model-Spec.md §"Field origin map".
    """
    now = datetime.now(timezone.utc).isoformat()

    columns = [
        "google_place_id", "name", "slug", "category",
        "address", "state_code", "postcode",
        "latitude", "longitude",
        "phone", "website",
        "is_mobile_service", "is_emergency_service", "service_radius_km",
        "opening_hours_raw", "is_24_hours",
        "google_rating", "google_rating_count", "google_photo_url",
        "data_completeness_score", "quality_score",
        "enriched_at", "updated_at",
    ]

    values = [
        sql_str(record.get("place_id")),
        sql_str(record.get("name")),
        sql_str(record.get("slug")),
        sql_str(record.get("category") or record.get("primary_type")),
        sql_str(record.get("address") or record.get("formatted_address")),
        sql_str(record.get("state_code")),
        sql_str(record.get("postal_code")),
        sql_str(record.get("lat") or record.get("latitude")),
        sql_str(record.get("lng") or record.get("longitude")),
        sql_str(record.get("phone") or record.get("national_phone")),
        sql_str(record.get("website")),
        sql_str(record.get("is_mobile_service", False)),
        sql_str(record.get("is_emergency_service", False)),
        sql_str(record.get("service_radius_km")),
        sql_str(record.get("opening_hours_raw")),
        sql_str(record.get("is_24_hours", False)),
        sql_str(record.get("rating") or record.get("google_rating")),
        sql_str(record.get("user_rating_count") or record.get("google_rating_count")),
        sql_str(record.get("google_photo_url")),
        sql_str(record.get("data_completeness_score")),
        sql_str(record.get("quality_score")),
        sql_str(record.get("enriched_at") or now),
        sql_str(now),
    ]

    col_str = ", ".join(columns)
    val_str = ", ".join(values)
    # UPSERT on google_place_id (UNIQUE constraint)
    updates = ", ".join(
        f"{c} = excluded.{c}" for c in columns
        if c not in ("google_place_id",)
    )

    return (
        f"INSERT INTO businesses ({col_str}) VALUES ({val_str}) "
        f"ON CONFLICT(google_place_id) DO UPDATE SET {updates}"
    )


# ─── Phase 6: Features / Hours / Services ──────────────────────────────────────

def build_feature_inserts(business_id: int, features: list) -> list[str]:
    """Build INSERT OR IGNORE statements for business_features."""
    statements = []
    for feat in features:
        if isinstance(feat, dict):
            key = feat.get("feature_key") or feat.get("key")
        else:
            key = feat
        if key:
            statements.append(
                f"INSERT OR IGNORE INTO business_features (business_id, feature_key) "
                f"VALUES ({business_id}, {sql_str(key)})"
            )
    return statements


def build_hours_inserts(business_id: int, hours_rows: list) -> list[str]:
    """Build INSERT OR IGNORE statements for business_hours.

    Maps the Phase 2 hours_rows format (day_of_week, open_mins, close_mins, etc.)
    to the Data-Model-Spec.md simplified schema (day_of_week, open_mins,
    close_mins, is_closed).
    """
    statements = []
    for row in hours_rows:
        dow = row.get("day_of_week")
        if dow is None:
            continue

        open_mins = row.get("open_mins")
        close_mins = row.get("close_mins")
        is_closed = 1 if (open_mins is None and close_mins is None) else 0
        # If parse_status indicates "unknown" or "failed", mark as closed
        parse_status = row.get("parse_status", "")
        if parse_status in ("unknown", "failed"):
            is_closed = 1

        statements.append(
            f"INSERT OR IGNORE INTO business_hours (business_id, day_of_week, open_mins, close_mins, is_closed) "
            f"VALUES ({business_id}, {sql_str(dow)}, {sql_str(open_mins)}, {sql_str(close_mins)}, {sql_str(is_closed)})"
        )
    return statements


def build_service_inserts(business_id: int, services: list) -> list[str]:
    """Build INSERT OR IGNORE statements for business_services.

    Only service names are extracted (pricing fields left NULL per spec).
    """
    statements = []
    for svc in services:
        if isinstance(svc, dict):
            name = svc.get("name") or svc.get("service_name")
        else:
            name = svc
        if name:
            statements.append(
                f"INSERT OR IGNORE INTO business_services (business_id, service_name) "
                f"VALUES ({business_id}, {sql_str(name)})"
            )
    return statements


# ─── Phase 7: Content (EEAT) ──────────────────────────────────────────────────

def build_content_upsert(
    entity_type: str,
    entity_id,
    content_type: str,
    body: str,
    ai_model: str | None = None,
) -> str:
    """Build an UPSERT for a content row.

    Per Data-Model-Spec.md: ``word_count`` is computed in Python
    (``len(body.split())``) since D1/SQLite has no regexp functions.
    """
    word_count = compute_word_count(body)
    now = datetime.now(timezone.utc).isoformat()

    return (
        f"INSERT INTO content (entity_type, entity_id, content_type, body, word_count, ai_model, approved, generated_at) "
        f"VALUES ({sql_str(entity_type)}, {sql_str(str(entity_id))}, {sql_str(content_type)}, "
        f"{sql_str(body)}, {sql_str(word_count)}, {sql_str(ai_model)}, 1, {sql_str(now)}) "
        f"ON CONFLICT(entity_type, entity_id, content_type) DO UPDATE SET "
        f"body=excluded.body, word_count=excluded.word_count, ai_model=excluded.ai_model, "
        f"generated_at=excluded.generated_at"
    )


# ─── Phase 8: business_count recomputation ─────────────────────────────────────

def build_count_recompute_statements() -> list[str]:
    """Build SQL statements to recompute business_count on geography tables.

    Per Data-Model-Spec.md: 'a simple COUNT grouped by the relevant FK'.
    """
    return [
        # Count businesses per state
        "UPDATE states SET business_count = ("
        "  SELECT COUNT(*) FROM businesses b WHERE b.state_code = states.code"
        ")",
        # Count businesses per region
        "UPDATE regions SET business_count = ("
        "  SELECT COUNT(*) FROM businesses b WHERE b.region_id = regions.id"
        ")",
        # Count businesses per suburb
        "UPDATE suburbs SET business_count = ("
        "  SELECT COUNT(*) FROM businesses b WHERE b.suburb_id = suburbs.id"
        ")",
    ]


# ─── Slug → id resolution helpers ──────────────────────────────────────────────
# Per Data-Model-Spec.md: resolve top-down once, then join on integer ids

def resolve_ids_placeholder(slugs_sql: str) -> str:
    """SQL snippet to look up ids from slugs. Returns a SELECT query."""
    return f"SELECT id, slug FROM businesses WHERE slug IN ({slugs_sql})"


# ─── Main upload logic ─────────────────────────────────────────────────────────

def upload_project(project_id: int, params: dict) -> dict:
    """Upload enriched records to a per-directory D1 database.

    Args:
        project_id: The collection project ID (determines which
            ``data/<project_id>/enriched/*.jsonl`` files to read).
        params: Must include:
            - ``d1_account_id``: Cloudflare account ID
            - ``d1_database_id``: D1 database ID
            - ``site_name``: Brand name for the directory
            - ``d1_api_token``: (optional) Cloudflare API token. If not
              provided, falls back to ``CLOUDFLARE_API_TOKEN`` env var.
        Optional params:
            - ``dry_run``: If True, print what would be uploaded without executing
            - ``site_slug``, ``tagline``, ``niche_label``, ``domain``, etc. (site_config fields)

    Returns:
        Dict with ``summary`` and ``counts``.
    """
    # ── Validate required params ─────────────────────────────────────────────
    account_id = params.get("d1_account_id")
    database_id = params.get("d1_database_id")
    site_name = params.get("site_name")
    dry_run = params.get("dry_run", False)

    if not account_id:
        raise ValueError("params.d1_account_id is required (Cloudflare account ID)")
    if not database_id:
        raise ValueError("params.d1_database_id is required (D1 database ID)")
    if not site_name:
        raise ValueError("params.site_name is required (directory branding name)")

    api_token = params.get("d1_api_token") or os.getenv("CLOUDFLARE_API_TOKEN")
    if not dry_run and not api_token:
        raise RuntimeError(
            "No Cloudflare API token available. Pass params.d1_api_token or set "
            "CLOUDFLARE_API_TOKEN env var."
        )

    # ── Read per-table enriched JSONL ─────────────────────────────────────────
    enriched_dir = os.path.join(_DATA_DIR, str(project_id), "enriched")
    biz_path = os.path.join(enriched_dir, "businesses.jsonl")
    if not os.path.isfile(biz_path):
        raise FileNotFoundError(
            f"Enriched data not found at {enriched_dir}. "
            f"Run 'enrichment.enrich --project-id={project_id}' first."
        )

    def _read_jsonl(path: str) -> list[dict]:
        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    records = _read_jsonl(biz_path)
    states = _read_jsonl(os.path.join(enriched_dir, "states.jsonl"))
    regions = _read_jsonl(os.path.join(enriched_dir, "regions.jsonl"))
    suburbs = _read_jsonl(os.path.join(enriched_dir, "suburbs.jsonl"))
    content_rows = _read_jsonl(os.path.join(enriched_dir, "content.jsonl"))

    if not records:
        return {
            "summary": f"No records to upload for project {project_id} (empty file)",
            "counts": {"records": 0, "states": 0, "regions": 0, "suburbs": 0,
                       "businesses": 0, "features": 0, "hours": 0, "services": 0,
                       "content": 0, "business_count_updated": False},
        }

    # ── Build all SQL statements in upload order ─────────────────────────────
    all_statements = []          # Schema + site_config + states/regions/suburbs/businesses
    dep_statements = []          # features/hours/services (need business_id)
    content_statements = []      # content rows (content last)
    site_config_statements = []  # site_config rows

    # 2. site_config
    site_config_statements = build_site_config_upserts(site_name, params)
    all_statements.extend(site_config_statements)

    # 3. States — from states.jsonl (deduped, business_count pre-computed)
    for st in states:
        code = st.get("code")
        if not code:
            continue
        name = st.get("name", code)
        slug = st.get("slug", code.lower())
        biz_count = st.get("business_count", 0)
        now = datetime.now(timezone.utc).isoformat()
        stmt = (
            f"INSERT INTO states (code, name, slug, business_count, updated_at) "
            f"VALUES ({sql_str(code)}, {sql_str(name)}, {sql_str(slug)}, {sql_str(biz_count)}, {sql_str(now)}) "
            f"ON CONFLICT(code) DO UPDATE SET name=excluded.name, slug=excluded.slug, "
            f"business_count=excluded.business_count, updated_at=excluded.updated_at"
        )
        all_statements.append(stmt)

    # 4. Regions — from regions.jsonl
    for reg in regions:
        slug = reg.get("slug")
        state_code = reg.get("state_code")
        if not slug or not state_code:
            continue
        name = reg.get("name", slug)
        biz_count = reg.get("business_count", 0)
        now = datetime.now(timezone.utc).isoformat()
        stmt = (
            f"INSERT INTO regions (slug, state_code, name, business_count, updated_at) "
            f"VALUES ({sql_str(slug)}, {sql_str(state_code)}, {sql_str(name)}, {sql_str(biz_count)}, {sql_str(now)}) "
            f"ON CONFLICT(slug, state_code) DO UPDATE SET name=excluded.name, "
            f"business_count=excluded.business_count, updated_at=excluded.updated_at"
        )
        all_statements.append(stmt)

    # 5. Suburbs — from suburbs.jsonl
    for sub in suburbs:
        slug = sub.get("slug")
        state_code = sub.get("state_code")
        if not slug or not state_code:
            continue
        name = sub.get("name", slug)
        postcode = sub.get("postcode")
        biz_count = sub.get("business_count", 0)
        now = datetime.now(timezone.utc).isoformat()
        stmt = (
            f"INSERT INTO suburbs (slug, state_code, name, postcode, business_count, updated_at) "
            f"VALUES ({sql_str(slug)}, {sql_str(state_code)}, {sql_str(name)}, {sql_str(postcode)}, {sql_str(biz_count)}, {sql_str(now)}) "
            f"ON CONFLICT(slug, state_code) DO UPDATE SET name=excluded.name, "
            f"postcode=excluded.postcode, business_count=excluded.business_count, "
            f"updated_at=excluded.updated_at"
        )
        all_statements.append(stmt)

    # 6. Businesses — region_slug/suburb_slug already on each record (from cleaning)
    all_statements.append("; ".join(build_count_recompute_statements()))
    for record in records:
        all_statements.append(build_business_upsert_sql(record))

    # ── Dry run mode ──────────────────────────────────────────────────────
    if dry_run:
        total_features = sum(len(r.get("feature_keys", [])) for r in records)
        total_hours = sum(len(r.get("hours_rows", [])) for r in records)
        total_services = 0
        total_biz_content = 0
        for r in content_rows:
            if r.get("entity_type") == "business":
                total_biz_content += 1
        total_geo_content = sum(1 for r in content_rows if r.get("entity_type") != "business")
        total_content = total_biz_content + total_geo_content

        return {
            "summary": (f"[DRY RUN] Would upload {len(records)} businesses to D1 "
                        f"database {database_id} via flat per-table pipeline: "
                        f"schema → site_config → {len(states)} states → "
                        f"{len(regions)} regions → {len(suburbs)} suburbs → "
                        f"businesses → features/hours/services → content ({len(content_rows)} rows) + count recompute"),
            "counts": {
                "records": len(records),
                "states": len(states),
                "regions": len(regions),
                "suburbs": len(suburbs),
                "businesses": len(records),
                "features": total_features,
                "hours": total_hours,
                "services": total_services,
                "content": total_content,
                "content_business": total_biz_content,
                "content_geography": total_geo_content,
                "dry_run": True,
                "statements_batch1": len(all_statements),
            },
        }

    # ── Execute Level 1-5: schema + site_config + geography + businesses ──
    d1_execute(account_id, database_id,
               "; ".join(all_statements) + ";", api_token)
    d1_execute(account_id, database_id,
               "; ".join(build_count_recompute_statements()) + ";",
               api_token)

    # ── Resolve natural keys → real D1 ids ────────────────────────────────────
    id_map = {}  # place_id (google_place_id) → business.id

    # Get business ids
    biz_place_ids = [r.get("place_id") for r in records if r.get("place_id")]
    if biz_place_ids:
        placeholders = ", ".join(sql_str(pid) for pid in biz_place_ids)
        biz_lookup = d1_execute(account_id, database_id,
            f"SELECT id, google_place_id FROM businesses WHERE google_place_id IN ({placeholders})",
            api_token)
        if isinstance(biz_lookup, list):
            for row in biz_lookup:
                if isinstance(row, dict):
                    id_map[row["google_place_id"]] = row["id"]

    # Get geography ids (state code, region slug+state_code, suburb slug+state_code)
    geo_lookup = d1_execute(account_id, database_id,
        "SELECT id, code FROM states; "
        "SELECT id, slug, state_code FROM regions; "
        "SELECT id, slug, state_code FROM suburbs;",
        api_token)

    state_id_map = {}   # code → id
    region_id_map = {}  # (slug, state_code) → id
    suburb_id_map = {}  # (slug, state_code) → id

    if isinstance(geo_lookup, list):
        for idx, row_set in enumerate(geo_lookup):
            if isinstance(row_set, dict) and "results" in row_set:
                results = row_set["results"]
            elif isinstance(row_set, list):
                results = row_set
            else:
                continue
            for row in results:
                if not isinstance(row, dict):
                    continue
                if idx == 0:  # states
                    state_id_map[row["code"]] = row["id"]
                elif idx == 1:  # regions
                    region_id_map[(row["slug"], row["state_code"])] = row["id"]
                elif idx == 2:  # suburbs
                    suburb_id_map[(row["slug"], row["state_code"])] = row["id"]

    # ── Build FK resolution UPDATE statements for businesses ────────────────
    update_geo_sql_parts = []
    for record in records:
        place_id = record.get("place_id")
        if not place_id:
            continue
        updates = []

        state_code = record.get("state_code")
        if state_code and state_code in state_id_map:
            updates.append(f"state_id = {state_id_map[state_code]}")

        region_slug = record.get("region_slug")
        if region_slug and state_code and (region_slug, state_code) in region_id_map:
            updates.append(f"region_id = {region_id_map[(region_slug, state_code)]}")

        suburb_slug = record.get("suburb_slug")
        if suburb_slug and state_code and (suburb_slug, state_code) in suburb_id_map:
            updates.append(f"suburb_id = {suburb_id_map[(suburb_slug, state_code)]}")

        if updates:
            update_geo_sql_parts.append(
                f"UPDATE businesses SET {', '.join(updates)} "
                f"WHERE google_place_id = {sql_str(place_id)}"
            )

    # ── Build dependent inserts (features/hours/services) ───────────────────
    dep_statements = []
    content_count = 0

    for record in records:
        biz_id = id_map.get(record.get("place_id"))
        if biz_id is None:
            continue

        # Features
        features = record.get("feature_keys", record.get("features", []))
        if features:
            dep_statements.extend(build_feature_inserts(biz_id, features))

        # Hours
        hours_rows = record.get("hours_rows", [])
        if hours_rows:
            dep_statements.extend(build_hours_inserts(biz_id, hours_rows))

        # Services
        services = record.get("services", [])
        if not services:
            services = record.get("enrichment", {}).get("services", [])
        if services:
            dep_statements.extend(build_service_inserts(biz_id, services))

    # ── Build content rows from content.jsonl ───────────────────────────────
    content_statements = []

    for crow in content_rows:
        etype = crow.get("entity_type", "")
        eid = crow.get("entity_id", "")
        ctype = crow.get("content_type", "")
        body = crow.get("body", "")
        ai_model = crow.get("ai_model") or "gemini-2.5-flash-lite"

        # Resolve natural key entity_id → real D1 id
        # Spec format (per Data-Model-Spec.md §Intermediate Pipeline Data Format):
        #   state:   entity_id = code (e.g. "QLD")
        #   region:  entity_id = "slug:state_code" (e.g. "brisbane:QLD")
        #   suburb:  entity_id = "slug:state_code" (e.g. "west-end:QLD")
        #   business: entity_id = google_place_id
        real_id = None
        if etype == "state":
            # entity_id is the state code directly
            real_id = state_id_map.get(eid)
        elif etype == "region":
            # entity_id format: "slug:state_code" (e.g. "brisbane:QLD")
            if eid and ":" in eid:
                slug, state_code = eid.split(":", 1)
                real_id = region_id_map.get((slug, state_code))
            else:
                logger.warning(f"Region content row has invalid entity_id '{eid}' — skipping")
                continue
        elif etype == "suburb":
            # entity_id format: "slug:state_code" (e.g. "west-end:QLD")
            if eid and ":" in eid:
                slug, state_code = eid.split(":", 1)
                real_id = suburb_id_map.get((slug, state_code))
            else:
                logger.warning(f"Suburb content row has invalid entity_id '{eid}' — skipping")
                continue
        elif etype == "business":
            # entity_id is the google_place_id (same as place_id)
            real_id = id_map.get(eid)

        if real_id is None:
            logger.warning(f"Content row entity_id '{eid}' ({etype}) could not be resolved to a D1 id — skipping")
            continue

        content_statements.append(
            build_content_upsert(etype, real_id, ctype, body, ai_model)
        )
        content_count += 1

    # ── Execute geography ID updates ────────────────────────────────────
    if update_geo_sql_parts:
        d1_execute_batch(account_id, database_id, update_geo_sql_parts, api_token, batch_size=50)

    # ── Execute dependent inserts (features/hours/services) ──────────────
    if dep_statements:
        d1_execute_batch(account_id, database_id, dep_statements, api_token)

    # ── Execute content rows (content LAST) ──────────────────────────────
    if content_statements:
        d1_execute_batch(account_id, database_id, content_statements, api_token)

    return {
        "summary": (f"Uploaded {len(records)} businesses to D1 database {database_id} "
                    f"(states: {len(states)}, regions: {len(regions)}, "
                    f"suburbs: {len(suburbs)})"),
        "counts": {
            "records": len(records),
            "states": len(states),
            "regions": len(regions),
            "suburbs": len(suburbs),
            "businesses": len(records),
            "features": len([s for s in dep_statements if s.startswith("INSERT OR IGNORE INTO business_features")]),
            "hours": len([s for s in dep_statements if s.startswith("INSERT OR IGNORE INTO business_hours")]),
            "services": len([s for s in dep_statements if s.startswith("INSERT OR IGNORE INTO business_services")]),
            "content": content_count,
        },
    }


# ─── Geography-level content helpers ───────────────────────────────────────────
# These generate EEAT content for state/region/suburb pages using placeholders
# that get substituted at render time (per Data-Model-Spec.md)

def build_state_content(state_name: str, state_code: str, biz_count: int, niche: str) -> dict:
    """Generate EEAT content rows for a state-level page.

    Uses {{placeholder}} syntax per Data-Model-Spec.md — placeholders are
    replaced at Astro render time.
    """
    niche_label = niche or "{{niche_label}}"
    return {
        "about": f"Browse {biz_count} {niche_label} services across {state_name}, {{state_code}}. "
                 f"We've verified each listing for quality and local expertise.",
        "local_context": f"{{state_name}} has {{business_count}} {niche_label} providers serving "
                         f"both metropolitan and regional areas. Our platform connects you "
                         f"with trusted local professionals who understand the unique needs "
                         f"of {{state_name}} residents.",
        "faq": f"How do I find the best {niche_label} in {state_name}? "
               f"We list only verified providers with real customer reviews. "
               f"Each business is tagged with its service area and availability.",
        "meta_title": f"{niche_label} in {state_name} — Find Verified Local Providers",
        "meta_description": f"Find {{business_count}} {niche_label} services in {state_name}. "
                            f"Browsed by region and suburb. Verified listings only.",
    }


def build_geo_content(level: str, geo_name: str, state_code: str, biz_count: int, niche: str) -> dict:
    """Generate EEAT content rows for a region or suburb page."""
    niche_label = niche or "{{niche_label}}"
    return {
        "about": f"Find {niche_label} services in {geo_name}. We've verified {{business_count}} local providers "
                 f"to help you find the right service for your needs.",
        "local_context": f"{{region_name}} residents trust our directory to find quality {niche_label}. "
                         f"With {{business_count}} providers operating in this area, you're sure to find "
                         f"the right service. Our verification process checks credentials, "
                         f"reviews, and local expertise.",
        "faq": f"What {niche_label} services are available in {geo_name}? "
               f"Browse our full list of verified providers serving {{region_name}}, "
               f"complete with ratings, hours, and service details.",
        "meta_title": f"{niche_label} in {geo_name} — Verified Local Directory",
        "meta_description": f"Find {niche_label} services in {geo_name}. "
                            f"Verified providers with real reviews. Serving the {{region_name}} area.",
    }


@script_main
def main(project_id: int, params: dict) -> dict:
    """D1 Upload — standard script entry point (Phase 3 contract).

    Params (required):
        d1_account_id   — Cloudflare account ID
        d1_database_id  — D1 database ID for this directory
        site_name       — Brand name for the directory

    Params (optional):
        d1_api_token    — Cloudflare API token (default: env CLOUDFLARE_API_TOKEN)
        site_slug       — URL-safe slug for the site
        niche_label     — e.g. "Mobile Dog Groomers"
        dry_run         — If True, print what would be uploaded without executing

    Upload order (per Data-Model-Spec.md):
        states → regions → suburbs → businesses →
        features/hours/services → content (content last)
    """
    return upload_project(project_id, params)


if __name__ == "__main__":
    main()
