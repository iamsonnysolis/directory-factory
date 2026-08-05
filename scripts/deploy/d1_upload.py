"""D1 Upload Module (Phase 4)

Takes cleaned + enriched records from ``data/enriched_<project_id>.jsonl``
and uploads them into a per-directory Cloudflare D1 database via the
Cloudflare REST API.

Per the architecture decision in the plan doc, **one D1 database per
directory** — credentials are NOT in ``.env`` but passed at runtime
as params (D1_ACCOUNT_ID, D1_DATABASE_ID). The Cloudflare API token
comes from the environment (``CLOUDFLARE_API_TOKEN``).

This is a **new build** (not a port) — the old `toiletsnearme-data`
pipeline used Supabase, not D1.

Usage via the Phase 3 runner:
    python runner/run.py upload.d1 --project-id=5 \
        --params='{"d1_account_id": "...", "d1_database_id": "...", "site_name": "Test"}'

The script:
  1. Reads the D1 schema DDL and runs it (CREATE TABLE IF NOT EXISTS)
  2. Reads enriched JSONL records
  3. Batch upserts each record into businesses / business_features /
     business_hours / business_notes / enrichment_content tables
  4. Inserts/updates site_config branding row
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
_RUNNER_DIR = os.path.join(_PROJECT_ROOT, "runner")

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
) -> dict:
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
        The ``result`` array from the Cloudflare API response.

    Raises:
        requests.HTTPError on non-2xx responses.
    """
    token = api_token or os.getenv("CLOUDFLARE_API_TOKEN")
    if not token:
        raise RuntimeError(
            "CLOUDFLARE_API_TOKEN environment variable is not set. "
            "Set it to your Cloudflare API token (requires D1 write access)."
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
        raise RuntimeError(
            f"Cloudflare API error: {errors}"
        )
    # D1 execute returns result as either a dict (single statement) or
    # an array of dicts (multiple statements). Each statement result has
    # a "results" key for SELECT queries.
    return data.get("result", [])


def d1_execute_batch(
    account_id: str,
    database_id: str,
    statements: list[str],
    api_token: str | None = None,
    batch_size: int = 100,
) -> None:
    """Execute a list of SQL statements in batches.

    Cloudflare D1 has a limit on the number of statements per request
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


# ─── SQL value escaping (for batch inserts) ──────────────────────────────────

def sql_str(value) -> str:
    """Escape a Python string for safe inline SQL insertion in D1.

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


# ─── Record → SQL builders ───────────────────────────────────────────────────

def build_business_upsert_sql(record: dict) -> str:
    """Build an UPSERT (INSERT OR REPLACE) statement for a business record."""
    now = datetime.now(timezone.utc).isoformat()

    columns = [
        "slug", "name", "place_id", "primary_type", "business_status",
        "address", "locality", "state_code", "postal_code", "country",
        "lat", "lng", "phone", "website", "rating", "user_rating_count",
        "is_24_hours", "opening_hours_raw", "opening_hours_note",
        "quality_score", "ai_generated", "data_completeness",
        "updated_at",
    ]
    values = [
        sql_str(record.get("slug")),
        sql_str(record.get("name")),
        sql_str(record.get("place_id")),
        sql_str(record.get("primary_type")),
        sql_str(record.get("business_status")),
        sql_str(record.get("address")),
        sql_str(record.get("locality")),
        sql_str(record.get("state_code")),
        sql_str(record.get("postal_code")),
        sql_str(record.get("country")),
        sql_str(record.get("lat")),
        sql_str(record.get("lng")),
        sql_str(record.get("phone") or record.get("national_phone")),
        sql_str(record.get("website")),
        sql_str(record.get("rating")),
        sql_str(record.get("user_rating_count")),
        sql_str(record.get("is_24_hours")),
        sql_str(record.get("opening_hours_raw")),
        sql_str(record.get("opening_hours_note")),
        sql_str(record.get("quality_score")),
        sql_str(record.get("ai_generated")),
        sql_str(record.get("data_completeness_score")),
        sql_str(now),
    ]

    # UPSERT: if slug exists (updated_at), update the rest
    # D1 (SQLite-based) supports INSERT ... ON CONFLICT(col) DO UPDATE
    col_str = ", ".join(columns)
    val_str = ", ".join(values)
    updates = ", ".join(f"{c} = excluded.{c}" for c in columns if c != "slug")

    return (
        f"INSERT INTO businesses ({col_str}) VALUES ({val_str}) "
        f"ON CONFLICT(slug) DO UPDATE SET {updates}"
    )


def build_feature_inserts(business_id: int, features: list) -> list[str]:
    """Build INSERT statements for business_features."""
    statements = []
    for feat in features:
        if isinstance(feat, dict):
            key = feat.get("feature_key")
            source = feat.get("source", "unknown")
        else:
            key = feat
            source = "unknown"
        if key:
            statements.append(
                f"INSERT INTO business_features (business_id, feature_key, source) "
                f"VALUES ({business_id}, {sql_str(key)}, {sql_str(source)})"
            )
    return statements


def build_hours_inserts(business_id: int, hours_rows: list) -> list[str]:
    """Build INSERT statements for business_hours."""
    statements = []
    for row in hours_rows:
        cols = []
        vals = []
        for col in ["business_id", "day_of_week", "month_start", "month_end",
                     "open_mins", "close_mins", "is_24_hours", "is_daylight",
                     "is_unknown", "parse_status", "raw_source"]:
            cols.append(col)
            if col == "business_id":
                vals.append(str(business_id))
            else:
                vals.append(sql_str(row.get(col)))
        col_str = ", ".join(cols)
        val_str = ", ".join(vals)
        statements.append(f"INSERT INTO business_hours ({col_str}) VALUES ({val_str})")
    return statements


def build_note_inserts(business_id: int, notes: list) -> list[str]:
    """Build INSERT statements for business_notes."""
    statements = []
    for note in notes:
        if isinstance(note, dict):
            note_type = note.get("note_type", "general")
            text = note.get("note", "")
        else:
            note_type = "general"
            text = str(note)
        if text and text.strip():
            statements.append(
                f"INSERT INTO business_notes (business_id, note_type, note) "
                f"VALUES ({business_id}, {sql_str(note_type)}, {sql_str(text)})"
            )
    return statements


def build_enrichment_upsert_sql(business_id: int, enrichment: dict) -> str:
    """Build an UPSERT for AI-generated enrichment content."""
    cols = ["business_id"]
    vals = [str(business_id)]

    for col in ["description", "services", "specialties", "seo_keywords",
                "seo_meta_desc", "ai_model", "generated_at"]:
        cols.append(col)
        if col in ("services", "specialties", "seo_keywords"):
            vals.append(sql_json(enrichment.get(col)))
        else:
            vals.append(sql_str(enrichment.get(col)))

    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "business_id")

    return (
        f"INSERT INTO enrichment_content ({', '.join(cols)}) VALUES ({', '.join(vals)}) "
        f"ON CONFLICT(business_id) DO UPDATE SET {updates}"
    )


