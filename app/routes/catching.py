import io
import json
import os
import traceback
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file, Response, stream_with_context
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user

from app.services import catcher_card, catching_report, chart_images, game_archive, pitch_filters
from app.services.branding_loader import BrandingLoader
from app.services.catcher_stats import CatcherReportRequest
from app.services.chart_prefs import ChartPrefs
from app.services.pitch_filters import PitchFilters
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import (
    MAX_EXPORT_BYTES, parse_date as _parse_date, display_date as _display_date,
    chart_prefs, charts_enabled, export_workdir, flash_toast, get_school_directories,
    get_school_games_directory,
)

catching_bp = Blueprint('catching', __name__)

CHART_SLOTS = ('heat_map', 'pitch_location')
MAX_EXPORT_CATCHERS = 100


def _resolve_range(params: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, ResponseReturnValue | None]:
    """
    Clamp the requested window to what the archive actually holds.

    Returns (games_dir, start_date, end_date, error_response).
    """
    games_dir = get_school_games_directory()
    earliest, latest = game_archive.date_bounds(games_dir)
    if earliest is None:
        return None, None, None, (jsonify({
            'error': 'No games have been saved yet. Upload a game and choose Save Game first.'
        }), 400)

    start_date = _parse_date(params.get('start_date'), earliest)
    end_date = _parse_date(params.get('end_date'), latest)
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    return games_dir, start_date, end_date, None


@dataclass
class _Selection:
    """What a catching request resolved to: the date window, the school's archive over it and
    the catchers it may ask about (every id must belong to this school's own archive)."""
    start_date: str
    end_date: str
    target: str
    source: pd.DataFrame      # unfiltered, shared across requests -- read-only
    allowed: dict[str, dict[str, Any]]
    filters: PitchFilters
    prefs: ChartPrefs

    @property
    def date_range(self) -> str:
        return f'{_display_date(self.start_date)} - {_display_date(self.end_date)}'


