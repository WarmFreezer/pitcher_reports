"""
Shared dynamic-import helper for school-owned tier-3 custom report scripts.

Both the pitcher and hitter pipelines let a school override/extend its report
with a Python file it owns (app/storage/schools/<school_id>/assets/<filename>).
This module owns the importlib boilerplate; report.py and hitter_report.py
each call load_custom_module() once per hook they need to invoke.
"""
import importlib.util
import os
from pathlib import Path
from typing import Any

STORAGE_SCHOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'storage', 'schools')


def custom_report_path(school_id: int, filename: str) -> Path:
    return Path(STORAGE_SCHOOLS) / str(school_id) / 'assets' / filename


def load_custom_module(school_id: int, filename: str) -> Any | None:
    """
    Dynamically imports a school's custom report script.

    Returns None if the file doesn't exist -- the tier is silently skipped, not
    an error. Raises if the file exists but fails to import; callers decide
    whether to catch that (report.py/hitter_report.py's collectors do, so one
    broken school script degrades to "no custom section" instead of failing
    the whole report).
    """
    path = custom_report_path(school_id, filename)
    if not path.exists():
        return None

    module_name = f"{path.stem}_{school_id}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
