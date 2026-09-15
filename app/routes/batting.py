import os
import gc
import glob
import json
from collections.abc import Generator, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Any

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file, Response, stream_with_context
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user

from app.services import game_archive, hitter_report
from app.services.branding_loader import BrandingLoader
from app.services.hitter_stats import HitterReportRequest
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import get_school_directories, get_school_games_directory, flash_toast

batting_bp = Blueprint('batting', __name__)

DATE_FORMAT = '%Y-%m-%d'


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


def _hitter_pdf_path(school_output_folder: str, batter_id: str) -> str:
    return os.path.abspath(os.path.join(
        school_output_folder, f'{current_user.id}_hitter_{batter_id}_report.pdf'))


def _build_one_hitter_report(task: dict[str, Any]) -> dict[str, Any]:
    """
    Build one hitter's charts + PDF and return the JSON-ready card data.

    Runs inside a worker process (see batting_report's ProcessPoolExecutor), so
    it must not touch current_user, db.session, or anything else that depends on
    Flask's app/request context -- every input it needs is already resolved into
    plain data on `task` by the caller. `source` is passed to every task rather
    than pre-filtered to this hitter's own rows, matching exactly what the old
    sequential loop passed to these same report functions.
    """
    batter_id = task['batter_id']
    try:
        source = task['source']
        user_id = task['user_id']
        school_id = task['school_id']
        school_temp_folder = task['school_temp_folder']
        school_output_folder = task['school_output_folder']

        rows = hitter_report.batter_rows(source, batter_id)
        if rows.empty:
            return {'ok': False, 'batter_id': batter_id, 'error': None}

        custom_stats = None
        custom_hit_type_stats = None
        custom_pitch_type_stats = None
        custom_chart_paths_by_theme: dict[str, list[tuple[str, str]]] = {}
        if task['is_active'] and task['include_charts']:
            for theme in ('light', 'dark'):
                hitter_report.hitter_spray_chart_by_pitcher_side(
                    source, user_id, school_temp_folder, batter_id, theme=theme)

        # Independent of include_charts -- gated only on whether the school has a
        # master-uploaded custom_hitter_report.py, so a lower-tier school can still
        # have custom reports/charts (see hitter_report.custom_stats_table)
        if task['is_active']:
            for theme in ('light', 'dark'):
                custom_chart_paths_by_theme[theme] = hitter_report.custom_charts(
                    source, batter_id, school_id, user_id, school_temp_folder, theme=theme) or []

            custom_stats = hitter_report.custom_stats_table(source, batter_id, school_id)
            custom_hit_type_stats = hitter_report.custom_hit_type_stats_table(source, batter_id, school_id)
            custom_pitch_type_stats = hitter_report.custom_pitch_type_stats_table(source, batter_id, school_id)

        summary = hitter_report.build_hitter_summary(source, batter_id)
        discipline = hitter_report.build_hitter_discipline_table(source, batter_id)
        batted_ball = hitter_report.build_batted_ball_table(source, batter_id)
        hitter_name = hitter_report.batter_name(source, batter_id)
        games = int(rows['GameDate'].nunique()) if 'GameDate' in rows.columns else 0

        def chart_path(side: str, theme: str) -> str | None:
            path = os.path.join(
                school_temp_folder,
                f'{user_id}_hitter_{batter_id}_spray_{side}_{theme}.png')
            return path if os.path.exists(path) else None

        gen = PDF_Generator(school_id=school_id, branding=task['branding'], ink_mode=task['ink_mode'])
        gen.generate_hitter_report(HitterReportRequest(
            hitter_name=hitter_name,
            hitter_id=str(batter_id),
            date_range=task['date_range'],
            team=task['team'],
            games=games,
            summary=summary,
            discipline_table=discipline,
            batted_ball_table=batted_ball,
            spray_chart_left=chart_path('left', 'light'),
            spray_chart_right=chart_path('right', 'light'),
            custom_stats=custom_stats,
            custom_hit_type_stats=custom_hit_type_stats,
            custom_pitch_type_stats=custom_pitch_type_stats,
            # A static PDF page has no theme toggle -- always the light render.
            custom_chart_paths=custom_chart_paths_by_theme.get('light'),
        ), os.path.abspath(os.path.join(
            school_output_folder, f'{user_id}_hitter_{batter_id}_report.pdf')))

        chart_base = f'/storage/schools/{school_id}/temp/{user_id}_hitter_{batter_id}_spray'
        return {
            'ok': True,
            'hitter_id': str(batter_id),
            'hitter_name': hitter_name,
            'games': games,
            'date_range': task['date_range'],
            'summary': summary,
            'discipline_table': discipline.to_html('pitcher-data-table'),
            'batted_ball_table': batted_ball.to_html('pitcher-data-table'),
            # Custom stats/charts (school's tier-3 custom_hitter_report.py, if
            # any) -- previously only reached the PDF, never the on-page preview.
            # Rendered as tiles on the page (see .summary-grid), matching the tile
            # grid the PDF shows for these via generate_stats_grid -- name/value
            # pairs, not tabular data, so a plain HTML table looked out of place.
            'custom_stats': {row.name: row.value for row in custom_stats.rows} if custom_stats else None,
            'custom_hit_type_stats_tables': [
                {'title': t.title or 'Custom Hit Type Stats', 'html': t.to_html('custom-stats-table')}
                for t in custom_hit_type_stats
            ] if custom_hit_type_stats else None,
            'custom_pitch_type_stats_tables': [
                {'title': t.title or 'Custom Pitch Type Stats', 'html': t.to_html('custom-stats-table')}
                for t in custom_pitch_type_stats
            ] if custom_pitch_type_stats else None,
            # Paired light/dark by title (same script call, just a different theme
            # param -- see custom_chart_paths_by_theme above) so the page can swap
            # them on theme toggle the same way every other chart here does.
            'custom_chart_urls': [
                {
                    'title': title,
                    'url': f'/storage/schools/{school_id}/temp/{os.path.basename(light_path)}',
                    'dark_url': f'/storage/schools/{school_id}/temp/{os.path.basename(dark_path)}',
                }
                for (title, light_path), (_, dark_path) in zip(
                    custom_chart_paths_by_theme.get('light', []),
                    custom_chart_paths_by_theme.get('dark', []),
                )
            ] or None,
            'spray_left_url': f'{chart_base}_left_light.png',
            'spray_right_url': f'{chart_base}_right_light.png',
            'spray_left_dark_url': f'{chart_base}_left_dark.png',
            'spray_right_dark_url': f'{chart_base}_right_dark.png',
            'pdf_url': task['export_url'],
            'pitch_by_pitch_url': task['pitch_by_pitch_url'],
        }
    except Exception as e:
        return {'ok': False, 'batter_id': batter_id, 'error': str(e)}
    finally:
        gc.collect()


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
    Build reports for every selected hitter over the date range.

    Charts are written in both themes so the page can swap them on theme toggle,
    and each hitter's PDF is written here rather than on export -- the expensive
    part is the chart render, which has already happened by that point.

    Streams one NDJSON line per hitter as their report finishes -- built in
    parallel via a process pool -- instead of waiting for the whole selection and
    returning one JSON blob, matching the pitcher route. One hitter failing does
    not fail the batch: log it, toast it, keep going.
    """
    params = request.get_json(silent=True) or {}
    batter_ids = params.get('batter_ids') or []
    if not batter_ids:
        return jsonify({'error': 'No hitters selected.'}), 400

    games_dir, start_date, end_date, error = _resolve_range(params)
    if error:
        return error
    assert games_dir is not None and start_date is not None and end_date is not None

    target = params.get('target', 'own')

    # Every id must belong to this school's archive before it is used for anything
    allowed = {
        h['id']: h for h in game_archive.list_hitters(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
    }
    requested = [str(b) for b in batter_ids]
    unknown = [b for b in requested if b not in allowed]
    if unknown:
        return jsonify({'error': 'Hitter not found'}), 404

    source = game_archive.load_range(games_dir, start_date, end_date)
    if source.empty:
        return jsonify({'error': 'No data in the selected date range.'}), 404

    school_temp_folder, school_output_folder = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)

    # Clear this user's previous hitter output so a stale chart or PDF from an
    # earlier selection can never be served or swept into the merged file
    stale = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_hitter_*_spray_*.png'))
    stale += glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_hitter_*_custom_*.png'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_hitter_*.pdf'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_merged_hitter_*.pdf'))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error deleting stale hitter output: {path} - {e}")

    date_range = f'{_display_date(start_date)} - {_display_date(end_date)}'
    school_id = current_user.school_id
    user_id = current_user.id
    is_active = current_user.school.is_active
    include_charts = current_user.school.tier >= 2
    ink_mode = current_user.ink_mode

    tasks = [{
        'batter_id': batter_id,
        'source': source,
        'user_id': user_id,
        'school_id': school_id,
        'school_temp_folder': school_temp_folder,
        'school_output_folder': school_output_folder,
        'is_active': is_active,
        'include_charts': include_charts,
        'branding': branding,
        'ink_mode': ink_mode,
        'date_range': date_range,
        'team': allowed[batter_id].get('team', ''),
        'export_url': (f'/api/batting/export?batter_id={batter_id}&target={target}'
                        f'&start_date={start_date}&end_date={end_date}'),
        'pitch_by_pitch_url': (f'/api/batting/pitch-by-pitch?batter_id={batter_id}&target={target}'
                                f'&start_date={start_date}&end_date={end_date}'),
    } for batter_id in requested]

    def stream() -> Generator[str, None, None]:
        reports_built = 0
        failed: list[str] = []
        max_workers = min(len(tasks), os.cpu_count() or 2, 4)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_build_one_hitter_report, task) for task in tasks]
            for future in as_completed(futures):
                result = future.result()
                if result['ok']:
                    reports_built += 1
                    yield json.dumps({'type': 'report', **result}) + '\n'
                else:
                    failed.append(result['batter_id'])
                    if result['error']:
                        print(f"Error processing hitter ID {result['batter_id']}: {result['error']}")
                        flash_toast(f"Error processing hitter {result['batter_id']}: {result['error']}", type='error')
                    yield json.dumps({'type': 'failed', 'batter_id': result['batter_id'], 'error': result['error']}) + '\n'

        merged_url = None
        if reports_built:
            merged_path = os.path.join(
                school_output_folder, f'{user_id}_merged_hitter_reports.pdf')
            if merge_pdfs(user_id, school_output_folder, merged_path, prefix='hitter'):
                merged_url = (f'/api/batting/export?merged=1&target={target}'
                              f'&start_date={start_date}&end_date={end_date}')

        # Distinct games across the whole selection. Ids are compared numerically --
        # astype(str) would yield '500.0' whenever pandas reads BatterId as float.
        total_games = 0
        if 'GameDate' in source.columns and requested:
            ids = pd.to_numeric(source['BatterId'], errors='coerce')
            targets = {float(b) for b in requested if str(b).replace('.', '', 1).isdigit()}
            total_games = int(source[ids.isin(targets)]['GameDate'].nunique())

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'merged_pdf_url': merged_url,
            'date_range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'games': total_games,
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@batting_bp.route('/api/batting/export')
@login_required
def batting_export() -> ResponseReturnValue:
    """
    Stream a PDF built by the preceding /report call.

    Streams through send_file rather than handing back a /storage URL: those
    static routes are unauthenticated, and an export is worth keeping behind
    the login. Pass merged=1 for the combined file.
    """
    games_dir, start_date, end_date, error = _resolve_range(request.args)
    if error:
        return error
    assert games_dir is not None

    _, school_output_folder = get_school_directories()

    if request.args.get('merged'):
        path = os.path.join(school_output_folder, f'{current_user.id}_merged_hitter_reports.pdf')
        download_name = f'hitter_reports_{start_date}_to_{end_date}.pdf'
    else:
        batter_id = request.args.get('batter_id')
        if not batter_id:
            return jsonify({'error': 'No hitter selected.'}), 400

        target = request.args.get('target', 'own')
        hitters = game_archive.list_hitters(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
        hitter = next((h for h in hitters if h['id'] == str(batter_id)), None)
        if hitter is None:
            return jsonify({'error': 'Hitter not found'}), 404

        path = _hitter_pdf_path(school_output_folder, batter_id)
        safe_name = hitter['name'].replace(', ', '_').replace(' ', '_')
        download_name = f'{safe_name}_{start_date}_to_{end_date}.pdf'

    if not os.path.exists(path):
        return jsonify({'error': 'Report not found. Generate it first.'}), 404

    return send_file(path, mimetype='application/pdf',
                     as_attachment=True, download_name=download_name)


@batting_bp.route('/api/batting/pitch-by-pitch')
@login_required
def batting_pitch_by_pitch() -> ResponseReturnValue:
    """
    Build and stream a simplified pitch-by-pitch PDF for one hitter: a header
    (hitter/date range) followed by every at-bat's pitches, numbered in the order
    thrown, with the pitcher faced shown per at-bat rather than a batter.
    """
    batter_id = request.args.get('batter_id')
    if not batter_id:
        return jsonify({'error': 'No hitter selected.'}), 400

    games_dir, start_date, end_date, error = _resolve_range(request.args)
    if error:
        return error
    assert games_dir is not None and start_date is not None and end_date is not None

    source = game_archive.load_range(games_dir, start_date, end_date)
    if source.empty:
        return jsonify({'error': 'No data in the selected date range.'}), 404

    date_range = f'{_display_date(start_date)} - {_display_date(end_date)}'
    pbp_report = hitter_report.build_pitch_by_pitch_report(source, batter_id, date_range)
    if pbp_report is None:
        return jsonify({'error': 'No data for that hitter in the selected range.'}), 404

    branding = BrandingLoader.get_branding(current_user.school_id)
    gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)

    _, school_output_folder = get_school_directories()
    output_path = os.path.abspath(os.path.join(
        school_output_folder, f'{current_user.id}_hitter_{batter_id}_pitch_by_pitch.pdf'))
    gen.generate_hitter_pitch_by_pitch_report(pbp_report, output_path)

    safe_name = pbp_report.hitter_name.replace(', ', '_').replace(' ', '_') or f'hitter_{batter_id}'
    return send_file(output_path, mimetype='application/pdf',
                      as_attachment=True, download_name=f'{safe_name}_pitch_by_pitch.pdf')
