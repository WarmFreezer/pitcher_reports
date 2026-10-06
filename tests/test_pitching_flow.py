"""
End-to-end coverage for /pitching.

Games reach the archive through /api/upload + /api/save-game, so these drive the
same path a user does. Unlike the old flow, no report exists until a game is saved.

Both fixture games are HOME vs AWAY with Doe (1001) pitching for HOME and Smith
(2002) for AWAY, so target='own' yields one pitcher and 'opponent' the other.
"""
import io
import json
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


def _report(client, hashes=None, target='own', **extra):
    if hashes is None:
        hashes = _hashes(client)
    return client.post('/api/pitching/report',
                       json={'content_hashes': hashes, 'target': target, **extra})


def _report_data(client, hashes=None, target='own', **extra):
    """
    /api/pitching/report streams one NDJSON line per pitcher (built in parallel)
    plus a final 'done' summary line, instead of one JSON blob -- reconstruct the
    old single-dict shape so the assertions below don't need to know that.
    """
    resp = _report(client, hashes=hashes, target=target, **extra)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    reports = []
    done = {}
    meta = {}
    for line in resp.get_data(as_text=True).splitlines():
        if not line.strip():
            continue
        msg = json.loads(line)
        if msg['type'] == 'report':
            reports.append(msg)
        elif msg['type'] == 'done':
            done = msg
        elif msg['type'] == 'meta':
            meta = msg

    return {
        'reports': reports,
        'meta': meta,
        'failed': done.get('failed', []),
        'date_range': done.get('date_range'),
        'opponent': done.get('opponent'),
        'games': done.get('games'),
    }


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
    data = _report_data(client)

    assert len(data['reports']) == 1
    assert data['reports'][0]['pitcher_name'] == 'Doe, John'
    assert data['failed'] == []
    assert data['games'] == 2


def test_opponent_target_reports_the_other_dugout(archived_games, client):
    data = _report_data(client, target='opponent')

    assert [r['pitcher_name'] for r in data['reports']] == ['Smith, Jane']


def test_selecting_one_game_narrows_the_range_in_the_header(archived_games, client):
    one = _hashes(client, start_date='2026-03-01', end_date='2026-03-01')

    data = _report_data(client, hashes=one)

    assert data['games'] == 1
    assert data['date_range'] == '03/01/2026'


def test_multi_game_selection_spans_the_dates(archived_games, client):
    data = _report_data(client)

    assert data['date_range'] == '03/01/2026 - 03/08/2026'


def test_report_cards_carry_plotly_figures_not_image_urls(archived_games, client):
    card = _report_data(client)['reports'][0]

    assert set(card['figures']) == {'heat_left', 'heat_right', 'break'}
    for figure in card['figures'].values():
        assert set(figure) == {'data', 'layout'}
    assert not any(key.endswith('_url') and 'map' in key for key in card)


def test_report_writes_no_chart_images_or_pdfs(archived_games, client, app, home_school):
    _report_data(client)

    school_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id))
    for sub in ('temp', 'reports'):
        folder = os.path.join(school_dir, sub)
        generated = [f for f in os.listdir(folder) if f.endswith(('.png', '.pdf'))] if os.path.isdir(folder) else []
        assert generated == []


def test_report_meta_describes_the_filter_bar(archived_games, client):
    meta = _report_data(client, target='opponent')['meta']

    assert [t['name'] for t in meta['pitch_types']] == ['Fastball', 'Slider', 'ChangeUp']
    assert meta['velo_min'] == 89 and meta['velo_max'] == 89
    assert meta['defaults'] == {'view': 'heatmap', 'color_by': 'pitch_type'}


def test_report_meta_defaults_follow_the_account_settings(archived_games, client, home_user):
    from app.db.models import db
    home_user.chart_style = 'pitch_point'
    home_user.chart_color_mode = 'velo'
    db.session.commit()

    meta = _report_data(client)['meta']

    assert meta['defaults'] == {'view': 'scatter', 'color_by': 'velo'}


def test_report_filters_change_the_stat_tables(archived_games, client):
    everything = _report_data(client, target='opponent')['reports'][0]
    sliders = _report_data(
        client, target='opponent', filters={'pitch_types': ['Slider']})['reports'][0]

    assert 'Fastball' not in sliders['pitcher_table']
    assert sliders['pitcher_table'] != everything['pitcher_table']
    assert sliders['pitch_count'] == 4   # the four sliders Smith threw in game 1
    assert everything['pitch_count'] == 13


def test_report_with_a_velo_range_nobody_threw_is_an_empty_card(archived_games, client):
    data = _report_data(client, target='opponent', filters={'velo': [95, 99]})

    assert data['failed'] == []
    assert data['reports'][0]['empty'] is True


