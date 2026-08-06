"""D1 Upload Module (Phase 4)

Takes cleaned + enriched records from ``data/enriched_<project_id>.jsonl``
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
from datetime import datetime, timezone

import requests

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
            ``data/enriched_<project_id>.jsonl`` file to read).
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

    # ── Read enriched JSONL ──────────────────────────────────────────────────
    input_path = os.path.join(_DATA_DIR, f"enriched_{project_id}.jsonl")
    if not os.path.isfile(input_path):
        raise FileNotFoundError(
            f"Enriched data not found at {input_path}. "
            f"Run 'enrichment.enrich --project-id={project_id}' first."
        )

    records = []
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

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

    # 1. Schema DDL
    all_statements.append(build_schema_sql())

    # 2. site_config
    site_config_statements = build_site_config_upserts(site_name, params)
    all_statements.extend(site_config_statements)

    # Track unique geography entities to upsert
    states_seen = {}
    regions_seen = {}
    suburbs_seen = {}

    # 3-5. States → Regions → Suburbs → Businesses
    business_slugs = []
    for record in records:
        # States
        state_stmt = build_state_upsert(record)
        if state_stmt:
            key = record.get("state_code")
            if key and key not in states_seen:
                states_seen[key] = True
                all_statements.append(state_stmt)

        # Regions
        region_stmt = build_region_upsert(record)
        if region_stmt:
            key = (record.get("region_name"), record.get("state_code"))
            if key not in regions_seen:
                regions_seen[key] = True
                all_statements.append(region_stmt)

        # Suburbs
        suburb_stmt = build_suburb_upsert(record)
        if suburb_stmt:
            key = (record.get("suburb_name"), record.get("state_code"))
            if key not in suburbs_seen:
                suburbs_seen[key] = True
                all_statements.append(suburb_stmt)

        # Businesses (needs suburb_id/region_id resolved — handled via subquery)
        all_statements.append(build_business_upsert_sql(record))
        business_slugs.append(record.get("slug") or record.get("name", ""))

    # ── Dry run mode ──────────────────────────────────────────────────────
    if dry_run:
        total_features = sum(len(r.get("feature_keys", [])) for r in records)
        total_hours = sum(len(r.get("hours_rows", [])) for r in records)
        total_services = sum(len(r.get("services", [])) + len(r.get("enrichment", {}).get("services", [])) for r in records)
        total_content = len(records) * 6 + len(states_seen) * 5 + len(regions_seen) * 5 + len(suburbs_seen) * 5

        return {
            "summary": (f"[DRY RUN] Would upload {len(records)} businesses to D1 "
                        f"database {database_id} via 8-level pipeline: "
                        f"schema → site_config → {len(states_seen)} states → "
                        f"{len(regions_seen)} regions → {len(suburbs_seen)} suburbs → "
                        f"businesses → features/hours/services → content + count recompute"),
            "counts": {
                "records": len(records),
                "states": len(states_seen),
                "regions": len(regions_seen),
                "suburbs": len(suburbs_seen),
                "businesses": len(records),
                "features": total_features,
                "hours": total_hours,
                "services": total_services,
                "content": total_content,
                "dry_run": True,
                "statements_batch1": len(all_statements),
            },
        }

    # ── Execute Level 1-5: schema + site_config + states/regions/suburbs/businesses ─
    all_statements.append("; ".join(build_count_recompute_statements()))
    d1_execute(account_id, database_id,
               "; ".join(all_statements) + ";", api_token)

    # ── Phase 2: Look up business_ids by slug ─────────────────────────────
    # Per Data-Model-Spec.md: resolve slug → id once, then join on integer ids
    valid_slugs = [s for s in business_slugs if s]
    if valid_slugs:
        placeholders = ", ".join(sql_str(s) for s in valid_slugs)
        lookup_result = d1_execute(account_id, database_id,
            f"SELECT id, slug FROM businesses WHERE slug IN ({placeholders})",
            api_token)
    else:
        lookup_result = []

    id_map = {}
    if valid_slugs and isinstance(lookup_result, list):
        # Single SELECT: d1_execute normalizes to return just the row dicts list
        for row in lookup_result:
            if isinstance(row, dict) and "slug" in row:
                id_map[row["slug"]] = row["id"]

    # ── Phase 3: Build + execute feature/hour/service/content inserts ──────
    dep_statements = []
    content_count = 0

    # Look up geography ids for content rows and business foreign keys
    # Get region/suburb id maps
    geo_lookup = d1_execute(account_id, database_id,
        "SELECT id, slug, state_code FROM regions; "
        "SELECT id, slug, state_code FROM suburbs; "
        "SELECT code, name FROM states;",
        api_token)

    region_map = {}
    suburb_map = {}
    state_map = {}

    if isinstance(geo_lookup, list):
        for idx, row_set in enumerate(geo_lookup):
            if isinstance(row_set, dict) and "results" in row_set:
                for row in row_set["results"]:
                    if idx == 0:  # regions
                        region_map[(row["slug"], row["state_code"])] = row["id"]
                    elif idx == 1:  # suburbs
                        suburb_map[(row["slug"], row["state_code"])] = row["id"]
                    elif idx == 2:  # states
                        state_map[row["code"]] = row["name"]

    # Get updated business_count values for content placeholders
    count_lookup = d1_execute(account_id, database_id,
        "SELECT state_code, SUM(business_count) as bc FROM states GROUP BY state_code;"
        "SELECT state_code, SUM(business_count) as bc FROM regions GROUP BY state_code;"
        "SELECT state_code, SUM(business_count) as bc FROM suburbs GROUP BY state_code;",
        api_token)

    state_biz_counts = {}
    region_biz_counts = {}
    suburb_biz_counts = {}

    if isinstance(count_lookup, list):
        for idx, row_set in enumerate(count_lookup):
            if isinstance(row_set, dict) and "results" in row_set:
                for row in row_set["results"]:
                    if idx == 0: state_biz_counts[row["state_code"]] = row["bc"] or 0
                    elif idx == 1: region_biz_counts[row["state_code"]] = row["bc"] or 0
                    elif idx == 2: suburb_biz_counts[row["state_code"]] = row["bc"] or 0

    # Resolve the subquery-based foreign keys in businesses table
    # The businesses table uses subqueries to resolve region_id/suburb_id
    # from region_name/suburb_name — but we already inserted the geography
    # rows, so we need to update businesses with the resolved ids.
    # This is a post-upsert step since the original UPSERT used subqueries.
    update_biz_sql = (
        "UPDATE businesses SET "
        "suburb_id = (SELECT s.id FROM suburbs s WHERE s.slug = businesses.slug AND s.state_code = businesses.state_code), "
        "region_id = (SELECT r.id FROM regions r WHERE r.slug = businesses.slug AND r.state_code = businesses.state_code) "
        "WHERE suburb_id IS NULL OR region_id IS NULL"
    )
    # Actually, we need to resolve from the record's suburb_name/region_name, not slug.
    # Let's do it per-record after looking up geography ids.
    # The business UPSERT already set state_code from the record directly.
    # For suburb_id and region_id, we need to look them up by name+state_code.
    # We'll do this as a batch UPDATE after all geography is inserted.

    # Build UPDATE statements for suburb_id and region_id on businesses
    # (using the slug-based lookup pattern from the spec)
    update_geo_sql_parts = []
    for record in records:
        slug = record.get("slug") or record.get("name", "")
        state_code = record.get("state_code")
        region_name = record.get("region_name")
        suburb_name = record.get("suburb_name")

        if not slug or not state_code:
            continue

        region_slug = region_name.lower().replace(" ", "-").replace("_", "-") if region_name else None
        suburb_slug = suburb_name.lower().replace(" ", "-").replace("_", "-") if suburb_name else None

        updates = []
        if region_slug:
            updates.append(
                f"region_id = (SELECT r.id FROM regions r WHERE r.slug = '{region_slug}' AND r.state_code = '{state_code}')"
            )
        if suburb_slug:
            updates.append(
                f"suburb_id = (SELECT s.id FROM suburbs s WHERE s.slug = '{suburb_slug}' AND s.state_code = '{state_code}')"
            )
        if updates:
            update_geo_sql_parts.append(
                f"UPDATE businesses SET {', '.join(updates)} "
                f"WHERE slug = '{slug}' AND state_code = '{state_code}'"
            )

    # ── Build dependent inserts ─────────────────────────────────────────
    for record in records:
        slug = record.get("slug") or record.get("name", "")
        biz_id = id_map.get(slug)
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

        # Services (business_services — name only, pricing null per Data-Model-Spec.md)
        services = record.get("services", [])
        if not services:
            services = record.get("enrichment", {}).get("services", [])
        if services:
            dep_statements.extend(build_service_inserts(biz_id, services))

        # Content — business-level (about, faq, tips, meta_title, meta_description, seo_keywords)
        # Per Data-Model-Spec.md: enrichment writes content rows, not columns on businesses.
        # The enrichment output uses these field names:
        #   description → about, seo_meta_desc → meta_description,
        #   seo_keywords → seo_keywords, services → business_services (handled above)
        # We also support a pre-mapped `content` dict if it exists.
        enrichment = record.get("enrichment", {})
        content = record.get("content", {})
        merged_content = {**enrichment, **content}

        # Map enrichment field names to content_type values
        content_mapping = {
            "about": merged_content.get("about", merged_content.get("description")),
            "faq": merged_content.get("faq"),
            "tips": merged_content.get("tips"),
            "meta_title": merged_content.get("meta_title"),
            "meta_description": merged_content.get("meta_description",
                                                    merged_content.get("seo_meta_desc")),
            "seo_keywords": merged_content.get("seo_keywords"),
        }

        for ctype, body in content_mapping.items():
            if body:
                if ctype == "seo_keywords" and isinstance(body, list):
                    body = ", ".join(body)
                elif ctype in ("about", "faq", "tips") and isinstance(body, list):
                    body = " ".join(str(b) for b in body)
                content_statements.append(
                    build_content_upsert("business", biz_id, ctype, str(body),
                                        merged_content.get("ai_model", "gemini-2.5-flash-lite"))
                )
                content_count += 1

    # ── Content for geography levels ────────────────────────────────────
    # Generate content for each state/region/suburb that has businesses
    for state_code, state_name in state_map.items():
        state_content = build_state_content(state_name, state_code,
            state_biz_counts.get(state_code, 0), params.get("niche_label", "businesses"))
        for ctype, body in state_content.items():
            content_statements.append(build_content_upsert("state", state_code, ctype, body, "gemini-2.5-flash"))
            content_count += 1

    for (region_slug, state_code), region_id in region_map.items():
        region_name = region_slug.replace("-", " ").title()
        region_content = build_geo_content("region", region_name, state_code,
            region_biz_counts.get(state_code, 0), params.get("niche_label", "businesses"))
        for ctype, body in region_content.items():
            content_statements.append(build_content_upsert("region", region_id, ctype, body, "gemini-2.5-flash"))
            content_count += 1

    for (suburb_slug, state_code), suburb_id in suburb_map.items():
        suburb_name = suburb_slug.replace("-", " ").title()
        suburb_content = build_geo_content("suburb", suburb_name, state_code,
            0, params.get("niche_label", "businesses"))  # per-suburb count not available without extra query
        for ctype, body in suburb_content.items():
            content_statements.append(build_content_upsert("suburb", suburb_id, ctype, body, "gemini-2.5-flash"))
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

    # ── Recompute business_count ────────────────────────────────────────
    d1_execute(account_id, database_id,
               "; ".join(build_count_recompute_statements()) + ";",
               api_token)

    return {
        "summary": (f"Uploaded {len(records)} businesses to D1 database {database_id} "
                    f"(states: {len(states_seen)}, regions: {len(regions_seen)}, "
                    f"suburbs: {len(suburbs_seen)})"),
        "counts": {
            "records": len(records),
            "states": len(states_seen),
            "regions": len(regions_seen),
            "suburbs": len(suburbs_seen),
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
