import glob
import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from flask import current_app, request, session
from flask_login import current_user

from app.db.models import School, db
from app.services import plotly_charts
from app.services.chart_prefs import ChartPrefs
from app.services.pitch_filters import PitchFilters


def get_active_school_id() -> int:
    """current_user's own school_id, unless they're a master currently acting as another school."""
    if current_user.role == 'master':
        acting_id = session.get('master_school_id')
        if acting_id and db.session.get(School, acting_id):
            return int(acting_id)
    return current_user.school_id


def get_active_school() -> School:
    """The School current_user is currently scoped to (see get_active_school_id)."""
    school = db.session.get(School, get_active_school_id())
    assert school is not None
    return school


def flash_toast(message: str, type: str = 'info') -> None:
    """Queue a toast notification, shown on the next page render then cleared."""
    toasts = session.get('_toasts', [])
    toasts.append({'message': message, 'type': type})
    session['_toasts'] = toasts


def get_school_directories() -> tuple[str, str]:
    """Return (temp_dir, reports_dir) for the current user's school, creating them if needed."""
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")

    storage = current_app.config['STORAGE']

    school_temp_dir = os.path.join(storage, 'schools', str(current_user.school_id), 'temp')
    school_output_dir = os.path.join(storage, 'schools', str(current_user.school_id), 'reports')

    os.makedirs(school_temp_dir, exist_ok=True)
    os.makedirs(school_output_dir, exist_ok=True)

    return school_temp_dir, school_output_dir


def get_school_games_directory() -> str:
    """Return the archived-games dir for the current user's school, creating it if needed."""
    if not current_user.is_authenticated:
        raise Exception("User not authenticated")

    return get_games_directory(current_user.school_id)


def get_games_directory(school_id: int) -> str:
    """Return the archived-games dir for an explicit school id, creating it if needed."""
    games_dir = os.path.join(current_app.config['STORAGE'], 'schools', str(school_id), 'games')
    os.makedirs(games_dir, exist_ok=True)
    return games_dir


# -- report pages: filters, chart options, on-demand PDF exports ------------------------------

def default_chart_prefs() -> dict[str, str]:
    """The account's saved defaults for the page's scatter/heatmap and color-by toggles."""
    return {
        'view': 'scatter' if current_user.chart_style == 'pitch_point' else 'heatmap',
        'color_by': current_user.chart_color_mode,
    }


def chart_prefs(
    params: dict[str, Any], allowed_colors: tuple[str, ...] = plotly_charts.COLOR_MODES,
    default_color: str | None = None,
) -> ChartPrefs:
    """
    Chart options from the request, falling back to the account's defaults.
    Raises ValueError. A page with its own meaningful color (the catcher page's framing value)
    passes allowed_colors and the default_color it wants regardless of the account setting.
    """
    merged: dict[str, Any] = dict(default_chart_prefs())
    if default_color is not None:
        merged['color_by'] = default_color
    merged.update({k: params[k] for k in ('view', 'color_by') if k in params})
    return ChartPrefs.from_request(merged, show_arrows=current_user.show_break_arrows,
                                   allowed_colors=allowed_colors)


def charts_enabled() -> bool:
    return bool(current_user.school.is_active and current_user.school.tier >= 2)


def filters_from_args() -> PitchFilters | None:
    """Filters carried on a GET (pitch-by-pitch) link as a JSON `filters` query param.
    None when the param is malformed -- callers answer 400."""
    raw = request.args.get('filters')
    if not raw:
        return PitchFilters()
    try:
        return PitchFilters.from_request(json.loads(raw))
    except ValueError:  # json.JSONDecodeError is a ValueError
        return None


@contextmanager
def export_workdir(temp_folder: str, user_id: int, max_age_seconds: int = 3600) -> Iterator[str]:
    """
    A private working directory for one PDF export, removed afterwards.

    Each export works in its own directory, so two exports running at once (two cards'
    buttons clicked back to back) can't delete or overwrite each other's files, and a PDF still
    being streamed can't block the next one (Windows won't overwrite an open file). Directories
    a crashed request left behind are swept on the way in.
    """
    cutoff = time.time() - max_age_seconds
    for path in glob.glob(os.path.join(temp_folder, '*_export_*')):
        try:
            if os.path.isdir(path) and os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass

    work_dir = tempfile.mkdtemp(prefix=f'{user_id}_export_', dir=temp_folder)
    try:
        yield work_dir
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
