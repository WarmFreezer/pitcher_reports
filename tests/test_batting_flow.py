"""
End-to-end coverage for the /batting date-ranged hitting reports.

Games reach the archive through /api/save-game, so these tests drive the same path a
user does: upload, save, then query. BATTER_ID bats for HOME, which is the school's
own team, so target='own' is the relevant filter.

The fixtures give batter 500 five batted balls total: three on 2026-03-01 (a line
single, a ground out, and a home run, all vs RHP) and two on 2026-03-08 (a double
and a ground out, both vs LHP). Several assertions below depend on that split.
"""
import glob
import io
import json
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


def _report_data(client, **overrides):
    """
    /api/batting/report streams one NDJSON line per hitter (built in parallel)
    plus a final 'done' summary line, instead of one JSON blob -- reconstruct the
    old single-dict shape, and force the whole stream to be read (a bare
    _report(client) only guarantees the generator advanced to its first
    'report' line, not through to 'done' and whatever runs after the per-hitter
    loop, like the merge).
    """
    resp = _report(client, **overrides)
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
        'start_date': done.get('start_date'),
        'end_date': done.get('end_date'),
        'games': done.get('games'),
    }


def _first_report(data):
    reports = data['reports']
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
    report = _first_report(_report_data(client))

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
    report = _first_report(_report_data(client, start_date='2026-03-01', end_date='2026-03-01'))

    assert report['games'] == 1
    assert report['summary']['PA'] == '5'
    assert report['summary']['AB'] == '4'
    # The double happens in game two, which this range excludes
    assert report['summary']['2B'] == '0'


def test_range_covering_no_games_returns_404_not_500(archived_games, client):
    resp = _report(client, start_date='2026-01-01', end_date='2026-01-31')

    assert resp.status_code == 404


def test_report_includes_rendered_tables(archived_games, client):
    report = _first_report(_report_data(client))

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
        TaggedPitchType=['Fastball', 'Screwball'],
        PitchCall=['StrikeCalled', 'StrikeCalled'],
        PlateLocSide=[0.0, 0.0],
        PlateLocHeight=[2.5, 2.5],
    )

    assert [row.pitch_type for row in table.rows] == ['FB', 'Screwball'], 'unknown tags sort after known ones'
    screwball = next(row for row in table.rows if row.pitch_type == 'Screwball')
    assert screwball.seen == 1


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
    assert hitter_report.custom_charts(source, 1, 999) is None


def test_custom_collectors_wire_a_schools_hooks_through(monkeypatch, tmp_path):
    """
    A school's custom_hitter_report.py hooks land in the typed tables the PDF
    renders -- get_stats -> CustomStatsTable, get_hit_type_stats ->
    CustomHitTypeStatsTable, get_pitch_type_stats -> CustomPitchTypeStatsTable,
    get_charts -> CustomChart(title, Plotly figure).
    """
    import types
    import pandas as pd
    from app.services import hitter_report
    from app.services.pitch_stats import CustomStat, CustomPitchTypeStat, CustomPitchTypeStatsTable
    from app.services.hitter_stats import CustomChart, CustomHitTypeStat, CustomHitTypeStatsTable

    fake_module = types.ModuleType('fake_custom_hitter_report')
    fake_module.get_stats = lambda source, batter_id: [CustomStat(name='Barrel', value='42.0%')]
    fake_module.get_hit_type_stats = lambda source, batter_id: [
        CustomHitTypeStatsTable([CustomHitTypeStat(hit_type='Line', stats={'Hard-Hit': '10.0%'})])
    ]
    fake_module.get_pitch_type_stats = lambda source, batter_id: [
        CustomPitchTypeStatsTable([CustomPitchTypeStat(pitch_type='Fastball', stats={'Damage': '5.0%'})])
    ]

    fake_module.get_charts = lambda source, batter_id: [CustomChart('Test Chart', _figure())]

    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: fake_module)

    source = pd.DataFrame({'BatterId': [1]})

    stats = hitter_report.custom_stats_table(source, 1, 999)
    assert stats is not None and stats.rows[0].name == 'Barrel'

    hit_type = hitter_report.custom_hit_type_stats_table(source, 1, 999)
    assert hit_type is not None and hit_type[0].rows[0].hit_type == 'Line'

    pitch_type = hitter_report.custom_pitch_type_stats_table(source, 1, 999)
    assert pitch_type is not None and pitch_type[0].rows[0].pitch_type == 'Fastball'

    charts = hitter_report.custom_charts(source, 1, 999)
    assert charts is not None
    assert charts[0].title == 'Test Chart'
    assert charts[0].figure['data'][0]['x'] == [1, 2, 3]


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


