"""
Ingest and management for TrackMan game files.

This blueprint used to generate every pitcher report inline. That work now lives in
app/routes/pitching.py, reading from the saved game archive, so a file has to be
saved before any report can be built from it. What is left here is the pipeline
that gets a file into the archive, plus the manager for what is already in it.
"""
import os
import glob
import pandas as pd
from datetime import datetime
from werkzeug.utils import secure_filename
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user

from app.services import report, game_archive, file_validator
from app.services.team_stats import hash_file
from app.routes.utils import get_school_directories, get_school_games_directory

upload_bp = Blueprint('upload_api', __name__)

required_columns = report.required_columns


def _read_source(filepath):
    if filepath.endswith(('.xlsx', '.xls')):
        return pd.read_excel(filepath)
    return pd.read_csv(filepath, low_memory=False)


def _distinct(source, column):
    return int(source[column].nunique()) if column in source.columns else 0


@upload_bp.route('/api/upload', methods=['POST'])
@login_required
def upload_file():
    """
    Validate a TrackMan file and stage it for saving.

    Returns a summary of what the file contains so the user can confirm it is the
    right game before committing it. No charts, no PDFs -- those come from
    /pitching and /batting once the game is saved.
    """
    school_temp_folder, _ = get_school_directories()

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    filename = secure_filename(file.filename)
    if not filename.endswith(('.csv', '.xlsx', '.xls')):
        return jsonify({'error': 'Unsupported file format. Please provide a .csv, .xlsx, or .xls file.'}), 400

    # Clear this user's previous staging file so save-game cannot pick up a stale one
    for pattern in ('*.xlsx', '*.xls', '*.csv'):
        for old_file in glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_{pattern}')):
            try:
                os.remove(old_file)
            except OSError as e:
                print(f"Error deleting old file: {old_file} - {e}")

    filepath = os.path.join(school_temp_folder, f'{current_user.id}_{filename}')
    file.save(filepath)

    try:
        source = _read_source(filepath)
    except Exception as e:
        os.remove(filepath)
        return jsonify({'error': f'Could not read the file: {e}'}), 400

    # Full validation: extension, MIME type, file signature, column presence, types
    is_valid, result = file_validator.validate_uploaded_file(
        source_df=source, file=file, filepath=filepath,
        required_columns=list(required_columns.keys()),
        column_types=required_columns,
    )

    if not is_valid:
        try:
            os.remove(filepath)
        except OSError:
            pass
        current_app.logger.warning(f"File validation failed: {filename} - {result}")
        return jsonify({'error': result}), 400

    current_app.logger.info(f"Valid file uploaded: {filename} - Checksum: {result}")

    raw_date = source['Date'].mode().iloc[0] if 'Date' in source.columns else ''
    parts = str(raw_date).split('-')
    display_date = f"{parts[1]}/{parts[2]}/{parts[0]}" if len(parts) == 3 else str(raw_date)

    # Must be team_stats.hash_file, not the validator's checksum -- the validator
    # returns SHA-256 for logging while the archive and the database both key on
    # that MD5. Comparing the two would never match.
    with open(filepath, 'rb') as f:
        content_hash = hash_file(f)
    already_saved = any(
        entry.get('content_hash') == content_hash
        for entry in game_archive.read_manifest(get_school_games_directory())
    )

    return jsonify({
        'message': 'File validated. Review the summary, then save the game.',
        'filename': filename,
        'already_saved': already_saved,
        'game_data': {
            'date': display_date,
            'home_team': source['HomeTeam'].mode().iloc[0] if 'HomeTeam' in source.columns else '',
            'away_team': source['AwayTeam'].mode().iloc[0] if 'AwayTeam' in source.columns else '',
            'pitches': int(len(source)),
            'pitchers': _distinct(source, 'PitcherId'),
            'batters': _distinct(source, 'BatterId'),
        },
    })


@upload_bp.route('/api/save-game', methods=['POST'])
@login_required
def save_game():
    """
    Commit the staged file: archive it, and unless it is a practice file, write
    its aggregates to the database.

    The archive is what /pitching and /batting read, so practice files stay fully
    reportable. The flag only gates the database write, which is what keeps them
    out of the dashboard and season totals.
    """
    from app.services.team_stats import add_report

    params = request.get_json(silent=True) or {}
    practice = bool(params.get('practice', False))

    school_temp_folder, _ = get_school_directories()
    matches = glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.csv'))
    matches += glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.xlsx'))
    matches += glob.glob(os.path.join(school_temp_folder, f'{current_user.id}_*.xls'))
    if not matches:
        return jsonify({'error': 'No uploaded file found. Please upload a file first.'}), 400

    filepath = matches[0]

    if not practice:
        with open(filepath, 'rb') as f:
            add_report(
                school_id=current_user.school_id,
                trackman_id=current_user.school.trackman_id,
                file=f,
            )

    entry = game_archive.archive_game(
        get_school_games_directory(), filepath, practice=practice)

    if entry is None:
        return jsonify({'message': 'Game was already saved.', 'duplicate': True})

    return jsonify({
        'message': 'Practice file saved.' if practice else 'Game data saved successfully.',
        'duplicate': False,
        'game': {'date': entry['date'], 'practice': entry['practice']},
    })


@upload_bp.route('/api/games')
@login_required
def list_saved_games():
    """Every saved game for this school, for the manager table."""
    games_dir = get_school_games_directory()
    return jsonify({
        'games': game_archive.list_games(games_dir, current_user.school.trackman_id),
    })


@upload_bp.route('/api/games/<content_hash>', methods=['DELETE'])
@login_required
def delete_saved_game(content_hash):
    """
    Remove a saved game from both stores.

    content_hash is deliberately the same identifier in the archive and the
    database, which is what makes a clean two-sided delete possible. The hash is
    checked against this school's archive first, so one school cannot delete
    another's rows by guessing.
    """
    from app.services.team_stats import remove_report

    games_dir = get_school_games_directory()
    known = {
        g['content_hash']
        for g in game_archive.list_games(games_dir, current_user.school.trackman_id)
    }
    if content_hash not in known:
        return jsonify({'error': 'Game not found'}), 404

    removed = game_archive.remove_game(games_dir, content_hash)
    remove_report(content_hash)

    return jsonify({'message': 'Game deleted.', 'removed': removed})
