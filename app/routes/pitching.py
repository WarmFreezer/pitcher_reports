import io
import os
import gc
import glob
import json
import traceback
from datetime import date, datetime
from typing import Any, Generator
from urllib.parse import quote

import pandas as pd
from flask import Blueprint, request, jsonify, render_template, send_file, Response, stream_with_context
from flask.typing import ResponseReturnValue
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.db import models
from app.services import chart_images, game_archive, pitch_filters, pitcher_card, report
from app.services.branding_loader import BrandingLoader
from app.services.pitch_filters import PitchFilters
from app.services.pitch_stats import PitcherReportRequest
from app.services.chart_prefs import ChartPrefs
from app.services.report_lab_generator import PDF_Generator, merge_pdfs
from app.routes.utils import (
    chart_prefs, charts_enabled, export_workdir, filters_from_args, flash_toast,
    get_school_directories, get_school_games_directory,
)

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


def _build_one_pitcher_pbp(task: dict[str, Any]) -> dict[str, Any]:
    """
    Build one pitcher's pitch-by-pitch PDF for the "download all pitch-by-pitch"
    bulk merge. Takes everything it needs on `task` as plain data (no current_user).
    Writes to the same path the single-pitcher pitch-by-pitch route uses, so a coach
    who already downloaded one pitcher individually just gets that file regenerated,
    not duplicated.
    """
    pitcher_id = task['pitcher_id']
    try:
        source = task['source']
        user_id = task['user_id']
        school_temp_folder = task['school_temp_folder']
        school_output_folder = task['school_output_folder']

        pbp_report = report.build_pitch_by_pitch_report(source, pitcher_id)
        if pbp_report is None:
            raise ValueError(f'Failed to build pitch-by-pitch data for pitcher ID {pitcher_id}')

        gen = PDF_Generator(school_id=task['school_id'], branding=task['branding'], ink_mode=task['ink_mode'])
        output_path = os.path.abspath(os.path.join(
            school_output_folder, f'{user_id}_pitcher_{pitcher_id}_pitch_by_pitch.pdf'))
        gen.generate_pitch_by_pitch_report(pbp_report, output_path)

        return {'ok': True, 'pitcher_id': str(pitcher_id)}
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


def _team_pitchers(source: pd.DataFrame, target: str) -> pd.DataFrame:
    """The Own/Opponent switch filters which arms get reports, not which games were
    selected -- both teams pitched in every game on the list."""
    trackman_id = current_user.school.trackman_id
    # Only the three columns the callers read (ids, pitch types, velo bounds) -- not a
    # copy of the whole wide frame just to learn who pitched.
    columns = ['PitcherId', 'TaggedPitchType', 'RelSpeed']
    if target == 'opponent':
        return source.loc[source['PitcherTeam'] != trackman_id, columns]
    return source.loc[source['PitcherTeam'] == trackman_id, columns]


