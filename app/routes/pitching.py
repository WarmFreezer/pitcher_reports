import os
import gc
import glob
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Generator
from urllib.parse import quote

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file, Response, stream_with_context
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.db import models
from app.services import game_archive, report
from app.services.branding_loader import BrandingLoader
from app.services.pitch_stats import PitcherReportRequest
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import get_school_directories, get_school_games_directory, flash_toast

pitching_bp = Blueprint('pitching', __name__)

DATE_FORMAT = '%Y-%m-%d'


def _parse_date(value: str | None, fallback: str | None = None) -> str | None:
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


def calculate_age(birthdate: date | None) -> int | None:
    if not birthdate:
        return None
    today = datetime.today()
    return today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))


def _selected_games(params: dict[str, Any]) -> tuple[str | None, list[dict[str, Any]] | None, ResponseReturnValue | None]:
    """
    Resolve the requested content hashes against this school's own archive.

    Returns (games_dir, [game rows], error_response). Anything not in this
    school's archive resolves to nothing and comes back 404 rather than 403, so
    a probe cannot distinguish "not yours" from "does not exist".
    """
    hashes = params.get('content_hashes') or []
    if not hashes:
        return None, None, (jsonify({'error': 'No games selected.'}), 400)

    games_dir = get_school_games_directory()
    available = {
        g['content_hash']: g
        for g in game_archive.list_games(games_dir, current_user.school.trackman_id)
    }

    selected = [available[h] for h in hashes if h in available]
    if len(selected) != len(hashes):
        return None, None, (jsonify({'error': 'Game not found'}), 404)

    return games_dir, selected, None


def _pitcher_meta(pitcher_id: int) -> tuple[str, str, int | None]:
    """Height/weight/age for the PDF header, blank when the roster has no entry."""
    pitcher = models.Pitcher.query.filter_by(
        trackman_id=str(pitcher_id), school_id=current_user.school_id).first()
    if pitcher is None:
        return '', '', None
    return (
        pitcher.height or '',
        pitcher.weight or '',
        calculate_age(pitcher.birthdate) if pitcher.birthdate else None,
    )


