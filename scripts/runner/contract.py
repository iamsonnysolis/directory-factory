"""Standardized script entry-point contract for the Directory Factory.

Every script in ``scripts/collection/``, ``scripts/cleaning_enrichment/``,
and ``scripts/deploy/`` uses the ``@script_main`` decorator so the runner
(``runner/run.py``) can invoke them uniformly via subprocess.

The decorated function must:
  - Accept ``project_id: int`` and ``params: dict``
  - Return a dict with at least a ``"summary"`` key (str), and optionally
    a ``"counts"`` key (dict)
  - Raise a normal Python exception on failure (do not catch-and-swallow)

The decorator wraps all of that: argparse, JSON parsing, result formatting,
and a clean JSON output on stdout that ``runner/run.py`` parses.
"""

import argparse
import json
import sys


def script_main(func):
    """Decorator for every standardized script entry point.

    ``func(project_id: int, params: dict) -> dict`` must return a dict with
    at least a ``"summary"`` key (str), and optionally a ``"counts"`` key (dict).
    Raise a normal Python exception on failure — this wrapper catches it,
    reports it, and exits non-zero. Do not catch-and-swallow errors inside
    ``func`` itself; let them raise.
    """
    def wrapper():
        parser = argparse.ArgumentParser()
        parser.add_argument("--project-id", type=int, required=True)
        parser.add_argument("--params", type=str, default="{}",
                             help="JSON string of extra parameters")
        args = parser.parse_args()
        params = json.loads(args.params)

        result = {"status": "success", "summary": None, "counts": {}, "error": None}
        try:
            output = func(args.project_id, params)
            result["summary"] = output.get("summary", "")
            result["counts"] = output.get("counts", {})
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)

        print(json.dumps(result))
        sys.exit(0 if result["status"] == "success" else 1)

    return wrapper