def test_report_rejects_malformed_filters(archived_games, client):
    for bad in ({'pitch_types': 'Slider'}, {'velo': [1]}, {'velo': ['a', 'b']}, 'x'):
        resp = _report(client, filters=bad)
        assert resp.status_code == 400, bad


def test_report_rejects_unknown_chart_options(archived_games, client):
    assert _report(client, view='3d').status_code == 400
    assert _report(client, color_by='spin').status_code == 400


# --- single-card refresh ----------------------------------------------------

def _card(client, **extra):
    body = {'content_hashes': _hashes(client), 'target': 'opponent', 'pitcher_id': 2002, **extra}
    return client.post('/api/pitching/pitcher', json=body)


def test_pitcher_endpoint_rebuilds_one_card_for_new_filters(archived_games, client):
    resp = _card(client, filters={'pitch_types': ['Slider']})

    assert resp.status_code == 200
    card = resp.get_json()
    assert card['pitcher_id'] == '2002'
    assert card['pitch_count'] == 4
    assert 'pitcher_table' in card


def test_pitcher_endpoint_charts_only_skips_the_tables(archived_games, client):
    card = _card(client, charts_only=True, view='scatter', color_by='velo').get_json()

    assert 'figures' in card
    assert 'pitcher_table' not in card


def test_pitcher_endpoint_scatter_view_draws_only_points(archived_games, client):
    card = _card(client, charts_only=True, view='scatter').get_json()

    for figure in card['figures'].values():
        assert {t['type'] for t in figure['data']} <= {'scatter'}


def test_pitcher_endpoint_404s_for_a_pitcher_on_the_other_side(archived_games, client):
    resp = client.post('/api/pitching/pitcher', json={
        'content_hashes': _hashes(client), 'target': 'own', 'pitcher_id': 2002})

    assert resp.status_code == 404


def test_pitcher_endpoint_rejects_a_game_outside_this_archive(archived_games, client):
    resp = client.post('/api/pitching/pitcher', json={
        'content_hashes': ['nope'], 'target': 'own', 'pitcher_id': 1001})

    assert resp.status_code == 404


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