def _figure(**overrides):
    figure = {'data': [{'type': 'scatter', 'mode': 'markers', 'x': [1, 2, 3], 'y': [4, 5, 6]}],
              'layout': {'xaxis': {'title': {'text': 'x'}}}}
    figure.update(overrides)
    return figure


def _fake_school_script(monkeypatch, charts):
    """Make hitter_report see a school script whose get_charts returns `charts`."""
    import types
    from app.services import hitter_report

    module = types.ModuleType('fake_custom_hitter_report')
    module.get_charts = lambda source, batter_id: charts
    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: module)


def test_custom_charts_skip_anything_the_page_cannot_safely_draw(monkeypatch, capsys):
    import pandas as pd
    from app.services import hitter_report
    from app.services.hitter_stats import CustomChart

    good = CustomChart('Good', _figure())
    _fake_school_script(monkeypatch, [
        good,
        ('Legacy', '/tmp/an-image-path.png'),                                  # the old (title, path) contract
        CustomChart('No data', {'layout': {}}),
        CustomChart('Not a figure', 'oops'),                                   # type: ignore[arg-type]
        CustomChart('', _figure()),
        CustomChart('NaN', _figure(data=[{'type': 'scatter', 'x': [float('nan')], 'y': [1]}])),
        CustomChart('Huge', _figure(data=[{'type': 'scatter', 'x': list(range(300_000)), 'y': [0]}])),
    ])

    charts = hitter_report.custom_charts(pd.DataFrame({'BatterId': [1]}), 1, 999)

    assert charts == [good]
    assert 'needs updating' in capsys.readouterr().out    # the legacy script is told why


def test_custom_charts_are_capped(monkeypatch):
    import pandas as pd
    from app.services import hitter_report
    from app.services.hitter_stats import CustomChart

    _fake_school_script(monkeypatch, [CustomChart(f'Chart {n}', _figure()) for n in range(20)])

    assert len(hitter_report.custom_charts(pd.DataFrame({'BatterId': [1]}), 1, 999)) == hitter_report.MAX_CUSTOM_CHARTS


def test_a_script_that_returns_nothing_or_raises_has_no_custom_charts(monkeypatch):
    import types
    import pandas as pd
    from app.services import hitter_report

    source = pd.DataFrame({'BatterId': [1]})
    _fake_school_script(monkeypatch, None)
    assert hitter_report.custom_charts(source, 1, 999) is None

    module = types.ModuleType('boom')

    def boom(source, batter_id):
        raise RuntimeError('chart blew up')

    module.get_charts = boom
    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: module)
    assert hitter_report.custom_charts(source, 1, 999) is None


def test_a_legacy_get_charts_signature_degrades_to_no_charts(monkeypatch):
    """A script still written for (source, id, user_id, output_dir) raises TypeError; that must not escape."""
    import types
    import pandas as pd
    from app.services import hitter_report

    module = types.ModuleType('legacy')
    module.get_charts = lambda source, batter_id, user_id, output_dir, theme='light': []
    monkeypatch.setattr(hitter_report, 'load_custom_module', lambda school_id, filename: module)

    assert hitter_report.custom_charts(pd.DataFrame({'BatterId': [1]}), 1, 999) is None


def test_custom_charts_reach_the_card_and_the_pdf(archived_games, client, monkeypatch):
    import io as _io
    import pypdf
    from app.services.hitter_stats import CustomChart

    _fake_school_script(monkeypatch, [CustomChart('Mine', _figure()), CustomChart('Also mine', _figure())])

    card = _first_report(_report_data(client))
    assert [(c['title'], c['slot']) for c in card['custom_charts']] == [('Mine', 'custom_0'), ('Also mine', 'custom_1')]
    assert card['custom_charts'][0]['figure']['data'][0]['x'] == [1, 2, 3]

    plain = _export(client, [{'batter_id': BATTER_ID, 'images': {'spray_left': PNG_1X1}}])
    with_charts = _export(client, [{'batter_id': BATTER_ID, 'images': {
        'spray_left': PNG_1X1, 'custom_0': PNG_1X1, 'custom_1': PNG_1X1, 'custom_9': PNG_1X1}}])

    assert with_charts.status_code == 200
    # the two custom charts add to the PDF; the made-up custom_9 slot is ignored
    pages = lambda resp: sum(len(p.extract_text()) for p in pypdf.PdfReader(_io.BytesIO(resp.data)).pages)
    assert pages(with_charts) > pages(plain)


