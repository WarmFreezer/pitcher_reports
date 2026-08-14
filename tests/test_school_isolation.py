"""
Verifies the school-scoped SaaS invariant from CLAUDE.md: a logged-in user must never
be able to see another school's data, regardless of which route or query path is used.
"""
import json
import os

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


def test_batting_hitters_only_lists_own_schools_archive(client, login_as, two_schools, app):
    """
    The game archive is keyed by school id on disk, so School B's saved games are in
    a directory School A's user never resolves. Seed one for B and confirm A sees none.
    """
    import json
    import os

    school_b = two_schools['school_b']
    games_dir = os.path.join(app.config['STORAGE'], 'schools', str(school_b.id), 'games')
    os.makedirs(games_dir, exist_ok=True)
    with open(os.path.join(games_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump([{
            'file': '2026-03-01_deadbeef.csv', 'date': '2026-03-01',
            'home_team': school_b.trackman_id, 'away_team': 'OTHER',
            'content_hash': 'deadbeef',
            'batters': [{'id': '777', 'name': 'Bravo Batter', 'team': school_b.trackman_id}],
        }], f)

    login_as(client, two_schools['user_a'])
    data = client.get('/api/batting/hitters?target=own').get_json()

    assert data['hitters'] == []
    assert data['game_count'] == 0
    assert 'Bravo Batter' not in json.dumps(data)


def test_batting_report_blocks_other_schools_batter(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.post('/api/batting/report', json={'batter_id': '777', 'target': 'own'})

    # No archive for School A at all, so this is refused before any batter lookup
    assert resp.status_code in (400, 404)
    assert 'Bravo' not in resp.get_data(as_text=True)


def test_pitching_games_only_lists_own_schools_archive(client, login_as, two_schools, app):
    """The archive is keyed by school id on disk, so B's games are in a directory
    A's user never resolves."""
    import json
    import os

    school_b = two_schools['school_b']
    games_dir = os.path.join(app.config['STORAGE'], 'schools', str(school_b.id), 'games')
    os.makedirs(games_dir, exist_ok=True)
    with open(os.path.join(games_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump([{
            'file': '2026-03-01_deadbeef.csv', 'date': '2026-03-01',
            'home_team': school_b.trackman_id, 'away_team': 'OTHER',
            'content_hash': 'deadbeef', 'practice': False,
            'batters': [], 'pitchers': [],
        }], f)

    login_as(client, two_schools['user_a'])
    data = client.get('/api/pitching/games').get_json()

    assert data['games'] == []
    assert data['game_count'] == 0


def test_pitching_report_blocks_another_schools_game(client, login_as, two_schools):
    login_as(client, two_schools['user_a'])

    resp = client.post('/api/pitching/report',
                       json={'content_hashes': ['deadbeef'], 'target': 'own'})

    assert resp.status_code == 404


# ── Slug -> school_id storage migration (docs/test-plan-slug-migration.md, category B) ────────


@pytest.fixture
def two_schools_same_slug(make_school, make_user, make_pitcher, make_outing, make_pitch_type, make_outing_pitch_stat):
    """
    Same shape as `two_schools`, but both schools share one slug. This is only
    constructible once `schools.slug` is no longer unique — until that DB-layer
    change lands, fixture setup itself raises IntegrityError, which is the
    expected signal that the migration's category-E step hasn't happened yet
    (see docs/test-plan-slug-migration.md).
    """
    school_a = make_school(name='School A', slug='shared-slug')
    school_b = make_school(name='School B', slug='shared-slug')
    user_a = make_user(school_a)
    user_b = make_user(school_b)

    pitcher_a = make_pitcher(school_a, name='Alpha Pitcher')
    pitcher_b = make_pitcher(school_b, name='Bravo Pitcher')

    outing_a = make_outing(pitcher_a)
    outing_b = make_outing(pitcher_b)

    pitch_type = make_pitch_type()
    make_outing_pitch_stat(pitcher_a, outing_a, pitch_type)
    make_outing_pitch_stat(pitcher_b, outing_b, pitch_type)

    return {
        'school_a': school_a, 'school_b': school_b,
        'user_a': user_a, 'user_b': user_b,
        'pitcher_a': pitcher_a, 'pitcher_b': pitcher_b,
    }


def _seed_pitching_game(app, school, batter_name):
    games_dir = os.path.join(app.config['STORAGE'], 'schools', str(school.id), 'games')
    os.makedirs(games_dir, exist_ok=True)
    with open(os.path.join(games_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump([{
            'file': '2026-03-01_deadbeef.csv', 'date': '2026-03-01',
            'home_team': school.trackman_id, 'away_team': 'OTHER',
            'content_hash': 'deadbeef', 'practice': False,
            'batters': [{'id': '777', 'name': batter_name, 'team': school.trackman_id}],
            'pitchers': [],
        }], f)


def test_own_schools_games_visible_via_id_keyed_storage(client, login_as, two_schools, app):
    """
    Target behavior once storage paths are keyed by school.id instead of
    school.slug. Fails against current code, which still resolves the games
    directory via current_user.school.slug (app/routes/utils.py:
    get_school_games_directory) -- that's expected until the storage-path
    migration (docs/test-plan-slug-migration.md, category B / phase 1c) lands.
    """
    school_a = two_schools['school_a']
    _seed_pitching_game(app, school_a, batter_name='Alpha Batter')

    login_as(client, two_schools['user_a'])
    data = client.get('/api/pitching/games').get_json()

    assert data['game_count'] == 1
    assert data['games'][0]['content_hash'] == 'deadbeef'


def test_same_slug_schools_do_not_leak_via_id_keyed_storage(client, login_as, two_schools_same_slug, app):
    """
    The critical collision-safety case this migration must guarantee: two
    schools sharing a slug must still resolve to distinct storage directories
    once keyed by id. Requires both the schools.slug unique constraint to be
    dropped (fixture setup fails otherwise) and the storage-path migration to
    be complete (assertions fail otherwise) -- only green once both steps of
    the migration have landed.
    """
    school_a = two_schools_same_slug['school_a']
    school_b = two_schools_same_slug['school_b']
    assert school_a.slug == school_b.slug  # the scenario this test exists to cover
    assert school_a.id != school_b.id

    _seed_pitching_game(app, school_b, batter_name='Bravo Batter')

    login_as(client, two_schools_same_slug['user_a'])
    data_a = client.get('/api/pitching/games').get_json()

    assert data_a['games'] == []
    assert data_a['game_count'] == 0
    assert 'Bravo Batter' not in json.dumps(data_a)

    client.get('/logout')  # /login redirects instead of switching users while already authenticated
    login_as(client, two_schools_same_slug['user_b'])
    data_b = client.get('/api/pitching/games').get_json()

    assert data_b['game_count'] == 1


@pytest.mark.parametrize('method,path', [
    ('GET', '/dashboard'),
    ('GET', '/account'),
    ('GET', '/upload'),
    ('GET', '/batting'),
    ('GET', '/api/batting/hitters'),
    ('GET', '/api/batting/export'),
    ('POST', '/api/batting/report'),
    ('GET', '/pitching'),
    ('GET', '/api/pitching/games'),
    ('GET', '/api/pitching/export'),
    ('POST', '/api/pitching/report'),
    ('GET', '/api/games'),
    ('DELETE', '/api/games/abc123'),
    ('GET', '/api/team/overview'),
    ('GET', '/api/pitcher/1/averages'),
    ('GET', '/subscription'),
    ('GET', '/api/subscription/roster'),
])
def test_login_required_routes_redirect_when_unauthenticated(client, method, path):
    resp = client.open(path, method=method, follow_redirects=False)

    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']