# A 1x1 PNG: valid, tiny, and enough for ReportLab to place.
PNG_1X1 = ('data:image/png;base64,'
           'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def _export(client, pitchers, target='own', **extra):
    body = {'content_hashes': _hashes(client), 'target': target, 'pitchers': pitchers, **extra}
    return client.post('/api/pitching/export', json=body)


def test_export_builds_a_single_pitcher_pdf(archived_games, client):
    resp = _export(client, [{'pitcher_id': 1001, 'images': {
        'heat_left': PNG_1X1, 'heat_right': PNG_1X1, 'break': PNG_1X1}}])

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')
    assert 'pitcher_1001_report.pdf' in resp.headers['Content-Disposition']


def test_export_without_images_still_builds_the_tables(archived_games, client):
    resp = _export(client, [{'pitcher_id': 1001}])

    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')


def test_export_merges_several_pitchers_into_one_pdf(client, login_as, home_user, tmp_path):
    """Relabel the away arm as HOME so the own side has two pitchers to merge."""
    login_as(client, home_user)
    both_home = tmp_path / 'both_home.csv'
    both_home.write_text(GAME_1.read_text().replace(',AWAY,HOME,2026', ',HOME,AWAY,2026'))
    _save_game(client, both_home)

    resp = _export(client, [{'pitcher_id': 1001}, {'pitcher_id': 2002}])

    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')
    assert 'pitcher_reports.pdf' in resp.headers['Content-Disposition']


def test_export_applies_the_filters_to_the_pdf(archived_games, client):
    resp = _export(client, [{'pitcher_id': 2002}], target='opponent',
                   filters={'velo': [95, 99]})

    assert resp.status_code == 404
    assert 'No pitches match' in resp.get_json()['error']


def test_export_rejects_an_image_that_is_not_a_png(archived_games, client):
    resp = _export(client, [{'pitcher_id': 1001, 'images': {'break': 'data:image/png;base64,AAAA'}}])

    assert resp.status_code == 400


def test_export_rejects_a_non_png_data_url(archived_games, client):
    resp = _export(client, [{'pitcher_id': 1001, 'images': {'break': 'data:image/svg+xml;base64,AAAA'}}])

    assert resp.status_code == 400


def test_export_ignores_slots_it_does_not_know(archived_games, client, app, home_school):
    resp = _export(client, [{'pitcher_id': 1001, 'images': {'../../evil': PNG_1X1}}])

    assert resp.status_code == 200
    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert not any('evil' in f for f in os.listdir(temp_dir))


def test_export_rejects_a_pitcher_from_the_other_dugout(archived_games, client):
    assert _export(client, [{'pitcher_id': 2002}], target='own').status_code == 404


def test_export_requires_pitchers(archived_games, client):
    assert _export(client, []).status_code == 400
    assert _export(client, 'all').status_code == 400


def test_export_rejects_a_game_outside_this_archive(archived_games, client):
    resp = client.post('/api/pitching/export', json={
        'content_hashes': ['nope'], 'target': 'own', 'pitchers': [{'pitcher_id': 1001}]})

    assert resp.status_code == 404


def test_export_leaves_no_working_files_behind(archived_games, client, app, home_school):
    _export(client, [{'pitcher_id': 1001, 'images': {'break': PNG_1X1}}])

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert [f for f in os.listdir(temp_dir) if '_export_' in f or f.endswith(('.png', '.pdf'))] == []


def test_a_second_export_can_run_right_after_the_first(archived_games, client):
    """Each export has its own working directory, so nothing from one can block the next."""
    for _ in range(2):
        assert _export(client, [{'pitcher_id': 1001, 'images': {'break': PNG_1X1}}]).status_code == 200


def test_a_pdf_that_fails_to_build_is_a_server_error_not_no_matches(archived_games, client, monkeypatch):
    from app.services.report_lab_generator import PDF_Generator

    def boom(self, data, output_path):
        raise RuntimeError('layout blew up')

    monkeypatch.setattr(PDF_Generator, 'generate_pitcher_report', boom)

    resp = _export(client, [{'pitcher_id': 1001}])

    assert resp.status_code == 500
    assert resp.get_json()['error'] == 'Could not build the PDF.'


def test_old_get_export_is_gone(archived_games, client):
    assert client.get('/api/pitching/export?pitcher_id=1001').status_code == 405


# --- pitch-by-pitch ---------------------------------------------------------

def _pbp_query(client, target='own', **extra):
    from urllib.parse import urlencode
    pairs = [('target', target), *[('content_hash', h) for h in _hashes(client)],
             *[(k, v) for k, v in extra.items()]]
    return urlencode(pairs)


def test_pitch_by_pitch_streams_one_pitchers_pdf(archived_games, client):
    resp = client.get(f'/api/pitching/pitch-by-pitch?pitcher_id=1001&{_pbp_query(client)}')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')


def test_pitch_by_pitch_writes_no_chart_images(archived_games, client, app, home_school):
    client.get(f'/api/pitching/pitch-by-pitch?pitcher_id=1001&{_pbp_query(client)}')

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert [f for f in os.listdir(temp_dir) if f.endswith('.png')] == []


def test_pitch_by_pitch_honors_the_filters(archived_games, client):
    nothing = json.dumps({'velo': [95, 99]})

    resp = client.get(f'/api/pitching/pitch-by-pitch?pitcher_id=2002&{_pbp_query(client, "opponent", filters=nothing)}')

    assert resp.status_code == 404   # no pitch passes, so there is nothing to chart


def test_pitch_by_pitch_rejects_malformed_filters(archived_games, client):
    resp = client.get(f'/api/pitching/pitch-by-pitch?pitcher_id=1001&{_pbp_query(client, filters="{nope")}')

    assert resp.status_code == 400


def test_pitch_by_pitch_all_merges_the_staff(client, login_as, home_user, tmp_path):
    """Relabel the away arm as HOME so the own side has two pitchers to merge."""
    login_as(client, home_user)
    both_home = tmp_path / 'both_home.csv'
    both_home.write_text(GAME_1.read_text().replace(',AWAY,HOME,2026', ',HOME,AWAY,2026'))
    _save_game(client, both_home)

    resp = client.get(f'/api/pitching/pitch-by-pitch/all?{_pbp_query(client)}')

    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')
    assert 'pitch_by_pitch_reports.pdf' in resp.headers['Content-Disposition']


def test_pitch_by_pitch_all_with_no_matching_pitches_is_an_error(archived_games, client):
    nothing = json.dumps({'velo': [95, 99]})

    resp = client.get(f'/api/pitching/pitch-by-pitch/all?{_pbp_query(client, filters=nothing)}')

    assert resp.status_code == 404


# --- practice files are still reportable ------------------------------------

def test_practice_games_can_still_be_reported_on(client, login_as, home_user):
    """The flag keeps a bullpen out of season stats, not out of the reports."""
    login_as(client, home_user)
    _save_game(client, GAME_1, practice=True)

    data = _report_data(client)

    assert len(data['reports']) == 1
