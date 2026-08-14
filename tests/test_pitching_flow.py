"""
End-to-end coverage for /pitching.

Games reach the archive through /api/upload + /api/save-game, so these drive the
same path a user does. Unlike the old flow, no report exists until a game is saved.

Both fixture games are HOME vs AWAY with Doe (1001) pitching for HOME and Smith
(2002) for AWAY, so target='own' yields one pitcher and 'opponent' the other.
"""
import io
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'
GAME_1 = FIXTURES / 'sample_hitting_game_1.csv'   # 2026-03-01
GAME_2 = FIXTURES / 'sample_hitting_game_2.csv'   # 2026-03-08


@pytest.fixture
def home_school(make_school):
    return make_school(trackman_id='HOME')


@pytest.fixture
def home_user(make_user, home_school):
    return make_user(home_school)


def _save_game(client, path, practice=False):
    resp = client.post(
        '/api/upload',
        data={'file': (io.BytesIO(path.read_bytes()), path.name)},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200, resp.get_json()
    resp = client.post('/api/save-game', json={'practice': practice})
    assert resp.status_code == 200, resp.get_json()


@pytest.fixture
def archived_games(client, login_as, home_user):
    login_as(client, home_user)
    _save_game(client, GAME_1)
    _save_game(client, GAME_2)
    return home_user


def _hashes(client, **params):
    from urllib.parse import urlencode
    query = f'?{urlencode(params)}' if params else ''
    return [g['content_hash'] for g in client.get(f'/api/pitching/games{query}').get_json()['games']]


def _report(client, hashes=None, target='own'):
    if hashes is None:
        hashes = _hashes(client)
    return client.post('/api/pitching/report',
                       json={'content_hashes': hashes, 'target': target})


# --- game listing -----------------------------------------------------------

def test_games_endpoint_lists_the_archive_with_bounds(archived_games, client):
    data = client.get('/api/pitching/games').get_json()

    assert data['game_count'] == 2
    assert data['first_date'] == '2026-03-01'
    assert data['last_date'] == '2026-03-08'
    assert [g['date'] for g in data['games']] == ['2026-03-01', '2026-03-08']


def test_games_endpoint_honors_the_date_range(archived_games, client):
    data = client.get(
        '/api/pitching/games?start_date=2026-03-08&end_date=2026-03-08').get_json()

    assert [g['date'] for g in data['games']] == ['2026-03-08']


def test_games_endpoint_can_hide_practice_files(client, login_as, home_user):
    login_as(client, home_user)
    _save_game(client, GAME_1, practice=True)
    _save_game(client, GAME_2, practice=False)

    with_practice = client.get('/api/pitching/games').get_json()['games']
    without = client.get('/api/pitching/games?include_practice=0').get_json()['games']

    assert len(with_practice) == 2
    assert [g['date'] for g in without] == ['2026-03-08']


def test_games_endpoint_is_empty_before_anything_is_saved(client, login_as, home_user):
    login_as(client, home_user)

    data = client.get('/api/pitching/games').get_json()

    assert data == {'games': [], 'first_date': None, 'last_date': None, 'game_count': 0}


# --- report generation ------------------------------------------------------

def test_report_covers_every_pitcher_on_the_selected_side(archived_games, client):
    data = _report(client).get_json()

    assert len(data['reports']) == 1
    assert data['reports'][0]['pitcher_name'] == 'Doe, John'
    assert data['failed'] == []
    assert data['games'] == 2


def test_opponent_target_reports_the_other_dugout(archived_games, client):
    data = _report(client, target='opponent').get_json()

    assert [r['pitcher_name'] for r in data['reports']] == ['Smith, Jane']


def test_selecting_one_game_narrows_the_range_in_the_header(archived_games, client):
    one = _hashes(client, start_date='2026-03-01', end_date='2026-03-01')

    data = _report(client, hashes=one).get_json()

    assert data['games'] == 1
    assert data['date_range'] == '03/01/2026'


def test_multi_game_selection_spans_the_dates(archived_games, client):
    data = _report(client).get_json()

    assert data['date_range'] == '03/01/2026 - 03/08/2026'


def test_report_generates_charts_in_both_themes(archived_games, client, app, home_school, home_user):
    _report(client)

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    for name in (
        f'{home_user.id}_pitcher_1001_heat_map_left_light.png',
        f'{home_user.id}_pitcher_1001_heat_map_left_dark.png',
        f'{home_user.id}_pitcher_1001_break_map_light.png',
        f'{home_user.id}_pitcher_1001_break_map_dark.png',
    ):
        assert os.path.exists(os.path.join(temp_dir, name)), f'missing {name}'


def test_report_produces_a_merged_pdf(archived_games, client, app, home_school, home_user):
    data = _report(client).get_json()

    assert data['merged_pdf_url']
    reports_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'reports')
    assert os.path.exists(os.path.join(reports_dir, f'{home_user.id}_merged_pitcher_reports.pdf'))


def test_report_without_a_selection_is_rejected(archived_games, client):
    resp = client.post('/api/pitching/report', json={'content_hashes': [], 'target': 'own'})

    assert resp.status_code == 400


def test_report_rejects_a_game_outside_this_schools_archive(archived_games, client):
    resp = _report(client, hashes=['not-a-real-hash'])

    assert resp.status_code == 404


def test_report_with_no_pitchers_on_that_side_explains_why(client, login_as, make_school, make_user):
    """A school whose trackman_id matches nothing in the file has no own-team arms."""
    school = make_school(trackman_id='NOBODY')
    user = make_user(school)
    login_as(client, user)
    _save_game(client, GAME_1)

    resp = _report(client, target='own')

    assert resp.status_code == 404
    assert 'No pitching data' in resp.get_json()['error']


# --- export -----------------------------------------------------------------

def test_export_streams_a_single_pitcher_pdf(archived_games, client):
    _report(client)

    resp = client.get('/api/pitching/export?pitcher_id=1001')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')


def test_export_streams_the_merged_pdf(archived_games, client):
    _report(client)

    resp = client.get('/api/pitching/export?merged=1')

    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')


def test_export_before_generating_returns_404(archived_games, client):
    resp = client.get('/api/pitching/export?pitcher_id=1001')

    assert resp.status_code == 404


# --- practice files are still reportable ------------------------------------

def test_practice_games_can_still_be_reported_on(client, login_as, home_user):
    """The flag keeps a bullpen out of season stats, not out of the reports."""
    login_as(client, home_user)
    _save_game(client, GAME_1, practice=True)

    data = _report(client).get_json()

    assert len(data['reports']) == 1