def test_a_charts_only_refresh_has_no_custom_charts_to_replace(archived_games, client, monkeypatch):
    from app.services.hitter_stats import CustomChart

    _fake_school_script(monkeypatch, [CustomChart('Mine', _figure())])

    card = client.post('/api/batting/hitter', json={'batter_id': BATTER_ID, 'target': 'own', 'charts_only': True}).get_json()

    assert 'custom_charts' not in card


def test_school_2s_exit_velocity_chart_is_a_plotly_figure():
    import importlib.util
    import json
    import pandas as pd
    from app.services.hitter_stats import CustomChart

    path = Path(__file__).parent.parent / 'app' / 'storage' / 'schools' / '2' / 'assets' / 'custom_hitter_report.py'
    spec = importlib.util.spec_from_file_location('school2_hitter', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = pd.DataFrame({
        'BatterId': [7, 7, 7, 7], 'PitchCall': ['InPlay', 'InPlay', 'InPlay', 'StrikeCalled'],
        'Angle': [12.0, 28.0, float('nan'), None], 'ExitSpeed': [101.5, 88.0, 90.0, None]})

    charts = module.get_charts(source, 7)

    assert len(charts) == 1 and isinstance(charts[0], CustomChart)
    figure = charts[0].figure
    json.dumps(figure, allow_nan=False)
    assert figure['data'][0]['x'] == [12.0, 28.0] and figure['data'][0]['y'] == [101.5, 88.0]
    assert figure['layout']['yaxis'].get('scaleanchor') is None          # EV vs LA aren't the same units
    assert 'name' not in figure['layout']['shapes'][0]                    # the barrel zone keeps its red in dark mode
    assert module.get_charts(source.iloc[0:0], 7) == []


def test_the_app_runs_without_matplotlib_or_seaborn():
    """They were dropped from requirements.txt; blocking them proves nothing still reaches for them."""
    import subprocess
    import sys

    code = (
        "import sys\n"
        "sys.modules['matplotlib'] = None\n"
        "sys.modules['seaborn'] = None\n"
        "import app.main\n"
        "from app.services import report, hitter_report, catching_report, plotly_charts, report_lab_generator\n"
        "print('ok')\n"
    )
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                            cwd=Path(__file__).parent.parent)

    assert result.returncode == 0, result.stderr
    assert 'ok' in result.stdout


# --- multi-hitter selection + merged PDF -----------------------------------

def _all_own_ids(client):
    return [h['id'] for h in client.get('/api/batting/hitters?target=own').get_json()['hitters']]


def test_selecting_multiple_hitters_returns_one_report_each(archived_games, client):
    ids = _all_own_ids(client)
    assert len(ids) >= 2, 'fixture should provide more than one own-team hitter'

    data = _report_data(client, batter_ids=ids)

    assert len(data['reports']) == len(ids)
    assert {r['hitter_id'] for r in data['reports']} == set(ids)
    assert data['failed'] == []


# --- report cards: filters, charts, no files --------------------------------

def _points(figure):
    """Number of plotted points in a figure (the legend-only traces carry no data)."""
    return sum(len(t['x']) for t in figure['data'] if t.get('showlegend') is not True and t.get('type') == 'scatter')


def test_report_cards_carry_plotly_spray_figures_not_image_urls(archived_games, client):
    card = _first_report(_report_data(client))

    assert set(card['figures']) == {'spray_left', 'spray_right'}
    for figure in card['figures'].values():
        assert set(figure) == {'data', 'layout'}
    assert not any(key.startswith('spray_') and key.endswith('_url') for key in card)


def test_spray_charts_plot_every_batted_ball_against_each_side(archived_games, client):
    figures = _first_report(_report_data(client))['figures']

    # Three batted balls vs RHP on 03-01 and two vs LHP on 03-08 (see the module docstring)
    assert _points(figures['spray_right']) == 3
    assert _points(figures['spray_left']) == 2


def test_report_writes_no_chart_images_or_pdfs(archived_games, client, app, home_school):
    _report_data(client)

    school_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id))
    for sub in ('temp', 'reports'):
        folder = os.path.join(school_dir, sub)
        generated = [f for f in os.listdir(folder) if f.endswith(('.png', '.pdf'))] if os.path.isdir(folder) else []
        assert generated == []


def test_report_meta_describes_the_filter_bar(archived_games, client):
    meta = _report_data(client)['meta']

    assert [t['name'] for t in meta['pitch_types']] == ['Fastball', 'Slider', 'ChangeUp']
    assert meta['velo_min'] == 89 and meta['velo_max'] == 89
    assert meta['defaults'] == {'view': 'heatmap', 'color_by': 'pitch_type'}


