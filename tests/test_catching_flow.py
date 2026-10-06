"""
End-to-end coverage for /catching: filtered, Plotly-drawn reports with an on-demand PDF.

The fixture is the pitching/hitting sample game with a catcher added to each row: HOME's
catcher (id 7) receives Doe's pitches and AWAY's (id 8) receives Smith's. Only pitches the
umpire called (BallCalled / StrikeCalled) are "taken" and count toward framing.
"""
import io
import json
import os
from pathlib import Path

import pandas as pd
import pytest

FIXTURES = Path(__file__).parent / 'fixtures'
GAME_1 = FIXTURES / 'sample_hitting_game_1.csv'   # 2026-03-01
GAME_2 = FIXTURES / 'sample_hitting_game_2.csv'   # 2026-03-08

OWN_CATCHER = '7'
OPP_CATCHER = '8'

PNG_1X1 = ('data:image/png;base64,'
           'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


@pytest.fixture
def home_school(make_school):
    return make_school(trackman_id='HOME')


@pytest.fixture
def home_user(make_user, home_school):
    return make_user(home_school)


def _with_catchers(path, tmp_path, name):
    """The sample game plus Catcher/CatcherId/CatcherTeam, with some called pitches mixed in."""
    df = pd.read_csv(path)
    own = df['PitcherTeam'] == 'HOME'
    df['CatcherId'] = own.map({True: int(OWN_CATCHER), False: int(OPP_CATCHER)})
    df['Catcher'] = own.map({True: 'Gamma, Gus', False: 'Delta, Dan'})
    df['CatcherTeam'] = own.map({True: 'HOME', False: 'AWAY'})
    out = tmp_path / name
    df.to_csv(out, index=False)
    return out


def _save_game(client, path):
    resp = client.post('/api/upload', data={'file': (io.BytesIO(path.read_bytes()), path.name), 'target': 'own'},
                       content_type='multipart/form-data')
    assert resp.status_code == 200, resp.get_json()
    resp = client.post('/api/save-game')
    assert resp.status_code == 200, resp.get_json()


@pytest.fixture
def archived_games(client, login_as, home_user, tmp_path):
    login_as(client, home_user)
    _save_game(client, _with_catchers(GAME_1, tmp_path, 'g1.csv'))
    _save_game(client, _with_catchers(GAME_2, tmp_path, 'g2.csv'))
    return home_user


def _report(client, ids=(OPP_CATCHER,), target='opponent', **extra):
    return client.post('/api/catching/report', json={'catcher_ids': list(ids), 'target': target, **extra})


def _report_data(client, **kw):
    resp = _report(client, **kw)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    out = {'reports': [], 'meta': {}, 'done': {}}
    for line in resp.get_data(as_text=True).splitlines():
        if line.strip():
            msg = json.loads(line)
            if msg['type'] == 'report':
                out['reports'].append(msg)
            elif msg['type'] == 'meta':
                out['meta'] = msg
            elif msg['type'] == 'done':
                out['done'] = msg
    return out


def _card(client, **extra):
    return client.post('/api/catching/catcher', json={'catcher_id': OPP_CATCHER, 'target': 'opponent', **extra})


def _export(client, catchers, target='opponent', **extra):
    return client.post('/api/catching/export', json={'target': target, 'catchers': catchers, **extra})


def _points(figure):
    return sum(len(t['x']) for t in figure['data'] if t.get('type') == 'scatter' and t.get('showlegend') is not True)


# --- listing ----------------------------------------------------------------

def test_catchers_endpoint_lists_each_side(archived_games, client):
    own = client.get('/api/catching/catchers?target=own').get_json()['catchers']
    opp = client.get('/api/catching/catchers?target=opponent').get_json()['catchers']

    assert [c['id'] for c in own] == [OWN_CATCHER]
    assert [c['id'] for c in opp] == [OPP_CATCHER]


# --- report cards -----------------------------------------------------------

def test_cards_carry_both_plotly_figures_and_the_framing_table(archived_games, client):
    card = _report_data(client)['reports'][0]

    assert card['catcher_name'] == 'Delta, Dan'
    assert set(card['figures']) == {'heat_map', 'pitch_location'}
    assert card['framing_table']
    assert not any(key.endswith('_url') for key in card)


def test_every_taken_pitch_is_on_the_location_chart(archived_games, client):
    figures = _report_data(client)['reports'][0]['figures']

    # Smith's pitches the umpire called across both games: two balls on 03-01, one on 03-08
    assert _points(figures['pitch_location']) == 3


def test_meta_offers_framing_pitch_type_and_velocity_and_defaults_to_framing(archived_games, client):
    meta = _report_data(client)['meta']

    assert meta['color_modes'] == ['framing', 'pitch_type', 'velo']
    assert meta['defaults']['color_by'] == 'framing'
    assert [t['name'] for t in meta['pitch_types']]


def test_account_color_default_does_not_override_framing(archived_games, client, home_user):
    from app.db.models import db
    home_user.chart_color_mode = 'velo'
    db.session.commit()

    assert _report_data(client)['meta']['defaults']['color_by'] == 'framing'


def test_filters_narrow_the_cards_numbers(archived_games, client):
    everything = _report_data(client)['reports'][0]
    sliders = _report_data(client, filters={'pitch_types': ['Slider']})['reports'][0]

    assert _points(sliders['figures']['pitch_location']) < _points(everything['figures']['pitch_location'])


def test_a_velo_range_nobody_threw_is_an_empty_card(archived_games, client):
    data = _report_data(client, filters={'velo': [95, 99]})

    assert data['done']['failed'] == []
    assert data['reports'][0]['empty'] is True


def test_malformed_filters_and_options_are_rejected(archived_games, client):
    for bad in ({'pitch_types': 'x'}, {'velo': [1]}, 'x'):
        assert _report(client, filters=bad).status_code == 400
    assert _report(client, view='3d').status_code == 400
    assert _report(client, color_by='spin').status_code == 400


def test_unknown_catcher_and_empty_selection(archived_games, client):
    assert _report(client, ids=['999999']).status_code == 404
    assert _report(client, ids=[]).status_code == 400


def test_the_wrong_side_is_not_found(archived_games, client):
    assert _report(client, ids=[OWN_CATCHER], target='opponent').status_code == 404


# --- single card -----------------------------------------------------------

def test_catcher_endpoint_rebuilds_one_card(archived_games, client):
    card = _card(client, filters={'pitch_types': ['Slider']}).get_json()

    assert card['catcher_id'] == OPP_CATCHER and 'framing_table' in card


def test_catcher_endpoint_charts_only_skips_the_table(archived_games, client):
    card = _card(client, charts_only=True, view='scatter', color_by='pitch_type').get_json()

    assert 'figures' in card and 'framing_table' not in card
    for figure in card['figures'].values():
        assert {t['type'] for t in figure['data']} <= {'scatter'}


def test_catcher_endpoint_404s_outside_the_archive(archived_games, client):
    assert client.post('/api/catching/catcher', json={'catcher_id': '999999', 'target': 'opponent'}).status_code == 404
    assert client.post('/api/catching/catcher', json={'target': 'opponent'}).status_code == 400


# --- export -----------------------------------------------------------------

def test_export_builds_a_pdf(archived_games, client):
    resp = _export(client, [{'catcher_id': OPP_CATCHER, 'images': {'heat_map': PNG_1X1, 'pitch_location': PNG_1X1}}])

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')


def test_export_applies_the_filters(archived_games, client):
    resp = _export(client, [{'catcher_id': OPP_CATCHER}], filters={'velo': [95, 99]})

    assert resp.status_code == 404


def test_export_rejects_bad_images_unknown_catchers_and_empty_requests(archived_games, client):
    assert _export(client, [{'catcher_id': OPP_CATCHER, 'images': {'heat_map': 'data:image/png;base64,AAAA'}}]).status_code == 400
    assert _export(client, [{'catcher_id': '999999'}]).status_code == 404
    assert _export(client, []).status_code == 400


def test_export_leaves_no_working_files(archived_games, client, app, home_school):
    _export(client, [{'catcher_id': OPP_CATCHER, 'images': {'heat_map': PNG_1X1}}])

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert [f for f in os.listdir(temp_dir) if '_export_' in f or f.endswith(('.png', '.pdf'))] == []


def test_export_merges_two_catchers(archived_games, client):
    # Both teams' catchers can only be reached from their own side, so merge by repeating one.
    resp = _export(client, [{'catcher_id': OPP_CATCHER}, {'catcher_id': OPP_CATCHER}])

    assert resp.status_code == 200
