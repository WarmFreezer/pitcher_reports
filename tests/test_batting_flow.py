"""
End-to-end coverage for the /batting date-ranged hitting reports.

Games reach the archive through /api/save-game, so these tests drive the same path a
user does: upload, save, then query. BATTER_ID bats for HOME, which is the school's
own team, so target='own' is the relevant filter.

The fixtures give batter 500 five batted balls total: three on 2026-03-01 (a line
single, a ground out, and a home run, all vs RHP) and two on 2026-03-08 (a double
and a ground out, both vs LHP). Several assertions below depend on that split.
"""
import io
import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / 'fixtures'
GAME_1 = FIXTURES / 'sample_hitting_game_1.csv'   # 2026-03-01, vs RHP
GAME_2 = FIXTURES / 'sample_hitting_game_2.csv'   # 2026-03-08, vs LHP

BATTER_ID = '500'
BATTER_NAME = 'Alpha, Adam'


@pytest.fixture
def home_school(make_school):
    # trackman_id must match the fixture's team codes so own/opponent filtering works
    return make_school(trackman_id='HOME')


@pytest.fixture
def home_user(make_user, home_school):
    return make_user(home_school)


def _save_game(client, path):
    """Upload a game then persist it, which is what puts it in the archive."""
    resp = client.post(
        '/api/upload',
        data={'file': (io.BytesIO(path.read_bytes()), path.name), 'target': 'own'},
        content_type='multipart/form-data',
    )
    assert resp.status_code == 200, resp.get_json()
    resp = client.post('/api/save-game')
    assert resp.status_code == 200, resp.get_json()


@pytest.fixture
def archived_games(client, login_as, home_user):
    login_as(client, home_user)
    _save_game(client, GAME_1)
    _save_game(client, GAME_2)
    return home_user


def _games_dir(app, school):
    return os.path.join(app.config['STORAGE'], 'schools', str(school.id), 'games')


def _report(client, **overrides):
    payload = {'batter_ids': [BATTER_ID], 'target': 'own'}
    payload.update(overrides)
    return client.post('/api/batting/report', json=payload)


def _first_report(resp):
    reports = resp.get_json()['reports']
    assert len(reports) == 1, reports
    return reports[0]


# --- archive ---------------------------------------------------------------

def test_save_game_archives_file_and_indexes_it(archived_games, app, home_school):
    from app.services import game_archive

    manifest = game_archive.read_manifest(_games_dir(app, home_school))

    assert len(manifest) == 2
    assert [entry['date'] for entry in manifest] == ['2026-03-01', '2026-03-08']
    for entry in manifest:
        assert os.path.exists(os.path.join(_games_dir(app, home_school), entry['file']))
        assert any(b['id'] == BATTER_ID for b in entry['batters'])


def test_saving_the_same_game_twice_does_not_duplicate(client, login_as, home_user, home_school, app):
    from app.services import game_archive

    login_as(client, home_user)
    _save_game(client, GAME_1)
    _save_game(client, GAME_1)

    assert len(game_archive.read_manifest(_games_dir(app, home_school))) == 1


# --- A1: manifest schema ---------------------------------------------------

def test_manifest_records_batted_ball_counts_per_batter(archived_games, app, home_school):
    """A1: the checkbox list needs batted-ball counts without opening any CSV."""
    from app.services import game_archive

    manifest = game_archive.read_manifest(_games_dir(app, home_school))
    by_date = {entry['date']: entry for entry in manifest}

    def batted(entry):
        return next(b for b in entry['batters'] if b['id'] == BATTER_ID)['batted_balls']

    assert batted(by_date['2026-03-01']) == 3
    assert batted(by_date['2026-03-08']) == 2


def test_manifest_defaults_practice_to_false(archived_games, app, home_school):
    """A1: the practice flag lands in the same schema pass."""
    from app.services import game_archive

    for entry in game_archive.read_manifest(_games_dir(app, home_school)):
        assert entry.get('practice') is False


# --- A1: date-filtered hitter listing --------------------------------------