def test_report_meta_defaults_follow_the_account_settings(archived_games, client, home_user):
    from app.db.models import db
    home_user.chart_style = 'pitch_point'
    home_user.chart_color_mode = 'velo'
    db.session.commit()

    assert _report_data(client)['meta']['defaults'] == {'view': 'scatter', 'color_by': 'velo'}


def test_report_filters_change_the_numbers(archived_games, client):
    everything = _first_report(_report_data(client))
    sliders = _first_report(_report_data(client, filters={'pitch_types': ['Slider']}))

    assert int(sliders['summary']['PA']) < int(everything['summary']['PA'])
    assert 'FB' not in sliders['discipline_table']


def test_report_with_a_velo_range_nobody_threw_is_an_empty_card(archived_games, client):
    data = _report_data(client, filters={'velo': [95, 99]})

    assert data['failed'] == []
    assert data['reports'][0]['empty'] is True


def test_report_rejects_malformed_filters_and_chart_options(archived_games, client):
    for bad in ({'pitch_types': 'Slider'}, {'velo': [1]}, 'x'):
        assert _report(client, filters=bad).status_code == 400, bad
    assert _report(client, view='3d').status_code == 400
    assert _report(client, color_by='framing').status_code == 400   # the catcher page's own color


# --- single-card refresh ----------------------------------------------------

def _card(client, **extra):
    body = {'batter_id': BATTER_ID, 'target': 'own', **extra}
    return client.post('/api/batting/hitter', json=body)


def test_hitter_endpoint_rebuilds_one_card_for_new_filters(archived_games, client):
    resp = _card(client, filters={'pitch_types': ['Slider']})

    assert resp.status_code == 200
    card = resp.get_json()
    assert card['hitter_id'] == BATTER_ID and 'discipline_table' in card


def test_hitter_endpoint_charts_only_skips_the_tables(archived_games, client):
    card = _card(client, charts_only=True, view='scatter', color_by='velo').get_json()

    assert 'figures' in card
    assert 'discipline_table' not in card


def test_hitter_endpoint_scatter_view_draws_only_points(archived_games, client):
    card = _card(client, charts_only=True, view='scatter').get_json()

    for figure in card['figures'].values():
        assert {t['type'] for t in figure['data']} <= {'scatter'}


def test_hitter_endpoint_404s_for_a_hitter_outside_the_archive(archived_games, client):
    assert _card(client, batter_id='999999').status_code == 404
    assert _card(client, batter_id='').status_code == 400


# --- export ----------------------------------------------------------------

PNG_1X1 = ('data:image/png;base64,'
           'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


def _export(client, hitters, **extra):
    body = {'target': 'own', 'hitters': hitters, **extra}
    return client.post('/api/batting/export', json=body)


def test_export_builds_a_single_hitter_pdf(archived_games, client):
    resp = _export(client, [{'batter_id': BATTER_ID, 'images': {'spray_left': PNG_1X1, 'spray_right': PNG_1X1}}])

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')
    assert 'attachment' in resp.headers['Content-Disposition']


def test_export_without_images_still_builds_the_tables(archived_games, client):
    assert _export(client, [{'batter_id': BATTER_ID}]).data.startswith(b'%PDF')


def test_export_merges_several_hitters_into_one_pdf(archived_games, client):
    import io as _io
    import pypdf

    ids = _all_own_ids(client)
    assert len(ids) >= 2
    singles = [len(pypdf.PdfReader(_io.BytesIO(_export(client, [{'batter_id': b}]).data)).pages) for b in ids]

    merged = _export(client, [{'batter_id': b} for b in ids])

    assert merged.status_code == 200
    assert 'hitter_reports_' in merged.headers['Content-Disposition']
    assert len(pypdf.PdfReader(_io.BytesIO(merged.data)).pages) == sum(singles)


def test_export_applies_the_filters_to_the_pdf(archived_games, client):
    resp = _export(client, [{'batter_id': BATTER_ID}], filters={'velo': [95, 99]})

    assert resp.status_code == 404
    assert 'No pitches match' in resp.get_json()['error']


def test_export_rejects_bad_images(archived_games, client):
    for bad in ('data:image/png;base64,AAAA', 'data:image/svg+xml;base64,AAAA'):
        assert _export(client, [{'batter_id': BATTER_ID, 'images': {'spray_left': bad}}]).status_code == 400


def test_export_ignores_slots_it_does_not_know(archived_games, client, app, home_school):
    resp = _export(client, [{'batter_id': BATTER_ID, 'images': {'../../evil': PNG_1X1}}])

    assert resp.status_code == 200
    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert not any('evil' in f for f in os.listdir(temp_dir))


def test_export_rejects_a_hitter_outside_the_archive_and_empty_requests(archived_games, client):
    assert _export(client, [{'batter_id': '999999'}]).status_code == 404
    assert _export(client, []).status_code == 400
    assert _export(client, 'all').status_code == 400


def test_export_leaves_no_working_files_behind(archived_games, client, app, home_school):
    _export(client, [{'batter_id': BATTER_ID, 'images': {'spray_left': PNG_1X1}}])

    temp_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'temp')
    assert [f for f in os.listdir(temp_dir) if '_export_' in f or f.endswith(('.png', '.pdf'))] == []