def _build_one_pitcher_report(task: dict[str, Any]) -> dict[str, Any]:
    """
    Build one pitcher's charts + PDF and return the JSON-ready card data.

    Runs inside a worker process (see pitching_report's ProcessPoolExecutor), so
    it must not touch current_user, db.session, or anything else that depends on
    Flask's app/request context -- every input it needs is already resolved into
    plain data on `task` by the caller. `source` (the full multi-pitcher/both-teams
    DataFrame) is passed to every task rather than pre-filtered to this pitcher's
    own rows, matching exactly what the old sequential loop passed to these same
    report functions -- filtering it down would shrink the per-task pickle cost,
    but risks changing behavior in a function that hasn't been audited for
    whether it relies on rows outside its own pitcher_id (e.g. build_table reads
    source['BatterTeam'].iloc[0] rather than a pitcher-scoped value).
    """
    pitcher_id = task['pitcher_id']
    try:
        source = task['source']
        user_id = task['user_id']
        school_id = task['school_id']
        school_temp_folder = task['school_temp_folder']
        school_output_folder = task['school_output_folder']

        arm_angle = None
        custom_stats = None
        custom_pitch_type_stats = None
        if task['is_active'] and task['include_charts']:
            for theme in ('light', 'dark'):
                report.pitch_heat_map_by_batter_side(
                    source, user_id, school_temp_folder, pitcher_id, 0.75, theme=theme,
                    chart_style=task['chart_style'])
                result = report.pitch_break_map(
                    source, user_id, school_temp_folder, pitcher_id, 0.75, theme=theme)
                if arm_angle is None and result is not None:
                    arm_angle = result

        # Independent of include_charts -- gated only on whether the school has a
        # master-uploaded custom_pitcher_report.py, so a lower-tier school can still
        # have custom reports (see report.custom_stats_table)
        if task['is_active']:
            custom_stats = report.custom_stats_table(source, pitcher_id, school_id)
            custom_pitch_type_stats = report.custom_pitch_type_stats_table(source, pitcher_id, school_id)

        game_report = report.build_table(source, pitcher_id)
        if game_report is None:
            raise ValueError(f'Failed to build table data for pitcher ID {pitcher_id}')

        usage_sides = report.usage_table(source, pitcher_id)
        if usage_sides is None:
            raise ValueError(f'Failed to build pitch usage table for pitcher ID {pitcher_id}')

        height, weight, age = task['pitcher_meta']

        gen = PDF_Generator(school_id=school_id, branding=task['branding'], ink_mode=task['ink_mode'])
        gen.generate_pitcher_report(PitcherReportRequest(
            pitcher_name=game_report.header.pitcher_name,
            pitcher_id=str(pitcher_id),
            date=task['date_range'],
            home_team=task['home_team'],
            away_team=task['opponent_label'],
            matchup_separator=task['matchup_separator'],
            pitcher_height=height,
            pitcher_weight=weight,
            pitcher_age=age,
            pitch_stats=game_report.stats,
            pitch_usage_left=usage_sides.left,
            pitch_usage_right=usage_sides.right,
            pitch_heat_map_left=os.path.join(school_temp_folder, f'{user_id}_pitcher_{pitcher_id}_heat_map_left_light.png'),
            pitch_heat_map_right=os.path.join(school_temp_folder, f'{user_id}_pitcher_{pitcher_id}_heat_map_right_light.png'),
            pitch_break_map=os.path.join(school_temp_folder, f'{user_id}_pitcher_{pitcher_id}_break_map_light.png'),
            custom_stats=custom_stats,
            custom_pitch_type_stats=custom_pitch_type_stats,
        ), os.path.abspath(os.path.join(
            school_output_folder, f'{user_id}_pitcher_{pitcher_id}_report.pdf')))

        chart_base = f'/storage/schools/{school_id}/temp/{user_id}_pitcher_{pitcher_id}'
        return {
            'ok': True,
            'pitcher_id': str(pitcher_id),
            'pitcher_name': game_report.header.pitcher_name,
            'pitcher_table': game_report.stats.to_html('pitcher-data-table'),
            'left_usage_table': usage_sides.left.to_html('pitch-usage-table'),
            'right_usage_table': usage_sides.right.to_html('pitch-usage-table'),
            # Custom stats (school's tier-3 custom_pitcher_report.py, if any) --
            # previously only reached the PDF, never the on-page preview.
            # Rendered as tiles on the page (see .summary-grid), matching the tile
            # grid the PDF shows for these via generate_stats_grid -- name/value
            # pairs, not tabular data, so a plain HTML table looked out of place.
            'custom_stats': {row.name: row.value for row in custom_stats.rows} if custom_stats else None,
            'custom_pitch_type_stats_tables': [
                {'title': t.title or 'Custom Pitch Type Stats', 'html': t.to_html('custom-stats-table')}
                for t in custom_pitch_type_stats
            ] if custom_pitch_type_stats else None,
            'heatmap_left_url': f'{chart_base}_heat_map_left_light.png',
            'heatmap_right_url': f'{chart_base}_heat_map_right_light.png',
            'heatmap_left_dark_url': f'{chart_base}_heat_map_left_dark.png',
            'heatmap_right_dark_url': f'{chart_base}_heat_map_right_dark.png',
            'breakmap_url': f'{chart_base}_break_map_light.png',
            'breakmap_dark_url': f'{chart_base}_break_map_dark.png',
            'arm_angle': f'{arm_angle:.1f}°' if arm_angle is not None else '',
            'pdf_url': f'/api/pitching/export?pitcher_id={pitcher_id}',
            'pitch_by_pitch_url': f'/api/pitching/pitch-by-pitch?pitcher_id={pitcher_id}&target={task["target"]}&{task["hash_qs"]}',
        }
    except Exception as e:
        return {'ok': False, 'pitcher_id': str(pitcher_id), 'error': str(e)}
    finally:
        gc.collect()


@pitching_bp.route('/pitching')
@login_required
def pitching_page() -> ResponseReturnValue:
    return render_template('pitching.html')