def test_list_hitters_counts_batted_balls_within_range(archived_games, app, home_school):
    from app.services import game_archive

    games_dir = _games_dir(app, home_school)

    full = game_archive.list_hitters(games_dir, 'HOME', 'own')
    one_game = game_archive.list_hitters(
        games_dir, 'HOME', 'own', start_date='2026-03-01', end_date='2026-03-01')

    assert next(h for h in full if h['id'] == BATTER_ID)['batted_balls'] == 5
    assert next(h for h in one_game if h['id'] == BATTER_ID)['batted_balls'] == 3
    assert next(h for h in one_game if h['id'] == BATTER_ID)['games'] == 1


def test_list_hitters_batted_only_drops_hitters_with_no_contact(archived_games, app, home_school):
    """
    Zulu only ever takes strikes, so he has nothing to plot and must not reach
    the checkbox list. Checked from HOME's perspective, where he is an opponent.
    """
    from app.services import game_archive

    games_dir = _games_dir(app, home_school)

    everyone = game_archive.list_hitters(games_dir, 'HOME', 'opponent')
    with_contact = game_archive.list_hitters(games_dir, 'HOME', 'opponent', batted_only=True)

    assert 'Zulu, Zed' in {h['name'] for h in everyone}, 'fixture should include a no-contact batter'
    assert 'Zulu, Zed' not in {h['name'] for h in with_contact}
    assert 'Yankee, Yuri' in {h['name'] for h in with_contact}
    assert all(h['batted_balls'] > 0 for h in with_contact)


def test_list_hitters_batted_only_sums_across_the_range_before_filtering(archived_games, app, home_school):
    """
    A hitter can go without contact in one game and still belong in the list.
    Filtering per game rather than on the total would drop them and undercount
    everyone else's game counts.
    """
    from app.services import game_archive

    games_dir = _games_dir(app, home_school)
    hitters = game_archive.list_hitters(
        games_dir, 'HOME', 'own',
        start_date='2026-03-01', end_date='2026-03-08', batted_only=True)

    alpha = next(h for h in hitters if h['id'] == BATTER_ID)
    assert alpha['batted_balls'] == 5
    assert alpha['games'] == 2


def test_list_hitters_empty_range_returns_nothing(archived_games, app, home_school):
    from app.services import game_archive

    out_of_range = game_archive.list_hitters(
        _games_dir(app, home_school), 'HOME', 'own',
        start_date='2026-01-01', end_date='2026-01-31', batted_only=True)

    assert out_of_range == []


def test_hitters_endpoint_lists_own_batters_with_bounds(archived_games, client):
    data = client.get('/api/batting/hitters?target=own').get_json()

    assert data['game_count'] == 2
    assert data['first_date'] == '2026-03-01'
    assert data['last_date'] == '2026-03-08'

    hitter = next(h for h in data['hitters'] if h['id'] == BATTER_ID)
    assert hitter['name'] == BATTER_NAME
    assert hitter['games'] == 2
    assert hitter['batted_balls'] == 5


def test_hitters_endpoint_honors_the_date_range(archived_games, client):
    data = client.get(
        '/api/batting/hitters?target=own&start_date=2026-03-08&end_date=2026-03-08'
    ).get_json()

    hitter = next(h for h in data['hitters'] if h['id'] == BATTER_ID)
    assert hitter['games'] == 1
    assert hitter['batted_balls'] == 2


def test_hitters_endpoint_separates_own_from_opponent(archived_games, client):
    own = {h['id'] for h in client.get('/api/batting/hitters?target=own').get_json()['hitters']}
    opponent = {h['id'] for h in client.get('/api/batting/hitters?target=opponent').get_json()['hitters']}

    assert BATTER_ID in own
    assert BATTER_ID not in opponent
    assert own.isdisjoint(opponent)


# --- report ----------------------------------------------------------------

def test_report_over_full_range_aggregates_both_games(archived_games, client):
    report = _first_report(_report(client))

    assert report['hitter_name'] == BATTER_NAME
    assert report['games'] == 2
    # 5 PA in game one plus 2 in game two; the walk is not an at bat
    assert report['summary']['PA'] == '7'
    assert report['summary']['AB'] == '6'
    assert report['summary']['H'] == '3'
    assert report['summary']['AVG'] == '.500'
    assert report['summary']['HR'] == '1'
    assert report['summary']['2B'] == '1'