def _card_payload(
    source: pd.DataFrame, pitcher_id: int, filters: PitchFilters, prefs: ChartPrefs,
    *, charts_only: bool = False, filtered: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """
    One pitcher's JSON card for the current filters. Built in-process; current_user is
    read here, in the view layer, and never inside the services it calls.

    charts_only skips the stat tables -- a color-by or scatter/heatmap change redraws the
    charts but can't change a single number. `filtered` is filters.apply(source) when the
    caller is building many cards and has already done it once.
    """
    payload: dict[str, Any] = {'ok': True, 'pitcher_id': str(pitcher_id)}

    if not charts_only:
        data = pitcher_card.build_pitcher_data(
            source, pitcher_id, filters,
            school_id=current_user.school_id, is_active=current_user.school.is_active,
            filtered=filtered)
        if data is None:
            payload['pitcher_name'] = pitcher_card.pitcher_name_in(source, pitcher_id) or str(pitcher_id)
            payload['empty'] = True
            return payload
        payload['pitcher_name'] = data.pitcher_name
        payload.update(pitcher_card.tables_payload(data))

    if charts_enabled():
        payload.update(pitcher_card.charts_payload(
            pitcher_card.build_pitcher_charts(source, pitcher_id, filters, prefs)))
    return payload


def _report_context(selected: list[dict[str, Any]]) -> dict[str, str]:
    dates = sorted(g['date'] for g in selected)
    date_range = (_display_date(dates[0]) if dates[0] == dates[-1]
                  else f'{_display_date(dates[0])} - {_display_date(dates[-1])}')
    opponents = sorted({g['opponent'] for g in selected})
    return {
        'date_range': date_range,
        'opponent_label': opponents[0] if len(opponents) == 1 else f'{len(opponents)} opponents',
        # A true single selected game reads correctly as "us @ opponent"; anything
        # aggregated across games isn't a real single-game home/away pair.
        'matchup_separator': '@' if len(selected) == 1 else 'vs',
    }


@pitching_bp.route('/api/pitching/report', methods=['POST'])
@login_required
def pitching_report() -> ResponseReturnValue:
    """
    Build the preview cards for every pitcher in the selected games.

    A selection may span several outings -- a weekend series against one opponent
    is the motivating case -- so each pitcher gets one report aggregating their
    work across everything selected, and the header carries the date range rather
    than a single game date.

    Streams newline-delimited JSON: one 'meta' line (the pitch types and velocity range
    the filter bar is built from, plus the account's chart defaults), one 'report' line
    per pitcher as their card finishes, then a 'done' summary. One pitcher failing does
    not fail the batch: log it, toast it, keep going.

    No chart images or PDFs are produced here. Charts are Plotly figures drawn by the
    browser; the PDF is built on demand by POST /api/pitching/export, with chart images
    the browser renders from those same figures.
    """
    params = request.get_json(silent=True) or {}
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    target = params.get('target', 'own')
    try:
        filters = PitchFilters.from_request(params.get('filters'))
        prefs = chart_prefs(params)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    source = game_archive.load_games_cached(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404

    matching = _team_pitchers(source, target)
    if matching.empty:
        side = 'opponent' if target == 'opponent' else 'your team'
        return jsonify({'error': f'No pitching data found for {side} in the selected games.'}), 404

    context = _report_context(selected)
    hash_qs = '&'.join(f'content_hash={quote(g["content_hash"])}' for g in selected)
    pitcher_ids = list(matching['PitcherId'].unique())
    charts_on = charts_enabled()
    bounds = pitch_filters.velo_bounds(matching)
    pitch_type_options = pitch_filters.pitch_type_options(matching)

    def stream() -> Generator[str, None, None]:
        yield json.dumps({
            'type': 'meta',
            'pitch_types': pitch_type_options,
            'velo_min': bounds[0] if bounds else None,
            'velo_max': bounds[1] if bounds else None,
            'defaults': {'view': prefs.view, 'color_by': prefs.color_by},
            'charts_enabled': charts_on,
        }) + '\n'

        reports_built = 0
        failed: list[str] = []
        # Filter once for the whole staff instead of rebuilding a filtered copy per pitcher.
        filtered = filters.apply(source)
        for pid in pitcher_ids:
            try:
                card = _card_payload(source, pid, filters, prefs, filtered=filtered)
            except Exception as e:
                failed.append(str(pid))
                print(f"Error processing pitcher ID {pid}: {e}")
                flash_toast(f"Error processing pitcher {pid}: {e}", type='error')
                yield json.dumps({'type': 'failed', 'pitcher_id': str(pid), 'error': str(e)}) + '\n'
                continue
            card['pitch_by_pitch_url'] = f'/api/pitching/pitch-by-pitch?pitcher_id={pid}&target={target}&{hash_qs}'
            reports_built += 1
            yield json.dumps({'type': 'report', **card}) + '\n'

        # Pitch-by-pitch PDFs aren't built here (they're lazy, per-pitcher, on
        # their own route) -- this just hands the bulk route the same game
        # selection so it can rebuild and merge them itself when clicked.
        pitch_by_pitch_all_url = (
            f'/api/pitching/pitch-by-pitch/all?target={target}&{hash_qs}' if reports_built else None)

        yield json.dumps({
            'type': 'done',
            'report_count': reports_built,
            'failed': failed,
            'pitch_by_pitch_all_url': pitch_by_pitch_all_url,
            'date_range': context['date_range'],
            'opponent': context['opponent_label'],
            'games': len(selected),
        }) + '\n'

    return Response(stream_with_context(stream()), mimetype='application/x-ndjson')


@pitching_bp.route('/api/pitching/pitcher', methods=['POST'])
@login_required
def pitching_pitcher() -> ResponseReturnValue:
    """
    Rebuild one pitcher's card for new filters or chart options, so a slider release
    recomputes only the cards the user has open instead of the whole staff.

    charts_only=true redraws just the figures (color-by / scatter-heatmap changes).
    """
    params = request.get_json(silent=True) or {}
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    try:
        pitcher_id = int(params['pitcher_id'])
        filters = PitchFilters.from_request(params.get('filters'))
        prefs = chart_prefs(params)
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Invalid request.'}), 400

    source = game_archive.load_games_cached(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404

    matching = _team_pitchers(source, params.get('target', 'own'))
    if pitcher_id not in set(matching['PitcherId'].unique()):
        return jsonify({'error': 'Pitcher not found'}), 404

    try:
        card = _card_payload(source, pitcher_id, filters, prefs,
                             charts_only=params.get('charts_only') is True)
    except Exception as e:
        print(f"Error rebuilding pitcher ID {pitcher_id}: {e}")
        return jsonify({'error': 'Could not rebuild that report.'}), 500
    return jsonify(card)


MAX_EXPORT_BYTES = 40 * 1024 * 1024
MAX_EXPORT_PITCHERS = 100
CHART_SLOTS = ('heat_left', 'heat_right', 'break')


@pitching_bp.route('/api/pitching/export', methods=['POST'])
@login_required
def pitching_export() -> ResponseReturnValue:
    """
    Build and stream the PDF for the requested pitchers under the current filters.

    The numbers and tables are recomputed here from the school's own archive; the only
    client-supplied inputs are the filters (validated) and each pitcher's chart images,
    which the browser rendered from the same Plotly figures it is displaying
    (see services/chart_images.py for how they are checked). One pitcher streams back
    as their own PDF, several as one merged file.
    """
    if (request.content_length or 0) > MAX_EXPORT_BYTES:
        return jsonify({'error': 'Export is too large.'}), 413

    params = request.get_json(silent=True) or {}
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    requested = params.get('pitchers')
    if not isinstance(requested, list) or not requested or len(requested) > MAX_EXPORT_PITCHERS:
        return jsonify({'error': 'No pitchers selected.'}), 400

    try:
        filters = PitchFilters.from_request(params.get('filters'))
        pitcher_ids = [int(p['pitcher_id']) for p in requested]
        images_by_pitcher = {int(p['pitcher_id']): p.get('images') or {} for p in requested}
        if not all(isinstance(imgs, dict) for imgs in images_by_pitcher.values()):
            raise ValueError('Invalid images.')
    except (TypeError, ValueError, KeyError):
        return jsonify({'error': 'Invalid request.'}), 400

    source = game_archive.load_games_cached(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404

    matching = _team_pitchers(source, params.get('target', 'own'))
    if not set(pitcher_ids) <= set(matching['PitcherId'].unique()):
        return jsonify({'error': 'Pitcher not found'}), 404

    school_temp_folder, _ = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)
    context = _report_context(selected)
    user_id = current_user.id
    use_images = charts_enabled()

    # The finished PDF is read into memory and the working directory removed (see export_workdir).
    with export_workdir(school_temp_folder, user_id) as work_dir:
        gen = PDF_Generator(school_id=current_user.school_id, branding=branding, ink_mode=current_user.ink_mode)
        built: list[int] = []
        failed = 0
        filtered = filters.apply(source)  # once, not once per pitcher
        for pid in pitcher_ids:
            data = pitcher_card.build_pitcher_data(
                source, pid, filters,
                school_id=current_user.school_id, is_active=current_user.school.is_active,
                filtered=filtered)
            if data is None:
                continue  # nothing passes the filters for this arm

            image_paths: dict[str, str | None] = {slot: None for slot in CHART_SLOTS}
            if use_images:
                for slot in CHART_SLOTS:
                    posted = images_by_pitcher[pid].get(slot)
                    if posted is None:
                        continue
                    path = os.path.join(work_dir, f'{user_id}_pitcher_{pid}_{slot}.png')
                    try:
                        chart_images.save_chart_image(posted, path)
                    except chart_images.InvalidChartImage as e:
                        return jsonify({'error': str(e)}), 400
                    image_paths[slot] = path

            height, weight, age = _pitcher_meta(pid)
            try:
                gen.generate_pitcher_report(PitcherReportRequest(
                    pitcher_name=data.pitcher_name,
                    pitcher_id=str(pid),
                    date=context['date_range'],
                    home_team=current_user.school.trackman_id,
                    away_team=context['opponent_label'],
                    matchup_separator=context['matchup_separator'],
                    pitcher_height=height,
                    pitcher_weight=weight,
                    pitcher_age=age,
                    pitch_stats=data.game_report.stats,
                    pitch_usage_left=data.usage_sides.left,
                    pitch_usage_right=data.usage_sides.right,
                    pitch_heat_map_left=image_paths['heat_left'],
                    pitch_heat_map_right=image_paths['heat_right'],
                    pitch_break_map=image_paths['break'],
                    pitch_break_map_legend=data.legend,
                    custom_stats=data.custom_stats,
                    custom_pitch_type_stats=data.custom_pitch_type_stats,
                ), os.path.abspath(os.path.join(work_dir, f'{user_id}_pitcher_{pid}_report.pdf')))
            except Exception:
                failed += 1
                print(f"Error generating PDF for pitcher ID {pid}:")
                traceback.print_exc()
                continue
            built.append(pid)

        if not built:
            if failed:
                return jsonify({'error': 'Could not build the PDF.'}), 500
            return jsonify({'error': 'No pitches match the current filters.'}), 404

        if len(built) == 1:
            path = os.path.join(work_dir, f'{user_id}_pitcher_{built[0]}_report.pdf')
            download_name = f'pitcher_{built[0]}_report.pdf'
        else:
            path = os.path.join(work_dir, f'{user_id}_merged_pitcher_reports.pdf')
            if not merge_pdfs(user_id, work_dir, path, prefix='pitcher'):
                return jsonify({'error': 'Could not merge the reports.'}), 500
            download_name = 'pitcher_reports.pdf'

        with open(path, 'rb') as f:
            pdf_bytes = f.read()

    return send_file(io.BytesIO(pdf_bytes), mimetype='application/pdf',
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

    filters = filters_from_args()
    if filters is None:
        return jsonify({'error': 'Invalid filters.'}), 400

    source = game_archive.load_games_cached(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404
    source = filters.apply(source)

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


@pitching_bp.route('/api/pitching/pitch-by-pitch/all')
@login_required
def pitching_pitch_by_pitch_all() -> ResponseReturnValue:
    """
    Build every displayed pitcher's pitch-by-pitch PDF for the given game
    selection and merge them into one download -- the bulk counterpart to
    pitching_pitch_by_pitch, for the "Download All Pitch-by-Pitch" button next
    to the main report's "Download All". Lazy like the single-pitcher route:
    nothing here runs during /report, only when a coach clicks this link (built
    from pitch_by_pitch_all_url in that same request's 'done' message).
    """
    params = {
        'content_hashes': request.args.getlist('content_hash'),
        'target': request.args.get('target', 'own'),
    }
    games_dir, selected, error = _selected_games(params)
    if error:
        return error
    assert games_dir is not None and selected is not None

    target = params['target']
    trackman_id = current_user.school.trackman_id

    filters = filters_from_args()
    if filters is None:
        return jsonify({'error': 'Invalid filters.'}), 400

    source = game_archive.load_games_cached(games_dir, [g['content_hash'] for g in selected])
    if source.empty:
        return jsonify({'error': 'No data in the selected games.'}), 404
    source = filters.apply(source)

    if target == 'opponent':
        matching = source.loc[source['PitcherTeam'] != trackman_id, 'PitcherId']
    else:
        matching = source.loc[source['PitcherTeam'] == trackman_id, 'PitcherId']

    if matching.empty:
        side = 'opponent' if target == 'opponent' else 'your team'
        return jsonify({'error': f'No pitching data found for {side} in the selected games.'}), 404

    school_temp_folder, school_output_folder = get_school_directories()
    branding = BrandingLoader.get_branding(current_user.school_id)
    school_id = current_user.school_id
    user_id = current_user.id
    ink_mode = current_user.ink_mode

    # Clear this user's previous pitch-by-pitch output so a stale file left
    # over from an earlier, different game selection can't get swept into
    # today's merge.
    stale = glob.glob(os.path.join(school_output_folder, f'{user_id}_pitcher_*_pitch_by_pitch.pdf'))
    stale.append(os.path.join(school_output_folder, f'{user_id}_merged_pitcher_pitch_by_pitch.pdf'))
    for path in stale:
        try:
            os.remove(path)
        except OSError as e:
            print(f"Error deleting stale pitch-by-pitch output: {path} - {e}")

    pitcher_ids = list(matching.unique())
    tasks = [{
        'pitcher_id': pid,
        'source': source,
        'user_id': user_id,
        'school_id': school_id,
        'school_temp_folder': school_temp_folder,
        'school_output_folder': school_output_folder,
        'branding': branding,
        'ink_mode': ink_mode,
    } for pid in pitcher_ids]

    # In-process: the at-bat panels are vector drawings now, so there is no chart rendering
    # worth fanning out to worker processes.
    built = 0
    for task in tasks:
        result = _build_one_pitcher_pbp(task)
        if result['ok']:
            built += 1
        else:
            print(f"Error building pitch-by-pitch for pitcher ID {result['pitcher_id']}: {result['error']}")

    if built == 0:
        return jsonify({'error': 'Could not build any pitch-by-pitch reports.'}), 500

    merged_path = os.path.join(school_output_folder, f'{user_id}_merged_pitcher_pitch_by_pitch.pdf')
    if not merge_pdfs(user_id, school_output_folder, merged_path, prefix='pitcher', require_suffix='_pitch_by_pitch.pdf'):
        return jsonify({'error': 'Could not merge the pitch-by-pitch reports.'}), 500

    return send_file(merged_path, mimetype='application/pdf',
                      as_attachment=True, download_name='pitch_by_pitch_reports.pdf')
