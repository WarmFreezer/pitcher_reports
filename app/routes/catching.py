import os
import gc
import glob
import json
from collections.abc import Generator, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from flask import Blueprint, request, jsonify, render_template, send_file, Response, stream_with_context
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user

from app.services import game_archive, catching_report
from app.services.branding_loader import BrandingLoader
from app.services.catcher_stats import CatcherReportRequest
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import get_school_directories, get_school_games_directory, flash_toast

catching_bp = Blueprint('catching', __name__)

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


def _catcher_pdf_path(school_output_folder: str, catcher_id: str) -> str:
    return os.path.abspath(os.path.join(
        school_output_folder, f'{current_user.id}_catcher_{catcher_id}_report.pdf'))


def _build_one_catcher_report(task: dict[str, Any]) -> dict[str, Any]:
    """
    Build one catcher's charts + PDF and return the JSON-ready card data.

    Runs inside a worker process (see catching_report's ProcessPoolExecutor), so
    it must not touch current_user, db.session, or anything else that depends on
    Flask's app/request context -- every input it needs is already resolved into
    plain data on `task` by the caller, mirroring _build_one_hitter_report.
    """
    catcher_id = task['catcher_id']
    try:
        source = task['source']
        user_id = task['user_id']
        school_id = task['school_id']
        school_temp_folder = task['school_temp_folder']
        school_output_folder = task['school_output_folder']

        if task['is_active'] and task['include_charts']:
            for theme in ('light', 'dark'):
                catching_report.catcher_framing_heat_map(
                    source, user_id, school_temp_folder, catcher_id, theme=theme)
                catching_report.catcher_pitch_location_chart(
                    source, user_id, school_temp_folder, catcher_id, theme=theme)

        framing_table = catching_report.build_catcher_framing_table(source, catcher_id)
        catcher_name = catching_report.catcher_name(source, catcher_id)

        heat_map_path = os.path.join(school_temp_folder, f'{user_id}_catcher_{catcher_id}_heat_map_light.png')
        pitch_location_path = os.path.join(school_temp_folder, f'{user_id}_catcher_{catcher_id}_pitch_location_light.png')

        gen = PDF_Generator(school_id=school_id, branding=task['branding'], ink_mode=task['ink_mode'])
        gen.generate_catcher_report(CatcherReportRequest(
            catcher_name=catcher_name,
            catcher_id=str(catcher_id),
            date_range=task['date_range'],
            team=task['team'],
            games=task['games'],
            framing_table=framing_table,
            heat_map=heat_map_path if os.path.exists(heat_map_path) else None,
            pitch_location_chart=pitch_location_path if os.path.exists(pitch_location_path) else None,
        ), os.path.abspath(os.path.join(
            school_output_folder, f'{user_id}_catcher_{catcher_id}_report.pdf')))

        chart_base = f'/storage/schools/{school_id}/temp/{user_id}_catcher_{catcher_id}'
        return {
            'ok': True,
            'catcher_id': str(catcher_id),
            'catcher_name': catcher_name,
            'framing_table': framing_table.to_html('pitcher-data-table') if framing_table else None,
            'heat_map_url': f'{chart_base}_heat_map_light.png',
            'heat_map_dark_url': f'{chart_base}_heat_map_dark.png',
            'pitch_location_url': f'{chart_base}_pitch_location_light.png',
            'pitch_location_dark_url': f'{chart_base}_pitch_location_dark.png',
            'pdf_url': task['export_url'],
        }
    except Exception as e:
        return {'ok': False, 'catcher_id': str(catcher_id), 'error': str(e)}
    finally:
        gc.collect()


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
    Build reports for every selected catcher over the date range.

    Streams one NDJSON line per catcher as their report finishes -- built in
    parallel via a process pool -- matching the pitcher/hitter routes.
    """
    params = request.get_json(silent=True) or {}
    catcher_ids = params.get('catcher_ids') or []
    if not catcher_ids:
        return jsonify({'error': 'No catchers selected.'}), 400

    games_dir, start_date, end_date, error = _resolve_range(params)
    if error:
        return error
    assert games_dir is not None and start_date is not None and end_date is not None

    target = params.get('target', 'own')

    # Every id must belong to this school's archive before it is used for anything
    allowed = {
        c['id']: c for c in game_archive.list_catchers(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
    }
    requested = [str(c) for c in catcher_ids]
    unknown = [c for c in requested if c not in allowed]
    if unknown:
        return jsonify({'error': 'Catcher not found'}), 404

    source = game_archive.load_range(games_dir, start_date, end_date)
    if source.empty:
        return jsonify({'error': 'No data in the selected date range.'}), 404

    school_temp_folder, school_output_folder = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)

    # Clear this user's previous catcher output so a stale chart or PDF from an
    # earlier selection can never be served or swept into the merged file
    stale = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_catcher_*.png'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_catcher_*.pdf'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_merged_catcher_*.pdf'))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error deleting stale catcher output: {path} - {e}")

    date_range = f'{_display_date(start_date)} - {_display_date(end_date)}'
    school_id = current_user.school_id
    user_id = current_user.id
    is_active = current_user.school.is_active
    include_charts = current_user.school.tier >= 2
    ink_mode = current_user.ink_mode

    tasks = [{
        'catcher_id': catcher_id,
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
        'team': allowed[catcher_id].get('team', ''),
        'games': allowed[catcher_id].get('games', 0),
        'export_url': (f'/api/catching/export?catcher_id={catcher_id}&target={target}'
                        f'&start_date={start_date}&end_date={end_date}'),
    } for catcher_id in requested]

    def stream() -> Generator[str, None, None]:
        reports_built = 0
        failed: list[str] = []
        max_workers = min(len(tasks), os.cpu_count() or 2, 4)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_build_one_catcher_report, task) for task in tasks]
            for future in as_completed(futures):
                result = future.result()
                if result['ok']:
                    reports_built += 1
                    yield json.dumps({'type': 'report', **result}) + '\n'
                else:
                    failed.append(result['catcher_id'])
                    print(f"Error processing catcher ID {result['catcher_id']}: {result['error']}")
                    flash_toast(f"Error processing catcher {result['catcher_id']}: {result['error']}", type='error')
                    yield json.dumps({'type': 'failed', 'catcher_id': result['catcher_id'], 'error': result['error']}) + '\n'

        merged_url = None
        if reports_built:
            merged_path = os.path.join(
                school_output_folder, f'{user_id}_merged_catcher_reports.pdf')
            if merge_pdfs(user_id, school_output_folder, merged_path, prefix='catcher'):
                merged_url = (f'/api/catching/export?merged=1&target={target}'
                              f'&start_date={start_date}&end_date={end_date}')

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'merged_pdf_url': merged_url,
            'date_range': date_range,
            'start_date': start_date,
            'end_date': end_date,
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@catching_bp.route('/api/catching/export')
@login_required
def catching_export() -> ResponseReturnValue:
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
        path = os.path.join(school_output_folder, f'{current_user.id}_merged_catcher_reports.pdf')
        download_name = f'catcher_reports_{start_date}_to_{end_date}.pdf'
    else:
        catcher_id = request.args.get('catcher_id')
        if not catcher_id:
            return jsonify({'error': 'No catcher selected.'}), 400

        target = request.args.get('target', 'own')
        catchers = game_archive.list_catchers(
            games_dir, current_user.school.trackman_id, target,
            start_date=start_date, end_date=end_date,
        )
        catcher = next((c for c in catchers if c['id'] == str(catcher_id)), None)
        if catcher is None:
            return jsonify({'error': 'Catcher not found'}), 404

        path = _catcher_pdf_path(school_output_folder, catcher_id)
        safe_name = catcher['name'].replace(', ', '_').replace(' ', '_')
        download_name = f'{safe_name}_{start_date}_to_{end_date}.pdf'

    if not os.path.exists(path):
        return jsonify({'error': 'Report not found. Generate it first.'}), 404

    return send_file(path, mimetype='application/pdf',
                     as_attachment=True, download_name=download_name)
