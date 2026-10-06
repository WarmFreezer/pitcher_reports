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

from app.services import chart_images, game_archive, hitter_card, hitter_report, pitch_filters
from app.services.branding_loader import BrandingLoader
from app.services.chart_prefs import ChartPrefs
from app.services.hitter_stats import HitterReportRequest
from app.services.pitch_filters import PitchFilters
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import (
    chart_prefs, charts_enabled, export_workdir, filters_from_args, flash_toast,
    get_school_directories, get_school_games_directory,
)

batting_bp = Blueprint('batting', __name__)

DATE_FORMAT = '%Y-%m-%d'
CHART_SLOTS = ('spray_left', 'spray_right')
MAX_EXPORT_BYTES = 40 * 1024 * 1024
MAX_EXPORT_HITTERS = 100


def _parse_date(value: str | None, fallback: str | None) -> str | None:
    """ISO date string, or the fallback when absent/malformed."""
    if not value:
        return fallback
    try:
        return datetime.strptime(value, DATE_FORMAT).date().isoformat()
    except ValueError:
        return fallback


def _display_date(iso_date: str | None) -> str:
    try:
        return datetime.strptime(iso_date or '', DATE_FORMAT).strftime('%m/%d/%Y')
    except (ValueError, TypeError):
        return iso_date or ''


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
    """What a batting request resolved to: the date window, the school's archive over it and
    the hitters it may ask about (every id must belong to this school's own archive)."""
    games_dir: str
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
        prefs = chart_prefs(dict(params))
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)

    target = params.get('target', 'own')
    allowed = {
        h['id']: h for h in game_archive.list_hitters(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
    }
    source = game_archive.load_range_cached(games_dir, start_date, end_date)
    if source.empty:
        return None, (jsonify({'error': 'No data in the selected date range.'}), 404)

    return _Selection(games_dir, start_date, end_date, target, source, allowed, filters, prefs), None


def _card_payload(sel: _Selection, batter_id: str, *, charts_only: bool = False) -> dict[str, Any]:
    """
    One hitter's JSON card for the current filters. Built in-process; current_user is read
    here, in the view layer, and never inside the services it calls.

    charts_only skips the stat tables -- a color-by or scatter/heatmap change redraws the
    charts but can't change a single number.
    """
    payload: dict[str, Any] = {'ok': True, 'hitter_id': str(batter_id)}
    if not charts_only:
        data = hitter_card.build_hitter_data(
            sel.source, batter_id, sel.filters,
            school_id=current_user.school_id, is_active=current_user.school.is_active)
        if data is None:
            payload['hitter_name'] = hitter_report.batter_name(sel.source, batter_id)
            payload['empty'] = True
            return payload
        payload.update(hitter_card.tables_payload(data))

        # Custom charts (tier 3) are Plotly figures the school's script builds; the page draws
        # them like any other chart. The slot name is how the export matches a rendered PNG back.
        custom = (hitter_report.custom_charts(data.source, batter_id, current_user.school_id)
                  if current_user.school.is_active else None)
        payload['custom_charts'] = [
            {'title': c.title, 'slot': f'custom_{i}', 'figure': c.figure} for i, c in enumerate(custom or [])]

    if charts_enabled():
        payload.update(hitter_card.charts_payload(
            hitter_card.build_hitter_charts(sel.source, batter_id, sel.filters, sel.prefs)))
    return payload


@batting_bp.route('/batting')
@login_required
def batting_page() -> ResponseReturnValue:
    return render_template('batting.html')


@batting_bp.route('/api/batting/hitters')
@login_required
def batting_hitters() -> ResponseReturnValue:
    """
    Hitters with batted balls inside the requested window, for the checkbox list.

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

    hitters = game_archive.list_hitters(
        games_dir,
        current_user.school.trackman_id,
        target,
        start_date=start_date,
        end_date=end_date,
        batted_only=True,
    )

    return jsonify({
        'hitters': hitters,
        'first_date': earliest,
        'last_date': latest,
        'game_count': len(game_archive.read_manifest(games_dir)),
    })


@batting_bp.route('/api/batting/report', methods=['POST'])
@login_required
def batting_report() -> ResponseReturnValue:
    """
    Build the preview cards for every selected hitter over the date range.

    Streams newline-delimited JSON: one 'meta' line (the pitch types and velocity range the
    filter bar is built from, plus the account's chart defaults), one 'report' line per hitter
    as their card finishes, then a 'done' summary. One hitter failing does not fail the batch:
    log it, toast it, keep going.

    No chart images or PDFs are produced here. Charts are Plotly figures drawn by the browser;
    the PDF is built on demand by POST /api/batting/export, with chart images the browser
    renders from those same figures.
    """
    params = request.get_json(silent=True) or {}
    batter_ids = params.get('batter_ids') or []
    if not batter_ids:
        return jsonify({'error': 'No hitters selected.'}), 400
    if not isinstance(batter_ids, list):
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None

    requested = [str(b) for b in batter_ids]
    if [b for b in requested if b not in sel.allowed]:
        return jsonify({'error': 'Hitter not found'}), 404

    charts_on = charts_enabled()
    ids = pd.to_numeric(sel.source['BatterId'], errors='coerce')
    wanted = {float(b) for b in requested if str(b).replace('.', '', 1).isdigit()}
    selected_rows = sel.source[ids.isin(wanted)]
    bounds = pitch_filters.velo_bounds(selected_rows)
    pitch_type_options = pitch_filters.pitch_type_options(selected_rows)
    total_games = int(selected_rows['GameDate'].nunique()) if 'GameDate' in selected_rows.columns else 0

    def stream() -> Generator[str, None, None]:
        yield json.dumps({
            'type': 'meta',
            'pitch_types': pitch_type_options,
            'velo_min': bounds[0] if bounds else None,
            'velo_max': bounds[1] if bounds else None,
            'defaults': {'view': sel.prefs.view, 'color_by': sel.prefs.color_by},
            'charts_enabled': charts_on,
        }) + '\n'

        reports_built = 0
        failed: list[str] = []
        for batter_id in requested:
            try:
                card = _card_payload(sel, batter_id)
            except Exception as e:
                failed.append(batter_id)
                print(f"Error processing hitter ID {batter_id}: {e}")
                flash_toast(f"Error processing hitter {batter_id}: {e}", type='error')
                yield json.dumps({'type': 'failed', 'batter_id': batter_id, 'error': str(e)}) + '\n'
                continue
            card['pitch_by_pitch_url'] = (
                f'/api/batting/pitch-by-pitch?batter_id={batter_id}&target={sel.target}'
                f'&start_date={sel.start_date}&end_date={sel.end_date}')
            reports_built += 1
            yield json.dumps({'type': 'report', **card}) + '\n'

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'date_range': sel.date_range,
            'start_date': sel.start_date,
            'end_date': sel.end_date,
            'games': total_games,
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@batting_bp.route('/api/batting/hitter', methods=['POST'])
@login_required
def batting_hitter() -> ResponseReturnValue:
    """
    Rebuild one hitter's card for new filters or chart options, so a slider release
    recomputes only the cards the user has open instead of the whole selection.

    charts_only=true redraws just the figures (color-by / scatter-heatmap changes).
    """
    params = request.get_json(silent=True) or {}
    batter_id = str(params.get('batter_id', ''))
    if not batter_id:
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None
    if batter_id not in sel.allowed:
        return jsonify({'error': 'Hitter not found'}), 404

    try:
        card = _card_payload(sel, batter_id, charts_only=params.get('charts_only') is True)
    except Exception:
        print(f"Error rebuilding hitter ID {batter_id}:")
        traceback.print_exc()
        return jsonify({'error': 'Could not rebuild that report.'}), 500
    return jsonify(card)


@batting_bp.route('/api/batting/export', methods=['POST'])
@login_required
def batting_export() -> ResponseReturnValue:
    """
    Build and stream the PDF for the requested hitters under the current filters.

    The numbers and tables are recomputed here from the school's own archive; the only
    client-supplied inputs are the filters (validated) and each hitter's chart images, which
    the browser rendered from the same Plotly figures it is displaying (see
    services/chart_images.py for how they are checked). One hitter streams back as their own
    PDF, several as one merged file.
    """
    if (request.content_length or 0) > MAX_EXPORT_BYTES:
        return jsonify({'error': 'Export is too large.'}), 413

    params = request.get_json(silent=True) or {}
    requested = params.get('hitters')
    if not isinstance(requested, list) or not requested or len(requested) > MAX_EXPORT_HITTERS:
        return jsonify({'error': 'No hitters selected.'}), 400
    try:
        batter_ids = [str(h['batter_id']) for h in requested]
        images_by_hitter = {str(h['batter_id']): h.get('images') or {} for h in requested}
        if not all(isinstance(imgs, dict) for imgs in images_by_hitter.values()):
            raise ValueError('Invalid images.')
    except (TypeError, ValueError, KeyError):
        return jsonify({'error': 'Invalid request.'}), 400

    sel, error = _selection(params)
    if error:
        return error
    assert sel is not None
    if [b for b in batter_ids if b not in sel.allowed]:
        return jsonify({'error': 'Hitter not found'}), 404

    school_temp_folder, _ = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)
    user_id = current_user.id
    use_images = charts_enabled()

    with export_workdir(school_temp_folder, user_id) as work_dir:
        gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)
        built: list[str] = []
        failed = 0
        for batter_id in batter_ids:
            data = hitter_card.build_hitter_data(
                sel.source, batter_id, sel.filters,
                school_id=current_user.school_id, is_active=current_user.school.is_active)
            if data is None:
                continue  # nothing passes the filters for this hitter

            # The school's own charts, in the order the page showed them: slot custom_0, custom_1, ...
            custom = (hitter_report.custom_charts(data.source, batter_id, current_user.school_id)
                      if current_user.school.is_active else None) or []
            custom_slots = [f'custom_{i}' for i in range(len(custom))]
            image_paths: dict[str, str | None] = {slot: None for slot in (*CHART_SLOTS, *custom_slots)}
            if use_images:
                for slot in image_paths:
                    posted = images_by_hitter[batter_id].get(slot)
                    if posted is None:
                        continue
                    path = os.path.join(work_dir, f'{user_id}_hitter_{batter_id}_{slot}.png')
                    try:
                        chart_images.save_chart_image(posted, path)
                    except chart_images.InvalidChartImage as e:
                        return jsonify({'error': str(e)}), 400
                    image_paths[slot] = path

            try:
                custom_chart_paths = [
                    (chart.title, chart_path) for chart, slot in zip(custom, custom_slots)
                    if (chart_path := image_paths[slot]) is not None] or None
                gen.generate_hitter_report(HitterReportRequest(
                    hitter_name=data.name,
                    hitter_id=str(batter_id),
                    date_range=sel.date_range,
                    team=sel.allowed[batter_id].get('team', ''),
                    games=data.games,
                    summary=data.summary,
                    discipline_table=data.discipline,
                    batted_ball_table=data.batted_ball,
                    spray_chart_left=image_paths['spray_left'],
                    spray_chart_right=image_paths['spray_right'],
                    custom_stats=data.custom_stats,
                    custom_hit_type_stats=data.custom_hit_type_stats,
                    custom_pitch_type_stats=data.custom_pitch_type_stats,
                    custom_chart_paths=custom_chart_paths,
                ), os.path.abspath(os.path.join(work_dir, f'{user_id}_hitter_{batter_id}_report.pdf')))
            except Exception:
                failed += 1
                print(f"Error generating PDF for hitter ID {batter_id}:")
                traceback.print_exc()
                continue
            built.append(batter_id)

        if not built:
            if failed:
                return jsonify({'error': 'Could not build the PDF.'}), 500
            return jsonify({'error': 'No pitches match the current filters.'}), 404

        if len(built) == 1:
            path = os.path.join(work_dir, f'{user_id}_hitter_{built[0]}_report.pdf')
            name = str(sel.allowed[built[0]]['name']).replace(', ', '_').replace(' ', '_')
            download_name = f'{name}_{sel.start_date}_to_{sel.end_date}.pdf'
        else:
            path = os.path.join(work_dir, f'{user_id}_merged_hitter_reports.pdf')
            if not merge_pdfs(user_id, work_dir, path, prefix='hitter'):
                return jsonify({'error': 'Could not merge the reports.'}), 500
            download_name = f'hitter_reports_{sel.start_date}_to_{sel.end_date}.pdf'

        with open(path, 'rb') as f:
            pdf_bytes = f.read()

    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name=download_name)


@batting_bp.route('/api/batting/pitch-by-pitch')
@login_required
def batting_pitch_by_pitch() -> ResponseReturnValue:
    """
    Build and stream a hitter's pitch-by-pitch PDF for the current filters.

    Built on request, not ahead of time: the at-bat panels are vector drawings now, so this is
    fast, and a pre-built file couldn't honor filters the user changes afterwards. Filters
    arrive as a JSON `filters` query param since this is a plain GET download.
    """
    batter_id = request.args.get('batter_id')
    if not batter_id:
        return jsonify({'error': 'No hitter selected.'}), 400

    filters = filters_from_args()
    if filters is None:
        return jsonify({'error': 'Invalid filters.'}), 400

    games_dir, start_date, end_date, error = _resolve_range(request.args)
    if error:
        return error
    assert games_dir is not None and start_date is not None and end_date is not None

    target = request.args.get('target', 'own')
    hitters = game_archive.list_hitters(
        games_dir, current_user.school.trackman_id, target,
        start_date=start_date, end_date=end_date,
    )
    hitter = next((h for h in hitters if h['id'] == str(batter_id)), None)
    if hitter is None:
        return jsonify({'error': 'Hitter not found'}), 404

    source = filters.apply(game_archive.load_range_cached(games_dir, start_date, end_date))
    date_range = f'{_display_date(start_date)} - {_display_date(end_date)}'
    pbp_report = hitter_report.build_pitch_by_pitch_report(source, batter_id, date_range)
    if pbp_report is None:
        return jsonify({'error': 'No pitches match the current filters.'}), 404

    school_temp_folder, _ = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)
    gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)
    with export_workdir(school_temp_folder, current_user.id) as work_dir:
        output_path = os.path.abspath(os.path.join(work_dir, f'hitter_{batter_id}_pitch_by_pitch.pdf'))
        gen.generate_hitter_pitch_by_pitch_report(pbp_report, output_path)
        with open(output_path, 'rb') as f:
            pdf_bytes = f.read()

    safe_name = hitter['name'].replace(', ', '_').replace(' ', '_')
    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
                     as_attachment=True, download_name=f'{safe_name}_pitch_by_pitch.pdf')
