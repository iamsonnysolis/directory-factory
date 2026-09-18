"""Jinja2 environment setup and template filter/global registration.

All globals and filters that templates call are registered here in one place,
so the move from app.py is verifiable at a glance.  Module-level execution
guarantees registration happens before any route renders a template.
"""

from jinja2 import Environment, FileSystemLoader

from .config import DASHBOARD_DIR


def _create_environment():
    """Create and return the configured Jinja2 Environment."""
    templates = Environment(
        loader=FileSystemLoader(str(DASHBOARD_DIR / "templates")),
        autoescape=True,
    )
    return templates


# Single shared environment instance — module-level so registration is
# complete at import time, before the FastAPI app starts serving.
_templates = _create_environment()

# Built-in available inside templates without explicit passing
_templates.globals["enumerate"] = enumerate


def format_int(value):
    """Format an integer with thousands separators (e.g. 42 -> '42', 1234 -> '1,234')."""
    if value is None:
        return "0"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


_templates.filters["format_int"] = format_int

# ─── Jinja2 helper functions for templates ───────────────────────────────────

# These functions are defined in services.pipeline / services.directories
# and imported here so the globals dict can reference them.  Importing at
# module level is fine — services do not import jinja_setup back.

from .services.pipeline import (  # noqa: E402
    _stage_state,
    _stage_pill_label,
    _done_count,
    _pipeline_stages_for_detail,
    _pipeline_stages_label,
    _pipeline_icon_for,
    _stage_short_label,
    _stage_progress_pct,
    _stage_last_run,
    _last_traceback_line,
)

# Register every global — this is the critical block.  If any of these
# lines is missing, the template that calls the corresponding function
# will raise silently at render time.
_templates.globals["_stage_state"] = _stage_state
_templates.globals["_stage_pill_label"] = _stage_pill_label
_templates.globals["_done_count"] = _done_count
_templates.globals["_pipeline_stages_for_detail"] = _pipeline_stages_for_detail
_templates.globals["_pipeline_stages_label"] = _pipeline_stages_label
_templates.globals["_pipeline_icon_for"] = _pipeline_icon_for
_templates.globals["_stage_short_label"] = _stage_short_label
_templates.globals["_stage_progress_pct"] = _stage_progress_pct
_templates.globals["_stage_last_run"] = _stage_last_run
_templates.globals["_last_traceback_line"] = _last_traceback_line