def test_date_range_narrows_to_a_single_game(archived_games, client):
    report = _first_report(_report(client, start_date='2026-03-01', end_date='2026-03-01'))

    assert report['games'] == 1
    assert report['summary']['PA'] == '5'
    assert report['summary']['AB'] == '4'
    # The double happens in game two, which this range excludes
    assert report['summary']['2B'] == '0'


def test_range_covering_no_games_returns_404_not_500(archived_games, client):
    resp = _report(client, start_date='2026-01-01', end_date='2026-01-31')

    assert resp.status_code == 404


def test_report_generates_both_themes_of_both_spray_charts(archived_games, client, app, home_school, home_user):
    report = _first_report(_report(client))

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    for side in ('left', 'right'):
        for theme in ('light', 'dark'):
            name = f'{home_user.id}_hitter_{BATTER_ID}_spray_{side}_{theme}.png'
            assert os.path.exists(os.path.join(temp_dir, name)), f'missing {name}'
            assert os.path.getsize(os.path.join(temp_dir, name)) > 0

    # The page needs both theme URLs so core.js can swap them on toggle
    assert report['spray_left_url'].endswith('_left_light.png')
    assert report['spray_left_dark_url'].endswith('_left_dark.png')


def test_report_includes_rendered_tables(archived_games, client):
    report = _first_report(_report(client))

    assert 'Ground' in report['batted_ball_table']
    assert 'Line' in report['batted_ball_table']
    # Plate discipline is keyed by the shared pitch-order abbreviations
    assert 'FB' in report['discipline_table']
    assert 'Chase' in report['discipline_table']


def test_report_without_any_hitter_is_rejected(archived_games, client):
    resp = client.post('/api/batting/report', json={'target': 'own', 'batter_ids': []})

    assert resp.status_code == 400


def test_report_rejects_a_batter_outside_this_schools_archive(archived_games, client):
    resp = _report(client, batter_ids=['999999'])

    assert resp.status_code == 404


# --- discipline table ------------------------------------------------------

def _discipline(**columns):
    """One batter's pitches straight into the table, bypassing the archive."""
    import pandas as pd
    from app.services.hitter_report import build_hitter_discipline_table

    rows = pd.DataFrame({'BatterId': [1] * len(columns['PitchCall']), **columns})
    return build_hitter_discipline_table(rows, 1)


def test_discipline_table_keeps_pitch_types_outside_the_shared_order():
    """
    A tag with no pitch_order entry must keep its own label. Dropping it from the
    sort order would lose which pitch a row's numbers describe.
    """
    table = _discipline(
        TaggedPitchType=['Fastball', 'Sweeper'],
        PitchCall=['StrikeCalled', 'StrikeCalled'],
        PlateLocSide=[0.0, 0.0],
        PlateLocHeight=[2.5, 2.5],
    )

    assert [row.pitch_type for row in table.rows] == ['FB', 'Sweeper'], 'unknown tags sort after known ones'
    sweeper = next(row for row in table.rows if row.pitch_type == 'Sweeper')
    assert sweeper.seen == 1


def test_zone_and_chase_ignore_pitches_with_no_tracked_location():
    """
    An untracked location is not evidence of a pitch off the plate. Counting it as
    out of zone would deflate Zone% and inflate the chase denominator, and a swing
    at one would post as a chase.

    Four fastballs: one in the zone, two off the plate (one of them chased), and
    one with no location that the batter swung at.
    """
    import numpy as np

    table = _discipline(
        TaggedPitchType=['Fastball'] * 4,
        PitchCall=['StrikeCalled', 'BallCalled', 'StrikeSwinging', 'StrikeSwinging'],
        PlateLocSide=[0.0, 2.0, 2.0, np.nan],
        PlateLocHeight=[2.5, 2.5, 2.5, np.nan],
    )
    row = table.rows[0]

    assert row.zone_pct == pytest.approx(33.333, abs=0.01), '1 of 3 located pitches, not 1 of 4 seen'
    assert row.chase_pct == 50.0, '1 chase of 2 located pitches out of the zone'

    # Rates that do not depend on location still cover every pitch seen
    assert row.seen == 4
    assert row.swing_pct == 50.0