@pitching_bp.route('/api/pitching/games')
@login_required
def pitching_games() -> ResponseReturnValue:
    """
    Archived games for the checkbox list, narrowed by the date range.

    Called with no dates on first load to learn the archive's bounds, so an empty
    archive has to answer cleanly rather than erroring.
    """
    games_dir = get_school_games_directory()
    earliest, latest = game_archive.date_bounds(games_dir)

    start_date = _parse_date(request.args.get('start_date'), earliest)
    end_date = _parse_date(request.args.get('end_date'), latest)
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    games = game_archive.list_games(
        games_dir,
        current_user.school.trackman_id,
        start_date=start_date,
        end_date=end_date,
        include_practice=request.args.get('include_practice', '1') != '0',
    )

    return jsonify({
        'games': games,
        'first_date': earliest,
        'last_date': latest,
        'game_count': len(game_archive.read_manifest(games_dir)),
    })


@pitching_bp.route('/api/pitching/report', methods=['POST'])
@login_required
def pitching_report() -> ResponseReturnValue:
    """
    Build reports for every pitcher in the selected games.

    A selection may span several outings -- a weekend series against one opponent
    is the motivating case -- so each pitcher gets one report aggregating their
    work across everything selected, and the header carries the date range rather
    than a single game date.

    Streams one NDJSON line per pitcher as their report finishes -- built in
    parallel via a process pool -- instead of waiting for the whole staff and
    returning one JSON blob, so the page can show results as they arrive. One
    pitcher failing does not fail the batch, matching the loop this replaced in
    upload.py: log it, toast it, keep going.
    """
    params = request.get_json(silent=True) or {}
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    target = params.get('target', 'own')
    trackman_id = current_user.school.trackman_id

    source = game_archive.load_games(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404

    # The Own/Opponent switch filters which arms get reports, not which games
    # were selected -- both teams pitched in every game on the list.
    if target == 'opponent':
        matching = source[source['PitcherTeam'] != trackman_id]
    else:
        matching = source[source['PitcherTeam'] == trackman_id]

    if matching.empty:
        side = 'opponent' if target == 'opponent' else 'your team'
        return jsonify({'error': f'No pitching data found for {side} in the selected games.'}), 404

    school_temp_folder, school_output_folder = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)

    # Clear this user's previous pitcher output so a stale chart or PDF from an
    # earlier selection cannot be served or swept into the merged file
    stale = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_pitcher_*.png'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_pitcher_*.pdf'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_merged_pitcher_*.pdf'))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error deleting stale pitcher output: {path} - {e}")

    dates = sorted(g['date'] for g in selected)
    date_range = (_display_date(dates[0]) if dates[0] == dates[-1]
                  else f'{_display_date(dates[0])} - {_display_date(dates[-1])}')
    opponents = sorted({g['opponent'] for g in selected})
    opponent_label = opponents[0] if len(opponents) == 1 else f'{len(opponents)} opponents'
    # A true single selected game reads correctly as "us @ opponent"; anything
    # aggregated across games isn't a real single-game home/away pair.
    matchup_separator = '@' if len(selected) == 1 else 'vs'

    school_id = current_user.school_id
    user_id = current_user.id
    # Resolved here, in the request/app-context-bound view function, and handed
    # to each worker as plain data -- _build_one_pitcher_report runs in a separate
    # process with no Flask app context, so it can't touch current_user itself.
    is_active = current_user.school.is_active
    include_charts = current_user.school.tier >= 2
    chart_style = current_user.chart_style
    ink_mode = current_user.ink_mode
    hash_qs = '&'.join(f'content_hash={quote(g["content_hash"])}' for g in selected)

    pitcher_ids = list(matching['PitcherId'].unique())
    pitcher_meta_by_id = {pid: _pitcher_meta(pid) for pid in pitcher_ids}

    tasks = [{
        'pitcher_id': pid,
        'source': source,
        'user_id': user_id,
        'school_id': school_id,
        'school_temp_folder': school_temp_folder,
        'school_output_folder': school_output_folder,
        'is_active': is_active,
        'include_charts': include_charts,
        'chart_style': chart_style,
        'ink_mode': ink_mode,
        'branding': branding,
        'date_range': date_range,
        'home_team': trackman_id,
        'opponent_label': opponent_label,
        'matchup_separator': matchup_separator,
        'target': target,
        'hash_qs': hash_qs,
        'pitcher_meta': pitcher_meta_by_id[pid],
    } for pid in pitcher_ids]

    def stream() -> Generator[str, None, None]:
        reports_built = 0
        failed: list[str] = []
        max_workers = min(len(tasks), os.cpu_count() or 2, 4)
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_build_one_pitcher_report, task) for task in tasks]
            for future in as_completed(futures):
                result = future.result()
                if result['ok']:
                    reports_built += 1
                    yield json.dumps({'type': 'report', **result}) + '\n'
                else:
                    failed.append(result['pitcher_id'])
                    print(f"Error processing pitcher ID {result['pitcher_id']}: {result['error']}")
                    flash_toast(f"Error processing pitcher {result['pitcher_id']}: {result['error']}", type='error')
                    yield json.dumps({'type': 'failed', 'pitcher_id': result['pitcher_id'], 'error': result['error']}) + '\n'

        merged_url = None
        if reports_built:
            merged_path = os.path.join(
                school_output_folder, f'{user_id}_merged_pitcher_reports.pdf')
            if merge_pdfs(user_id, school_output_folder, merged_path, prefix='pitcher'):
                merged_url = '/api/pitching/export?merged=1'

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'merged_pdf_url': merged_url,
            'date_range': date_range,
            'opponent': opponent_label,
            'games': len(selected),
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@pitching_bp.route('/api/pitching/export')
@login_required
def pitching_export() -> ResponseReturnValue:
    """
    Stream a PDF built by the preceding /report call.

    send_file rather than a /storage URL: the export is worth keeping behind the
    login even though the /storage routes now check school ownership too. Pass
    merged=1 for the combined file, pitcher_id for one arm.
    """
    _, school_output_folder = get_school_directories()

    if request.args.get('merged'):
        path = os.path.join(school_output_folder, f'{current_user.id}_merged_pitcher_reports.pdf')
        download_name = 'pitcher_reports.pdf'
    else:
        pitcher_id = request.args.get('pitcher_id')
        if not pitcher_id:
            return jsonify({'error': 'No pitcher selected.'}), 400
        path = os.path.join(
            school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_report.pdf')
        download_name = f'pitcher_{pitcher_id}_report.pdf'

    if not os.path.exists(path):
        return jsonify({'error': 'Report not found. Generate it first.'}), 404

    return send_file(path, mimetype='application/pdf',
                     as_attachment=True, download_name=download_name)


@pitching_bp.route('/api/pitching/pitch-by-pitch')
@login_required
def pitching_pitch_by_pitch() -> ResponseReturnValue:
    """
    Build and stream a simplified pitch-by-pitch PDF for one pitcher: a header
    (pitcher/date/matchup) followed by every at-bat's pitches, numbered in the
    order thrown. Standalone from the main per-pitcher report PDF, for the game
    selection carried in pitch_by_pitch_url (built alongside pdf_url in /report,
    from that same request's content_hashes/target).
    """
    pitcher_id_param = request.args.get('pitcher_id')
    if not pitcher_id_param:
        return jsonify({'error': 'No pitcher selected.'}), 400
    try:
        pitcher_id = int(pitcher_id_param)
    except ValueError:
        return jsonify({'error': 'Invalid pitcher ID.'}), 400

    params = {
        'content_hashes': request.args.getlist('content_hash'),
        'target': request.args.get('target', 'own'),
    }
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    source = game_archive.load_games(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404

    pitcher_rows = source[source['PitcherId'] == pitcher_id]
    if pitcher_rows.empty:
        return jsonify({'error': 'No data for that pitcher in the selected games.'}), 404
    pitcher_name = str(pitcher_rows['Pitcher'].iloc[0])

    pbp_report = report.build_pitch_by_pitch_report(source, pitcher_id)
    if pbp_report is None:
        return jsonify({'error': 'Could not build the pitch-by-pitch report.'}), 500

    branding = BrandingLoader.get_branding(current_user.school_id)
    gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)

    _, school_output_folder = get_school_directories()
    output_path = os.path.abspath(os.path.join(
        school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_pitch_by_pitch.pdf'))
    gen.generate_pitch_by_pitch_report(pbp_report, output_path)

    safe_name = secure_filename(pitcher_name) or f'pitcher_{pitcher_id}'
    return send_file(output_path, mimetype='application/pdf',
                      as_attachment=True, download_name=f'{safe_name}_pitch_by_pitch.pdf')
