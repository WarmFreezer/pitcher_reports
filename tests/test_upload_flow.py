import io
import os
from pathlib import Path

import pytest

from app.db.models import Outing, Pitcher

FIXTURE_PATH = Path(__file__).parent / 'fixtures' / 'sample_game.csv'


@pytest.fixture
def home_school(make_school):
    # trackman_id must match the fixture's PitcherTeam values so uploaded rows match
    return make_school(trackman_id='HOME')


@pytest.fixture
def home_user(make_user, home_school):
    return make_user(home_school)


def _upload(client, target='own', filename='sample_game.csv', content=None):
    content = content if content is not None else FIXTURE_PATH.read_bytes()
    return client.post(
        '/api/upload',
        data={'file': (io.BytesIO(content), filename), 'target': target},
        content_type='multipart/form-data',
    )


def test_upload_own_pitcher_generates_report(client, login_as, home_user, home_school, app):
    login_as(client, home_user)

    resp = _upload(client, target='own')
    data = resp.get_json()

    assert resp.status_code == 200, data
    assert data['num_reports'] == 1
    report = data['reports'][0]
    assert report['pitcher_name'] == 'Doe, John'

    reports_dir = os.path.join(app.config['STORAGE'], 'schools', home_school.slug, 'reports')
    pdf_path = os.path.join(reports_dir, f'{home_user.id}_pitcher_1001_report.pdf')
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 0

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', home_school.slug, 'temp')
    heatmap_path = os.path.join(temp_dir, f'{home_user.id}_pitcher_1001_heat_map_left_light.png')
    assert os.path.exists(heatmap_path)


def test_upload_opponent_pitcher_generates_report(client, login_as, home_user):
    login_as(client, home_user)

    resp = _upload(client, target='opponent')
    data = resp.get_json()

    assert resp.status_code == 200, data
    assert data['num_reports'] == 1
    assert data['reports'][0]['pitcher_name'] == 'Smith, Jane'


def test_upload_rejects_missing_file(client, login_as, home_user):
    login_as(client, home_user)

    resp = client.post('/api/upload', data={}, content_type='multipart/form-data')

    assert resp.status_code == 400
    assert 'No file part' in resp.get_json()['error']


def test_upload_own_target_with_no_matching_rows_returns_error(client, login_as, make_school, make_user):
    # School whose trackman_id matches nothing in the fixture file
    school = make_school(trackman_id='NOBODY')
    user = make_user(school)
    login_as(client, user)

    resp = _upload(client, target='own')

    assert resp.status_code == 400
    assert 'No pitching data found' in resp.get_json()['error']


def test_upload_opponent_target_with_no_matching_rows_returns_error(client, login_as, make_school, make_user):
    # If the school's trackman_id matches every PitcherTeam in the file, "opponent" finds nothing
    single_team_csv = FIXTURE_PATH.read_text().replace('AWAY', 'HOME')
    school = make_school(trackman_id='HOME')
    user = make_user(school)
    login_as(client, user)

    resp = _upload(client, target='opponent', content=single_team_csv.encode('utf-8'))

    assert resp.status_code == 400
    assert 'No opponent pitching data found' in resp.get_json()['error']


def test_upload_unsupported_extension_raises(client, login_as, home_user):
    # upload.py's own extension dispatch (before file_validator runs) raises an
    # uncaught ValueError for non csv/xlsx/xls files instead of returning a 400 —
    # documented here as current behavior rather than silently working around it.
    login_as(client, home_user)

    with pytest.raises(ValueError, match='Unsupported file format'):
        _upload(client, filename='sample_game.txt')


def test_save_game_persists_outings(client, login_as, home_user, home_school, app):
    login_as(client, home_user)
    _upload(client, target='own')

    resp = client.post('/api/save-game')
    assert resp.status_code == 200

    with app.app_context():
        outings = Outing.query.join(Pitcher, Outing.pitcher_id == Pitcher.id).filter(Pitcher.school_id == home_school.id).all()
        assert len(outings) >= 1