def _selection(params: Mapping[str, Any]) -> tuple[_Selection | None, ResponseReturnValue | None]:
    games_dir, start_date, end_date, error = _resolve_range(params)
    if error:
        return None, error
    assert games_dir is not None and start_date is not None and end_date is not None

    try:
        filters = PitchFilters.from_request(params.get('filters'))
        # A framing chart is for framing value, so that is its color unless the user chose another
        # on the page -- the account's pitch-type/velocity default doesn't apply to it.
        prefs = chart_prefs(dict(params), allowed_colors=catcher_card.COLOR_MODES, default_color='framing')
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)

    target = params.get('target', 'own')
    allowed = {
        c['id']: c for c in game_archive.list_catchers(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
    }
    source = game_archive.load_range_cached(games_dir, start_date, end_date)
    if source.empty:
        return None, (jsonify({'error': 'No data in the selected date range.'}), 404)

    return _Selection(start_date, end_date, target, source, allowed, filters, prefs), None


def _card_payload(sel: _Selection, catcher_id: str, *, charts_only: bool = False) -> dict[str, Any]:
    """
    One catcher's JSON card for the current filters. Built in-process; current_user is read
    here, in the view layer, and never inside the services it calls.

    charts_only skips the framing table -- a color-by or scatter/heatmap change redraws the
    charts but can't change a single number.
    """
    payload: dict[str, Any] = {'ok': True, 'catcher_id': str(catcher_id)}

    if not charts_only:
        data = catcher_card.build_catcher_data(sel.source, catcher_id, sel.filters)
        if data is None:
            payload['catcher_name'] = catching_report.catcher_name(sel.source, catcher_id)
            payload['empty'] = True
            return payload
        payload.update(catcher_card.tables_payload(data))

    if charts_enabled():
        payload.update(catcher_card.charts_payload(
            catcher_card.build_catcher_charts(sel.source, catcher_id, sel.filters, sel.prefs)))
    return payload


@catching_bp.route('/catching')
@login_required
def catching_page() -> ResponseReturnValue:
    return render_template('catching.html')


@catching_bp.route('/api/catching/catchers')
@login_required
def catching_catchers() -> ResponseReturnValue:
    """
    Catchers with archived data inside the requested window, for the checkbox list.

    Called with no dates on first load purely to learn the archive's bounds, so
    an empty archive must answer cleanly rather than erroring.
    """
    games_dir = get_school_games_directory()
    target = request.args.get('target', 'own')
    earliest, latest = game_archive.date_bounds(games_dir)

    start_date = _parse_date(request.args.get('start_date'), earliest)
    end_date = _parse_date(request.args.get('end_date'), latest)
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    catchers = game_archive.list_catchers(
        games_dir,
        current_user.school.trackman_id,
        target,
        start_date=start_date,
        end_date=end_date,
    )

    return jsonify({
        'catchers': catchers,
        'first_date': earliest,
        'last_date': latest,
        'game_count': len(game_archive.read_manifest(games_dir)),
    })


@catching_bp.route('/api/catching/report', methods=['POST'])
@login_required
def catching_build_report() -> ResponseReturnValue:
    """
    Build the preview cards for every selected catcher over the date range.

    Streams newline-delimited JSON: one 'meta' line (the pitch types and velocity range the
    filter bar is built from, plus the chart defaults), one 'report' line per catcher as their
    card finishes, then a 'done' summary. No chart images or PDFs are produced here -- charts
    are Plotly figures drawn by the browser and the PDF is built on demand by POST
    /api/catching/export.
    """
    params = request.get_json(silent=True) or {}
    catcher_ids = params.get('catcher_ids') or []
    if not catcher_ids:
        return jsonify({'error': 'No catchers selected.'}), 400
    if not isinstance(catcher_ids, list):
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None

    requested = [str(c) for c in catcher_ids]
    if [c for c in requested if c not in sel.allowed]:
        return jsonify({'error': 'Catcher not found'}), 404

    charts_on = charts_enabled()
    ids = pd.to_numeric(sel.source['CatcherId'], errors='coerce') if 'CatcherId' in sel.source.columns else None
    wanted = {float(c) for c in requested if str(c).replace('.', '', 1).isdigit()}
    selected_rows = sel.source[ids.isin(wanted)] if ids is not None else sel.source.iloc[0:0]
    bounds = pitch_filters.velo_bounds(selected_rows) if not selected_rows.empty else None
    pitch_type_options = pitch_filters.pitch_type_options(selected_rows) if not selected_rows.empty else []

    def stream() -> Generator[str, None, None]:
        yield json.dumps({
            'type': 'meta',
            'pitch_types': pitch_type_options,
            'velo_min': bounds[0] if bounds else None,
            'velo_max': bounds[1] if bounds else None,
            'defaults': {'view': sel.prefs.view, 'color_by': sel.prefs.color_by},
            'color_modes': list(catcher_card.COLOR_MODES),
            'charts_enabled': charts_on,
        }) + '\n'

        reports_built = 0
        failed: list[str] = []
        for catcher_id in requested:
            try:
                card = _card_payload(sel, catcher_id)
            except Exception as e:
                failed.append(catcher_id)
                print(f"Error processing catcher ID {catcher_id}: {e}")
                flash_toast(f"Error processing catcher {catcher_id}: {e}", type='error')
                yield json.dumps({'type': 'failed', 'catcher_id': catcher_id, 'error': str(e)}) + '\n'
                continue
            reports_built += 1
            yield json.dumps({'type': 'report', **card}) + '\n'

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'date_range': sel.date_range,
            'start_date': sel.start_date,
            'end_date': sel.end_date,
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@catching_bp.route('/api/catching/catcher', methods=['POST'])
@login_required
def catching_catcher() -> ResponseReturnValue:
    """
    Rebuild one catcher's card for new filters or chart options, so a slider release
    recomputes only the cards the user has open instead of the whole selection.

    charts_only=true redraws just the figures (color-by / scatter-heatmap changes).
    """
    params = request.get_json(silent=True) or {}
    catcher_id = str(params.get('catcher_id', ''))
    if not catcher_id:
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None
    if catcher_id not in sel.allowed:
        return jsonify({'error': 'Catcher not found'}), 404

    try:
        card = _card_payload(sel, catcher_id, charts_only=params.get('charts_only') is True)
    except Exception:
        print(f"Error rebuilding catcher ID {catcher_id}:")
        traceback.print_exc()
        return jsonify({'error': 'Could not rebuild that report.'}), 500
    return jsonify(card)


@catching_bp.route('/api/catching/export', methods=['POST'])
@login_required
def catching_export() -> ResponseReturnValue:
    """
    Build and stream the PDF for the requested catchers under the current filters.

    The numbers and tables are recomputed here from the school's own archive; the only
    client-supplied inputs are the filters (validated) and each catcher's chart images, which
    the browser rendered from the same Plotly figures it is displaying (see
    services/chart_images.py for how they are checked). One catcher streams back as their own
    PDF, several as one merged file.
    """
    if (request.content_length or 0) > MAX_EXPORT_BYTES:
        return jsonify({'error': 'Export is too large.'}), 413

    params = request.get_json(silent=True) or {}
    requested = params.get('catchers')
    if not isinstance(requested, list) or not requested or len(requested) > MAX_EXPORT_CATCHERS:
        return jsonify({'error': 'No catchers selected.'}), 400
    try:
        catcher_ids = [str(c['catcher_id']) for c in requested]
        images_by_catcher = {str(c['catcher_id']): c.get('images') or {} for c in requested}
        if not all(isinstance(imgs, dict) for imgs in images_by_catcher.values()):
            raise ValueError('Invalid images.')
    except (TypeError, ValueError, KeyError):
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None
    if [c for c in catcher_ids if c not in sel.allowed]:
        return jsonify({'error': 'Catcher not found'}), 404

    school_temp_folder, _ = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)
    user_id = current_user.id
    use_images = charts_enabled()

    with export_workdir(school_temp_folder, user_id) as work_dir:
        gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)
        built: list[str] = []
        failed = 0
        for catcher_id in catcher_ids:
            data = catcher_card.build_catcher_data(sel.source, catcher_id, sel.filters)
            if data is None:
                continue  # nothing passes the filters for this catcher

            image_paths: dict[str, str | None] = {slot: None for slot in CHART_SLOTS}
            if use_images:
                for slot in CHART_SLOTS:
                    posted = images_by_catcher[catcher_id].get(slot)
                    if posted is None:
                        continue
                    path = os.path.join(work_dir, f'{user_id}_catcher_{catcher_id}_{slot}.png')
                    try:
                        chart_images.save_chart_image(posted, path)
                    except chart_images.InvalidChartImage as e:
                        return jsonify({'error': str(e)}), 400
                    image_paths[slot] = path

            try:
                gen.generate_catcher_report(CatcherReportRequest(
                    catcher_name=data.name,
                    catcher_id=str(catcher_id),
                    date_range=sel.date_range,
                    team=sel.allowed[catcher_id].get('team', ''),
                    games=sel.allowed[catcher_id].get('games', 0),
                    framing_table=data.framing_table,
                    heat_map=image_paths['heat_map'],
                    pitch_location_chart=image_paths['pitch_location'],
                ), os.path.abspath(os.path.join(work_dir, f'{user_id}_catcher_{catcher_id}_report.pdf')))
            except Exception:
                failed += 1
                print(f"Error generating PDF for catcher ID {catcher_id}:")
                traceback.print_exc()
                continue
            built.append(catcher_id)

        if not built:
            if failed:
                return jsonify({'error': 'Could not build the PDF.'}), 500
            return jsonify({'error': 'No pitches match the current filters.'}), 404

        if len(built) == 1:
            path = os.path.join(work_dir, f'{user_id}_catcher_{built[0]}_report.pdf')
            name = str(sel.allowed[built[0]]['name']).replace(', ', '_').replace(' ', '_')
            download_name = f'{name}_{sel.start_date}_to_{sel.end_date}.pdf'
        else:
            path = os.path.join(work_dir, f'{user_id}_merged_catcher_reports.pdf')
            if not merge_pdfs(user_id, work_dir, path, prefix='catcher'):
                return jsonify({'error': 'Could not merge the reports.'}), 500
            download_name = f'catcher_reports_{sel.start_date}_to_{sel.end_date}.pdf'

        with open(path, 'rb') as f:
            pdf_bytes = f.read()

    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name=download_name)
