import os
import gc
import glob
from datetime import date, datetime
from typing import Any

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user

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

    One pitcher failing does not fail the batch, matching the loop this replaced
    in upload.py: log it, toast it, keep going.
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
    gen = PDF_Generator(current_user=current_user, branding=branding)

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

    school_id = current_user.school_id
    reports = []
    failed = []

    for pitcher_id in matching['PitcherId'].unique():
        try:
            arm_angle = None
            custom_stats = None
            custom_pitch_type_stats = None
            if current_user.school.is_active:
                for theme in ('light', 'dark'):
                    report.pitch_heat_map_by_batter_side(
                        source, current_user.id, school_temp_folder, pitcher_id, 0.75, theme=theme)
                    result = report.pitch_break_map(
                        source, current_user.id, school_temp_folder, pitcher_id, 0.75, theme=theme)
                    if arm_angle is None and result is not None:
                        arm_angle = result

                custom_stats = report.custom_stats_table(source, pitcher_id, school_id)
                custom_pitch_type_stats = report.custom_pitch_type_stats_table(source, pitcher_id, school_id)

            game_report = report.build_table(source, pitcher_id)
            if game_report is None:
                raise ValueError(f'Failed to build table data for pitcher ID {pitcher_id}')

            usage_sides = report.usage_table(source, pitcher_id)
            if usage_sides is None:
                raise ValueError(f'Failed to build pitch usage table for pitcher ID {pitcher_id}')

            height, weight, age = _pitcher_meta(pitcher_id)

            gen.generate_pitcher_report(PitcherReportRequest(
                pitcher_name=game_report.header.pitcher_name,
                pitcher_id=str(pitcher_id),
                date=date_range,
                home_team=trackman_id,
                away_team=opponent_label,
                pitcher_height=height,
                pitcher_weight=weight,
                pitcher_age=age,
                pitch_stats=game_report.stats,
                pitch_usage_left=usage_sides.left,
                pitch_usage_right=usage_sides.right,
                pitch_heat_map_left=os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_heat_map_left_light.png'),
                pitch_heat_map_right=os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_heat_map_right_light.png'),
                pitch_break_map=os.path.join(school_temp_folder, f'{current_user.id}_pitcher_{pitcher_id}_break_map_light.png'),
                custom_stats=custom_stats,
                custom_pitch_type_stats=custom_pitch_type_stats,
            ), os.path.abspath(os.path.join(
                school_output_folder, f'{current_user.id}_pitcher_{pitcher_id}_report.pdf')))

            chart_base = f'/storage/schools/{school_id}/temp/{current_user.id}_pitcher_{pitcher_id}'
            reports.append({
                'pitcher_id': str(pitcher_id),
                'pitcher_name': game_report.header.pitcher_name,
                'pitcher_table': game_report.stats.to_html('pitcher-data-table'),
                'left_usage_table': usage_sides.left.to_html('pitch-usage-table'),
                'right_usage_table': usage_sides.right.to_html('pitch-usage-table'),
                'heatmap_left_url': f'{chart_base}_heat_map_left_light.png',
                'heatmap_right_url': f'{chart_base}_heat_map_right_light.png',
                'heatmap_left_dark_url': f'{chart_base}_heat_map_left_dark.png',
                'heatmap_right_dark_url': f'{chart_base}_heat_map_right_dark.png',
                'breakmap_url': f'{chart_base}_break_map_light.png',
                'breakmap_dark_url': f'{chart_base}_break_map_dark.png',
                'arm_angle': f'{arm_angle:.1f}°' if arm_angle is not None else '',
                'pdf_url': f'/api/pitching/export?pitcher_id={pitcher_id}',
            })

        except Exception as e:
            print(f"Error processing pitcher ID {pitcher_id}: {e}")
            flash_toast(f"Error processing pitcher {pitcher_id}: {str(e)}", type='error')
            failed.append(str(pitcher_id))
            continue

        gc.collect()

    merged_url = None
    if reports:
        merged_path = os.path.join(
            school_output_folder, f'{current_user.id}_merged_pitcher_reports.pdf')
        if merge_pdfs(current_user.id, school_output_folder, merged_path, prefix='pitcher'):
            merged_url = '/api/pitching/export?merged=1'

    return jsonify({
        'reports': reports,
        'failed': failed,
        'merged_pdf_url': merged_url,
        'date_range': date_range,
        'opponent': opponent_label,
        'games': len(selected),
    })


@pitching_bp.route('/api/pitching/export')
@login_required
def pitching_export() -> ResponseReturnValue:
    """
    Stream a PDF built by the preceding /report call.

    send_file rather than a /storage URL: those static routes are unauthenticated,
    and an export is worth keeping behind the login. Pass merged=1 for the combined
    file, pitcher_id for one arm.
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