# --- tier-3 custom hitter report --------------------------------------------

def test_custom_collectors_return_none_without_a_school_script(monkeypatch):
    """No custom_hitter_report.py on disk -> every tier-3 collector is a silent no-op."""
    import pandas as pd
    from app.services import hitter_report

    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: None)

    source = pd.DataFrame({'BatterId': [1]})
    assert hitter_report.custom_stats_table(source, 1, 999) is None
    assert hitter_report.custom_hit_type_stats_table(source, 1, 999) is None
    assert hitter_report.custom_pitch_type_stats_table(source, 1, 999) is None
    assert hitter_report.custom_charts(source, 1, 999, 1, str(FIXTURES)) is None


def test_custom_collectors_wire_a_schools_hooks_through(monkeypatch, tmp_path):
    """
    A school's custom_hitter_report.py hooks land in the typed tables the PDF
    renders -- get_stats -> CustomStatsTable, get_hit_type_stats ->
    CustomHitTypeStatsTable, get_pitch_type_stats -> CustomPitchTypeStatsTable,
    get_charts -> (title, path) pairs with the file actually written to disk.
    """
    import types
    import pandas as pd
    from app.services import hitter_report
    from app.services.pitch_stats import CustomStat, CustomPitchTypeStat, CustomPitchTypeStatsTable
    from app.services.hitter_stats import CustomHitTypeStat, CustomHitTypeStatsTable

    fake_module = types.ModuleType('fake_custom_hitter_report')
    fake_module.get_stats = lambda source, batter_id: [CustomStat(name='Barrel', value='42.0%')]
    fake_module.get_hit_type_stats = lambda source, batter_id: [
        CustomHitTypeStatsTable([CustomHitTypeStat(hit_type='Line', stats={'Hard-Hit': '10.0%'})])
    ]
    fake_module.get_pitch_type_stats = lambda source, batter_id: [
        CustomPitchTypeStatsTable([CustomPitchTypeStat(pitch_type='Fastball', stats={'Damage': '5.0%'})])
    ]

    def get_charts(source, batter_id, user_id, output_dir):
        path = os.path.join(output_dir, f'{user_id}_hitter_{batter_id}_custom_test.png')
        with open(path, 'wb') as f:
            f.write(b'not a real png -- just proving the hook wrote a file')
        return [('Test Chart', path)]

    fake_module.get_charts = get_charts

    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: fake_module)

    source = pd.DataFrame({'BatterId': [1]})

    stats = hitter_report.custom_stats_table(source, 1, 999)
    assert stats is not None and stats.rows[0].name == 'Barrel'

    hit_type = hitter_report.custom_hit_type_stats_table(source, 1, 999)
    assert hit_type is not None and hit_type[0].rows[0].hit_type == 'Line'

    pitch_type = hitter_report.custom_pitch_type_stats_table(source, 1, 999)
    assert pitch_type is not None and pitch_type[0].rows[0].pitch_type == 'Fastball'

    charts = hitter_report.custom_charts(source, 1, 999, 7, str(tmp_path))
    assert charts is not None
    title, path = charts[0]
    assert title == 'Test Chart'
    assert os.path.exists(path)


def test_custom_collectors_swallow_a_broken_scripts_exception(monkeypatch):
    """A school's script raising on load must degrade to None, not blow up the report loop."""
    import pandas as pd
    from app.services import hitter_report

    def load_custom_module(school_id, filename):
        raise ImportError('simulated broken school script')

    monkeypatch.setattr(hitter_report, 'load_custom_module', load_custom_module)

    source = pd.DataFrame({'BatterId': [1]})
    assert hitter_report.custom_stats_table(source, 1, 999) is None
    assert hitter_report.custom_hit_type_stats_table(source, 1, 999) is None
    assert hitter_report.custom_pitch_type_stats_table(source, 1, 999) is None


# --- multi-hitter selection + merged PDF -----------------------------------

def _all_own_ids(client):
    return [h['id'] for h in client.get('/api/batting/hitters?target=own').get_json()['hitters']]