# ─── Main script logic ───────────────────────────────────────────────────────

def upload_project(project_id: int, params: dict) -> dict:
    """Upload enriched records to a per-directory D1 database.

    Args:
        project_id: The collection project ID (determines which
            ``data/enriched_<project_id>.jsonl`` file to read).
        params: Must include:
            - ``d1_account_id``: Cloudflare account ID
            - ``d1_database_id``: D1 database ID
            - ``site_name``: Brand name for the directory (stored in site_config)
            - ``d1_api_token``: (optional) Cloudflare API token. If not
              provided, falls back to ``CLOUDFLARE_API_TOKEN`` env var.
              Optional params:
            - ``dry_run``: If True, print SQL but don't execute (default: False)

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
            "counts": {"records": 0, "businesses": 0, "features": 0, "hours": 0},
        }

    # ── Load schema DDL ───────────────────────────────────────────────────────
    if not os.path.isfile(_SCHEMA_PATH):
        raise FileNotFoundError(f"D1 schema not found at {_SCHEMA_PATH}")

    with open(_SCHEMA_PATH) as f:
        schema_sql = f.read()

    # ── Build all SQL statements ─────────────────────────────────────────────
    all_statements = []

    # 1. Schema
    all_statements.append(schema_sql.rstrip(";"))

    # 2. site_config branding
    site_config_rows = [
        ("site_name", site_name),
        ("site_slug", params.get("site_slug", site_name.lower().replace(" ", "-"))),
        ("domain", params.get("domain", "")),
        ("created_at", datetime.now(timezone.utc).isoformat()),
    ]
    for key, value in site_config_rows:
        all_statements.append(
            f"INSERT OR REPLACE INTO site_config (key, value) "
            f"VALUES ({sql_str(key)}, {sql_str(value)})"
        )

    # 3. Business upserts (with RETURNING for business_id lookup)
    # D1 supports RETURNING in SQLite 1.2+ / Cloudflare D1
    # However, for batch simplicity, we do a two-phase approach:
    #   Phase 1: UPSERT all businesses
    #   Phase 2: Look up business_ids by slug
    #   Phase 3: UPSERT features, hours, notes, enrichment

    # Phase 1: UPSERT businesses
    business_slugs = []
    for record in records:
        all_statements.append(build_business_upsert_sql(record))
        business_slugs.append(record.get("slug") or record.get("name", ""))

    if dry_run:
        # In dry-run mode, skip the dependent inserts (no DB to look up IDs)
        total_features = sum(len(r.get("feature_keys", [])) for r in records)
        total_hours = sum(len(r.get("hours_rows", [])) for r in records)
        total_notes = sum(len(r.get("notes", [])) for r in records)
        total_enrichment = sum(1 for r in records if r.get("enrichment"))

        return {
            "summary": f"[DRY RUN] Would upload {len(records)} businesses "
                       f"({total_features} features, {total_hours} hours, "
                       f"{total_notes} notes, {total_enrichment} enrichment records) "
                       f"to D1 database {database_id}",
            "counts": {
                "records": len(records),
                "businesses": len(records),
                "features": total_features,
                "hours": total_hours,
                "notes": total_notes,
                "enrichment": total_enrichment,
                "dry_run": True,
                "statements": len(all_statements),
            },
        }

    # Phase 2: Execute schema + businesses + site_config first
    d1_execute(account_id, database_id,
               "; ".join(all_statements) + ";", api_token)

    # Phase 3: Look up business_ids by slug
    # Filter out None/empty slugs
    valid_slugs = [s for s in business_slugs if s]
    if valid_slugs:
        # Use sql_str for each slug value
        placeholders = ", ".join(sql_str(s) for s in valid_slugs)
        lookup_result = d1_execute(account_id, database_id,
            f"SELECT id, slug FROM businesses WHERE slug IN ({placeholders})",
            api_token)
    else:
        lookup_result = []

    # Build slug → id map from D1 response
    # D1 execute returns: result = [ {stmt_id: 0, success: true, results: [...]} ]
    id_map = {}
    results = lookup_result
    # Handle both single-result (dict) and multi-result (array) formats
    if isinstance(results, dict):
        results = [results]
    if results and isinstance(results, list):
        for row_set in results:
            if isinstance(row_set, dict) and "results" in row_set:
                for row in row_set["results"]:
                    if isinstance(row, dict) and "slug" in row:
                        id_map[row["slug"]] = row["id"]

    # Phase 4: Build + execute feature/hour/note/enrichment inserts
    dep_statements = []
    for record in records:
        slug = record.get("slug") or record.get("name", "")
        biz_id = id_map.get(slug)
        if biz_id is None:
            continue

        # Features
        features = record.get("feature_keys", record.get("features", []))
        if features:
            dep_statements.extend(build_feature_inserts(biz_id, features))

        # Hours rows
        hours_rows = record.get("hours_rows", [])
        if hours_rows:
            dep_statements.extend(build_hours_inserts(biz_id, hours_rows))

        # Notes
        notes = record.get("notes", [])
        if notes:
            dep_statements.extend(build_note_inserts(biz_id, notes))

        # Enrichment (AI-generated content)
        enrichment = record.get("enrichment")
        if enrichment:
            dep_statements.append(build_enrichment_upsert_sql(biz_id, enrichment))

    if dep_statements:
        d1_execute_batch(account_id, database_id, dep_statements, api_token)

    return {
        "summary": f"Uploaded {len(records)} businesses to D1 database {database_id} "
                   f"(features, hours, notes, enrichment included)",
        "counts": {
            "records": len(records),
            "businesses": len(records),
            "features": len([s for s in dep_statements if s.startswith("INSERT INTO business_features")]),
            "hours": len([s for s in dep_statements if s.startswith("INSERT INTO business_hours")]),
            "notes": len([s for s in dep_statements if s.startswith("INSERT INTO business_notes")]),
            "enrichment": len([s for s in dep_statements if s.startswith("INSERT INTO enrichment_content")]),
        },
    }


if __name__ == "__main__":
    @script_main
    def main(project_id: int, params: dict) -> dict:
        """D1 Upload — standard script entry point.

        Params (required):
            d1_account_id   — Cloudflare account ID
            d1_database_id  — D1 database ID for this directory
            site_name       — Brand name for the directory

        Params (optional):
            d1_api_token    — Cloudflare API token (default: env CLOUDFLARE_API_TOKEN)
            site_slug       — URL-safe slug for the site
            domain          — Custom domain (optional)
            dry_run         — If True, print what would be uploaded without executing
        """
        return upload_project(project_id, params)

    main()
