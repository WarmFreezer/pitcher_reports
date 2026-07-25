"""
Verifies the school-scoped SaaS invariant from CLAUDE.md: a logged-in user must never
be able to see another school's data, regardless of which route or query path is used.
"""
import pytest


@pytest.fixture
def two_schools(make_school, make_user, make_pitcher, make_outing, make_pitch_type, make_outing_pitch_stat):
    school_a = make_school(name='School A')
    school_b = make_school(name='School B')
    user_a = make_user(school_a)

    pitcher_a = make_pitcher(school_a, name='Alpha Pitcher')
    pitcher_b = make_pitcher(school_b, name='Bravo Pitcher')

    outing_a = make_outing(pitcher_a)
    outing_b = make_outing(pitcher_b)

    pitch_type = make_pitch_type()
    make_outing_pitch_stat(pitcher_a, outing_a, pitch_type)
    make_outing_pitch_stat(pitcher_b, outing_b, pitch_type)

    return {
        'school_a': school_a, 'school_b': school_b, 'user_a': user_a,
        'pitcher_a': pitcher_a, 'pitcher_b': pitcher_b,
    }


def test_team_overview_excludes_other_schools_pitchers(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.get('/api/team/overview')
    data = resp.get_json()

    names = {row['pitcher_name'] for row in data}
    assert 'Alpha Pitcher' in names
    assert 'Bravo Pitcher' not in names


def test_pitcher_averages_blocks_other_schools_pitcher(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.get(f"/api/pitcher/{two_schools['pitcher_b'].id}/averages")

    assert resp.status_code == 404, (
        "GET /api/pitcher/<id>/averages does not filter by current_user.school_id "
        "(unlike its .../averages/download sibling) — School A can read School B's "
        "pitch stats by ID. See app/routes/pages.py:pitcher_averages."
    )


def test_pitcher_averages_download_blocks_other_schools_pitcher(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.get(f"/api/pitcher/{two_schools['pitcher_b'].id}/averages/download")

    assert resp.status_code == 404


def test_pitcher_averages_allows_own_schools_pitcher(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.get(f"/api/pitcher/{two_schools['pitcher_a'].id}/averages")

    assert resp.status_code == 200


@pytest.mark.parametrize('method,path', [
    ('GET', '/dashboard'),
    ('GET', '/account'),
    ('GET', '/upload'),
    ('GET', '/api/team/overview'),
    ('GET', '/api/pitcher/1/averages'),
    ('GET', '/subscription'),
    ('GET', '/api/subscription/roster'),
])
def test_login_required_routes_redirect_when_unauthenticated(client, method, path):
    resp = client.open(path, method=method, follow_redirects=False)

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
