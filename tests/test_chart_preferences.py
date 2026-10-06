"""The account's chart defaults: scatter/heatmap (chart_style) and color-by (chart_color_mode)."""
import pytest

from app.db.models import db


@pytest.fixture
def signed_in(client, login_as, make_school, make_user):
    user = make_user(make_school())
    login_as(client, user)
    return user


def test_color_mode_defaults_to_pitch_type(signed_in):
    assert signed_in.chart_color_mode == 'pitch_type'


def test_saving_the_color_mode_persists_it(client, signed_in):
    resp = client.post('/api/account/preferences', json={'chart_color_mode': 'velo'})

    assert resp.status_code == 200
    db.session.refresh(signed_in)
    assert signed_in.chart_color_mode == 'velo'


def test_rejects_an_unknown_color_mode(client, signed_in):
    resp = client.post('/api/account/preferences', json={'chart_color_mode': 'spin'})

    assert resp.status_code == 400
    db.session.refresh(signed_in)
    assert signed_in.chart_color_mode == 'pitch_type'


def test_preferences_are_independent(client, signed_in):
    client.post('/api/account/preferences', json={'chart_color_mode': 'velo'})
    client.post('/api/account/preferences', json={'chart_style': 'pitch_point'})

    db.session.refresh(signed_in)
    assert (signed_in.chart_style, signed_in.chart_color_mode) == ('pitch_point', 'velo')


def test_account_page_reflects_the_saved_defaults(client, signed_in):
    signed_in.chart_color_mode = 'velo'
    db.session.commit()

    html = client.get('/account').get_data(as_text=True)

    assert 'id="chart-color-toggle"' in html
    assert 'id="chart-color-toggle" class="switch-input" checked' in html
