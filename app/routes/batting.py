import os
import gc
import glob
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user

from app.services import game_archive, hitter_report
from app.services.branding_loader import BrandingLoader
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

    One hitter failing does not fail the batch, matching how the pitcher loop
    handles a bad pitcher: log it, toast it, keep going.
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
    gen = PDF_Generator(current_user=current_user, branding=branding)

    # Clear this user's previous hitter output so a stale chart or PDF from an
    # earlier selection can never be served or swept into the merged file
    stale = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_hitter_*_spray_*.png'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_hitter_*.pdf'))
    stale += glob.glob(os.path.join(school_output_folder, f'{current_user.id}_merged_hitter_*.pdf'))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error deleting stale hitter output: {path} - {e}")

    date_range = f'{_display_date(start_date)} - {_display_date(end_date)}'
    school_id = current_user.school_id
    reports = []
    failed = []

    for batter_id in requested:
        try:
            rows = hitter_report.batter_rows(source, batter_id)
            if rows.empty:
                failed.append(batter_id)
                continue

            if current_user.school.is_active:
                for theme in ('light', 'dark'):
                    hitter_report.hitter_spray_chart_by_pitcher_side(
                        source, current_user.id, school_temp_folder, batter_id, theme=theme)

            summary = hitter_report.build_hitter_summary(source, batter_id)
            discipline = hitter_report.build_hitter_discipline_table(source, batter_id)
            batted_ball = hitter_report.build_batted_ball_table(source, batter_id)
            hitter_name = hitter_report.batter_name(source, batter_id)
            games = int(rows['GameDate'].nunique()) if 'GameDate' in rows.columns else 0

            def chart_path(side: str, theme: str) -> str | None:
                path = os.path.join(
                    school_temp_folder,
                    f'{current_user.id}_hitter_{batter_id}_spray_{side}_{theme}.png')
                return path if os.path.exists(path) else None

            gen.generate_hitter_report({
                'hitter_name': hitter_name,
                'hitter_id': str(batter_id),
                'date_range': date_range,
                'team': allowed[batter_id].get('team', ''),
                'games': games,
                'summary': summary,
                'discipline_table': discipline,
                'batted_ball_table': batted_ball,
                'spray_chart_left': chart_path('left', 'light'),
                'spray_chart_right': chart_path('right', 'light'),
            }, _hitter_pdf_path(school_output_folder, batter_id))

            chart_base = f'/storage/schools/{school_id}/temp/{current_user.id}_hitter_{batter_id}_spray'
            export = f'/api/batting/export?batter_id={batter_id}&target={target}' \
                     f'&start_date={start_date}&end_date={end_date}'

            reports.append({
                'hitter_id': str(batter_id),
                'hitter_name': hitter_name,
                'games': games,
                'date_range': date_range,
                'summary': summary,
                'discipline_table': discipline.to_html('pitcher-data-table'),
                'batted_ball_table': batted_ball.to_html('pitcher-data-table'),
                'spray_left_url': f'{chart_base}_left_light.png',
                'spray_right_url': f'{chart_base}_right_light.png',
                'spray_left_dark_url': f'{chart_base}_left_dark.png',
                'spray_right_dark_url': f'{chart_base}_right_dark.png',
                'pdf_url': export,
            })

        except Exception as e:
            print(f"Error processing hitter ID {batter_id}: {e}")
            flash_toast(f"Error processing hitter {batter_id}: {str(e)}", type='error')
            failed.append(batter_id)
            continue

        # Charts hold matplotlib figures and full game frames; release per hitter
        gc.collect()

    merged_url = None
    if reports:
        merged_path = os.path.join(
            school_output_folder, f'{current_user.id}_merged_hitter_reports.pdf')
        if merge_pdfs(current_user.id, school_output_folder, merged_path, prefix='hitter'):
            merged_url = (f'/api/batting/export?merged=1&target={target}'
                          f'&start_date={start_date}&end_date={end_date}')

    # Distinct games across the whole selection. Ids are compared numerically --
    # astype(str) would yield '500.0' whenever pandas reads BatterId as float.
    total_games = 0
    if 'GameDate' in source.columns and requested:
        ids = pd.to_numeric(source['BatterId'], errors='coerce')
        targets = {float(b) for b in requested if str(b).replace('.', '', 1).isdigit()}
        total_games = int(source[ids.isin(targets)]['GameDate'].nunique())

    return jsonify({
        'reports': reports,
        'failed': failed,
        'merged_pdf_url': merged_url,
        'date_range': date_range,
        'start_date': start_date,
        'end_date': end_date,
        'games': total_games,
    })


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
