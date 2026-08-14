"""
Upload, save, and the saved-game manager.

/api/upload no longer generates anything -- it validates a file and describes it so
the user can confirm the right game before committing. Report generation moved to
/pitching and /batting, which read from the archive, so a game must be saved first.
"""
import io
import os
from pathlib import Path

import pytest

from app.db.models import Outing, Pitcher

FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'sample_game.csv'
HITTING_GAME = Path(__file__).parent / 'fixtures' / 'sample_hitting_game_1.csv'


@pytest.fixture
def home_school(make_school):
    # trackman_id must match the fixture's PitcherTeam values so uploaded rows match
    return make_school(trackman_id='HOME')


@pytest.fixture
def home_user(make_user, home_school):
    return make_user(home_school)


def _upload(client, path=FIXTURE_PATH, filename=None, content=None):
    content = content if content is not None else path.read_bytes()
    return client.post(
        '/api/upload',
        data={'file': (io.BytesIO(content), filename or path.name)},
        content_type='multipart/form-data',
    )


def _save(client, practice=False):
    return client.post('/api/save-game', json={'practice': practice})


def _games_dir(app, school):
    return os.path.join(app.config['STORAGE'], 'schools', str(school.id), 'games')


# --- upload: validate and describe -----------------------------------------

def test_upload_returns_a_summary_of_the_file(client, login_as, home_user):
    login_as(client, home_user)

    resp = _upload(client)
    data = resp.get_json()

    assert resp.status_code == 200, data
    assert data['already_saved'] is False
    game = data['game_data']
    assert game['date'] == '01/15/2026'
    assert game['home_team'] == 'HOME'
    assert game['away_team'] == 'AWAY'
    assert game['pitchers'] == 2          # Doe and Smith
    assert game['pitches'] == 18


def test_upload_generates_no_reports(client, login_as, home_user, home_school, app):
    """Generation moved to /pitching -- upload should touch neither charts nor PDFs."""
    login_as(client, home_user)

    _upload(client)

    school_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id))
    assert glob_count(os.path.join(school_dir, 'temp'), '.png') == 0
    assert glob_count(os.path.join(school_dir, 'reports'), '.pdf') == 0


def glob_count(directory, suffix):
    if not os.path.isdir(directory):
        return 0
    return len([f for f in os.listdir(directory) if f.endswith(suffix)])


def test_upload_flags_a_file_that_is_already_saved(client, login_as, home_user):
    login_as(client, home_user)
    _upload(client)
    _save(client)

    resp = _upload(client)

    assert resp.get_json()['already_saved'] is True


def test_upload_rejects_missing_file(client, login_as, home_user):
    login_as(client, home_user)

    resp = client.post('/api/upload', data={}, content_type='multipart/form-data')

    assert resp.status_code == 400
    assert 'No file part' in resp.get_json()['error']


def test_upload_rejects_an_unsupported_extension(client, login_as, home_user):
    """Previously this raised an uncaught ValueError; it is a 400 now."""
    login_as(client, home_user)

    resp = _upload(client, filename='sample_game.txt')

    assert resp.status_code == 400
    assert 'Unsupported file format' in resp.get_json()['error']


def test_upload_rejects_a_file_missing_required_columns(client, login_as, home_user):
    login_as(client, home_user)
    stripped = FIXTURE_PATH.read_text().replace('RelSpeed,', '')

    resp = _upload(client, content=stripped.encode('utf-8'))

    assert resp.status_code == 400


# --- save: archive + database ----------------------------------------------

def test_save_game_persists_outings_and_archives_the_file(client, login_as, home_user, home_school, app):
    from app.services import game_archive

    login_as(client, home_user)
    _upload(client)

    resp = _save(client)
    assert resp.status_code == 200
    assert resp.get_json()['duplicate'] is False

    with app.app_context():
        outings = (Outing.query
                   .join(Pitcher, Outing.pitcher_id == Pitcher.id)
                   .filter(Pitcher.school_id == home_school.id).all())
        assert len(outings) >= 1

    assert len(game_archive.read_manifest(_games_dir(app, home_school))) == 1


def test_saving_twice_reports_a_duplicate(client, login_as, home_user, home_school, app):
    from app.services import game_archive

    login_as(client, home_user)
    _upload(client)
    _save(client)
    _upload(client)

    resp = _save(client)

    assert resp.get_json()['duplicate'] is True
    assert len(game_archive.read_manifest(_games_dir(app, home_school))) == 1


def test_save_without_an_upload_is_rejected(client, login_as, home_user):
    login_as(client, home_user)

    resp = _save(client)

    assert resp.status_code == 400
    assert 'No uploaded file' in resp.get_json()['error']


# --- practice files ---------------------------------------------------------

def test_practice_file_is_archived_but_skips_the_database(client, login_as, home_user, home_school, app):
    """The flag gates the database write only -- the game stays fully reportable."""
    from app.services import game_archive

    login_as(client, home_user)
    _upload(client)

    resp = _save(client, practice=True)
    assert resp.status_code == 200

    with app.app_context():
        outings = (Outing.query
                   .join(Pitcher, Outing.pitcher_id == Pitcher.id)
                   .filter(Pitcher.school_id == home_school.id).all())
        assert outings == [], 'a practice file must not reach season stats'

    manifest = game_archive.read_manifest(_games_dir(app, home_school))
    assert len(manifest) == 1
    assert manifest[0]['practice'] is True


def test_practice_file_appears_in_the_saved_games_list(client, login_as, home_user):
    login_as(client, home_user)
    _upload(client)
    _save(client, practice=True)

    games = client.get('/api/games').get_json()['games']

    assert len(games) == 1
    assert games[0]['practice'] is True


# --- manager: list and delete -----------------------------------------------

def test_games_list_is_empty_before_anything_is_saved(client, login_as, home_user):
    login_as(client, home_user)

    assert client.get('/api/games').get_json() == {'games': []}


def test_games_list_describes_each_saved_game(client, login_as, home_user):
    login_as(client, home_user)
    _upload(client)
    _save(client)

    game = client.get('/api/games').get_json()['games'][0]

    assert game['date'] == '2026-01-15'
    assert game['content_hash']
    assert game['practice'] is False
    assert game['pitcher_count'] == 2


def test_delete_removes_the_game_from_both_stores(client, login_as, home_user, home_school, app):
    from app.services import game_archive

    login_as(client, home_user)
    _upload(client)
    _save(client)

    content_hash = client.get('/api/games').get_json()['games'][0]['content_hash']
    resp = client.delete(f'/api/games/{content_hash}')

    assert resp.status_code == 200
    assert game_archive.read_manifest(_games_dir(app, home_school)) == []
    with app.app_context():
        assert Outing.query.filter_by(content_hash=content_hash).all() == []


def test_delete_of_an_unknown_game_is_a_404(client, login_as, home_user):
    login_as(client, home_user)

    resp = client.delete('/api/games/not-a-real-hash')

    assert resp.status_code == 404


def test_delete_cannot_reach_another_schools_game(client, login_as, make_school, make_user, home_user):
    """The hash is checked against this school's archive before anything is removed."""
    other_school = make_school(trackman_id='OTHER')
    other_user = make_user(other_school)

    login_as(client, other_user)
    _upload(client)
    _save(client)
    stolen = client.get('/api/games').get_json()['games'][0]['content_hash']
    client.get('/logout')

    login_as(client, home_user)
    resp = client.delete(f'/api/games/{stolen}')

    assert resp.status_code == 404