def test_selecting_multiple_hitters_returns_one_report_each(archived_games, client):
    ids = _all_own_ids(client)
    assert len(ids) >= 2, 'fixture should provide more than one own-team hitter'

    data = _report(client, batter_ids=ids).get_json()

    assert len(data['reports']) == len(ids)
    assert {r['hitter_id'] for r in data['reports']} == set(ids)
    assert data['failed'] == []


def test_multi_hitter_run_produces_a_merged_pdf(archived_games, client, app, home_school, home_user):
    ids = _all_own_ids(client)
    data = _report(client, batter_ids=ids).get_json()

    assert data['merged_pdf_url'], 'a multi-hitter run must produce a merged PDF'

    reports_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'reports')
    merged = os.path.join(reports_dir, f'{home_user.id}_merged_hitter_reports.pdf')
    assert os.path.exists(merged)

    # Every selected hitter also gets their own file
    for batter_id in ids:
        assert os.path.exists(os.path.join(reports_dir, f'{home_user.id}_hitter_{batter_id}_report.pdf'))


def test_merged_pdf_excludes_pitcher_reports(archived_games, client, app, home_school, home_user):
    """A2: merge_pdfs must filter on the hitter prefix, not sweep the whole folder."""
    from reportlab.pdfgen import canvas

    reports_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'reports')
    os.makedirs(reports_dir, exist_ok=True)

    # A decoy pitcher report sharing the folder. Written here rather than relying
    # on the upload step, which no longer generates PDFs at all.
    decoy = os.path.join(reports_dir, f'{home_user.id}_pitcher_999_report.pdf')
    c = canvas.Canvas(decoy)
    c.drawString(100, 100, 'pitcher decoy')
    c.save()

    ids = _all_own_ids(client)
    _report(client, batter_ids=ids)

    resp = client.get('/api/batting/export?merged=1&target=own')
    assert resp.status_code == 200
    assert resp.data.startswith(b'%PDF')

    # The merged file must hold only the hitter reports. Page counts are the
    # cheapest proof: sweeping the folder would pull the pitcher PDFs in too.
    import pypdf
    merged = os.path.join(reports_dir, f'{home_user.id}_merged_hitter_reports.pdf')
    hitter_pages = sum(
        len(pypdf.PdfReader(os.path.join(reports_dir, f'{home_user.id}_hitter_{b}_report.pdf')).pages)
        for b in ids
    )
    assert len(pypdf.PdfReader(merged).pages) == hitter_pages


def test_regenerating_clears_the_previous_selection(archived_games, client, app, home_school, home_user):
    """A stale PDF from a wider selection must not survive into a narrower one."""
    ids = _all_own_ids(client)
    _report(client, batter_ids=ids)

    _report(client, batter_ids=[BATTER_ID])

    reports_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'reports')
    remaining = {f for f in os.listdir(reports_dir) if '_hitter_' in f and 'merged' not in f}
    assert remaining == {f'{home_user.id}_hitter_{BATTER_ID}_report.pdf'}


# --- export ----------------------------------------------------------------

def test_export_streams_a_single_hitter_pdf(archived_games, client):
    _report(client)

    resp = client.get(f'/api/batting/export?batter_id={BATTER_ID}&target=own')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')
    assert 'attachment' in resp.headers['Content-Disposition']


def test_export_before_generating_returns_404(archived_games, client):
    resp = client.get(f'/api/batting/export?batter_id={BATTER_ID}&target=own')

    assert resp.status_code == 404
    assert 'Generate it first' in resp.get_json()['error']


# --- empty archive ---------------------------------------------------------

def test_report_before_any_game_is_saved_explains_why(client, login_as, home_user):
    login_as(client, home_user)

    resp = _report(client)

    assert resp.status_code == 400
    assert 'No games have been saved' in resp.get_json()['error']


def test_hitters_endpoint_is_empty_before_any_game_is_saved(client, login_as, home_user):
    login_as(client, home_user)

    data = client.get('/api/batting/hitters').get_json()

    assert data == {'hitters': [], 'first_date': None, 'last_date': None, 'game_count': 0}