def test_a_pdf_that_fails_to_build_is_a_server_error_not_no_matches(archived_games, client, monkeypatch):
    from app.services.report_lab_generator import PDF_Generator

    def boom(self, data, output_path):
        raise RuntimeError('layout blew up')

    monkeypatch.setattr(PDF_Generator, 'generate_hitter_report', boom)

    resp = _export(client, [{'batter_id': BATTER_ID}])

    assert resp.status_code == 500
    assert resp.get_json()['error'] == 'Could not build the PDF.'


def test_old_get_export_is_gone(archived_games, client):
    assert client.get(f'/api/batting/export?batter_id={BATTER_ID}&target=own').status_code == 405


# --- pitch-by-pitch -------------------------------------------------------------

def test_pitch_by_pitch_is_built_on_request(archived_games, client, app, home_school):
    resp = client.get(f'/api/batting/pitch-by-pitch?batter_id={BATTER_ID}&target=own')

    assert resp.status_code == 200
    assert resp.mimetype == 'application/pdf'
    assert resp.data.startswith(b'%PDF')
    assert 'attachment' in resp.headers['Content-Disposition']
    reports_dir = os.path.join(app.config['STORAGE'], 'schools', str(home_school.id), 'reports')
    assert [f for f in os.listdir(reports_dir) if f.endswith('.pdf')] == []


def test_pitch_by_pitch_honors_the_filters(archived_games, client):
    nothing = json.dumps({'velo': [95, 99]})

    resp = client.get(f'/api/batting/pitch-by-pitch?batter_id={BATTER_ID}&target=own&filters={nothing}')

    assert resp.status_code == 404


def test_pitch_by_pitch_rejects_malformed_filters_and_unknown_hitters(archived_games, client):
    assert client.get(f'/api/batting/pitch-by-pitch?batter_id={BATTER_ID}&target=own&filters={{nope').status_code == 400
    assert client.get('/api/batting/pitch-by-pitch?batter_id=999999&target=own').status_code == 404
    assert client.get('/api/batting/pitch-by-pitch?target=own').status_code == 400


def test_pitch_by_pitch_pdf_pairs_charts_and_tables_with_an_odd_at_bat_count(app, home_school, tmp_path):
    """
    Charts and tables are laid out two-per-line so a chart never drifts far from
    its own table. An odd at-bat count leaves the last pair's second cell empty --
    this must not raise building the PDF.
    """
    from app.services.branding_loader import BrandingLoader
    from app.services.hitter_stats import HitterPitchByPitchAtBat, HitterPitchByPitchReport
    from app.services.pitch_stats import PitchByPitchPitch
    from app.services.report_lab_generator import PDF_Generator

    at_bats = [
        HitterPitchByPitchAtBat(
            inning=f'Bottom {n}', pitcher_name='Doe, John', pitcher_throws='Right', result='Out',
            pitches=[PitchByPitchPitch(
                number=1, pitch_type='Fastball', velo=90.0, balls=0, strikes=1, result='StrikeCalled',
                plate_loc_side=0.0, plate_loc_height=2.5,
            )],
        )
        for n in range(1, 6)  # odd count -> last pair has only one AB
    ]

    pbp_report = HitterPitchByPitchReport(
        hitter_name='Alpha, Adam', date_range='2026-01-01 - 2026-01-01', at_bats=at_bats,
    )
    branding = BrandingLoader.get_branding(home_school.id)
    gen = PDF_Generator(school_id=home_school.id, branding=branding, ink_mode='full_color')
    output_path = str(tmp_path / 'pbp_regression.pdf')

    gen.generate_hitter_pitch_by_pitch_report(pbp_report, output_path)

    assert os.path.exists(output_path)


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
