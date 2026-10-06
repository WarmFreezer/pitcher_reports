"""Plotly figure specs: structure, JSON-safety, and the scatter/heatmap/color-by switches."""
import json

import numpy as np
import pandas as pd
import pytest

from app.services import plotly_charts as pc


def _pitches(n_fastball=40, n_slider=5, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for pitch_type, n, speed in (('Fastball', n_fastball, 93.0), ('Slider', n_slider, 84.0)):
        for _ in range(n):
            rows.append({
                'TaggedPitchType': pitch_type, 'BatterSide': 'Right',
                'PlateLocSide': rng.normal(0, 0.6), 'PlateLocHeight': rng.normal(2.5, 0.6),
                'HorzBreak': rng.normal(-5, 3), 'InducedVertBreak': rng.normal(15, 3),
                'RelSpeed': rng.normal(speed, 1.5),
            })
    return pd.DataFrame(rows)


def _types(figure):
    return [t['type'] for t in figure['data']]


# --- velocity scale ---------------------------------------------------------

def test_velo_limits_are_the_quartiles():
    rows = pd.DataFrame({'RelSpeed': [80.0, 85.0, 90.0, 95.0, 100.0]})

    assert pc.velo_limits(rows) == (85.0, 95.0)


def test_velo_limits_keep_a_readable_span_for_a_very_consistent_arm():
    lo, hi = pc.velo_limits(pd.DataFrame({'RelSpeed': [90.0] * 10}))

    assert hi - lo == pytest.approx(1.0)


def test_velo_limits_need_two_tracked_pitches():
    assert pc.velo_limits(pd.DataFrame({'RelSpeed': [90.0, None]})) is None


# --- location chart ---------------------------------------------------------

def test_scatter_view_draws_one_marker_trace_per_pitch_type():
    fig = pc.location_figure(_pitches(), 'Right', 'pitch_type', 'scatter', None)

    assert _types(fig) == ['scatter', 'scatter']
    assert [t['name'] for t in fig['data']] == ['FB', 'SL']
    assert fig['data'][0]['marker']['symbol'] != fig['data'][1]['marker']['symbol']


def test_heatmap_view_uses_a_density_for_types_with_enough_pitches():
    fig = pc.location_figure(_pitches(n_fastball=40, n_slider=5), 'Right', 'pitch_type', 'heatmap', None)

    # Fastball (40) gets a contour + its mean marker; Slider (5) is too sparse to trust one.
    assert _types(fig) == ['contour', 'scatter', 'scatter']
    assert fig['data'][-1]['name'] == 'SL'


def test_density_is_scaled_to_a_unit_peak():
    fig = pc.location_figure(_pitches(), 'Right', 'pitch_type', 'heatmap', None)

    z = np.array([[v for v in row] for row in fig['data'][0]['z']], dtype=float)
    assert z.max() == pytest.approx(1.0, abs=1e-3)
    assert z.min() >= 0


def test_the_other_batter_side_has_no_data_note():
    fig = pc.location_figure(_pitches(), 'Left', 'pitch_type', 'scatter', None)

    assert fig['data'] == []
    assert 'No data for Left-handed batters' in fig['layout']['annotations'][0]['text']


def test_strike_zone_shapes_are_tagged_for_theming():
    fig = pc.location_figure(_pitches(), 'Right', 'pitch_type', 'scatter', None)

    assert {s['name'] for s in fig['layout']['shapes']} == {'ink', 'muted'}


def test_locationless_pitches_are_dropped_not_plotted_at_nan():
    rows = _pitches(n_fastball=10, n_slider=0)
    rows.loc[:2, 'PlateLocSide'] = np.nan

    fig = pc.location_figure(rows, 'Right', 'pitch_type', 'scatter', None)

    assert len(fig['data'][0]['x']) == 7


def test_untyped_pitches_are_not_plotted():
    rows = _pitches(n_fastball=10, n_slider=0)
    rows.loc[:3, 'TaggedPitchType'] = 'n/a'

    fig = pc.location_figure(rows, 'Right', 'pitch_type', 'scatter', None)

    assert len(fig['data'][0]['x']) == 6


# --- color by velocity --------------------------------------------------------

def test_velo_scatter_is_one_trace_pinned_to_the_given_scale():
    fig = pc.location_figure(_pitches(), 'Right', 'velo', 'scatter', (88.0, 94.0))

    assert len(fig['data']) == 1
    marker = fig['data'][0]['marker']
    assert (marker['cmin'], marker['cmax']) == (88.0, 94.0)
    assert marker['showscale'] is True
    assert len(set(marker['symbol'])) == 2   # pitch type still reads, through the marker shape


def test_velo_scatter_keeps_untracked_pitches_in_gray():
    rows = _pitches(n_fastball=10, n_slider=0)
    rows.loc[:1, 'RelSpeed'] = np.nan

    fig = pc.location_figure(rows, 'Right', 'velo', 'scatter', (88.0, 94.0))

    gray = [t for t in fig['data'] if t['name'] == 'No velo']
    assert len(gray) == 1 and len(gray[0]['x']) == 2


def test_velo_heatmap_is_one_contour_of_mean_velocity():
    fig = pc.location_figure(_pitches(), 'Right', 'velo', 'heatmap', (88.0, 94.0))

    assert _types(fig) == ['contour']
    trace = fig['data'][0]
    assert (trace['zmin'], trace['zmax']) == (88.0, 94.0)
    values = [v for row in trace['z'] for v in row if v is not None]
    assert values and 80 < min(values) and max(values) < 100


def test_velo_heatmap_falls_back_to_points_when_too_few_tracked_pitches():
    fig = pc.location_figure(_pitches(n_fastball=5, n_slider=0), 'Right', 'velo', 'heatmap', (88.0, 94.0))

    assert _types(fig) == ['scatter']


# --- break chart --------------------------------------------------------------

def test_break_figure_returns_the_arm_angle():
    rows = pd.DataFrame({
        'TaggedPitchType': ['Fastball'] * 4, 'RelSpeed': [90.0] * 4,
        'HorzBreak': [10.0] * 4, 'InducedVertBreak': [10.0] * 4})

    _, arm_angle = pc.break_figure(rows, 'pitch_type', 'scatter', None, show_arrows=True)

    assert arm_angle == pytest.approx(45.0)


def test_break_arrows_follow_the_preference_but_the_angle_does_not():
    rows = _pitches()

    with_arrows, angle_on = pc.break_figure(rows, 'pitch_type', 'scatter', None, show_arrows=True)
    without, angle_off = pc.break_figure(rows, 'pitch_type', 'scatter', None, show_arrows=False)

    assert len(with_arrows['layout']['annotations']) == 3   # two pitch types + the overall arrow
    assert without['layout']['annotations'] == []
    assert angle_on == angle_off


def test_break_figure_without_data_has_a_note_and_no_angle():
    fig, arm_angle = pc.break_figure(_pitches().iloc[0:0], 'pitch_type', 'scatter', None, True)

    assert fig['data'] == [] and arm_angle is None
    assert fig['layout']['annotations'][0]['text'] == 'No movement data'


def test_break_axes_use_the_abbreviations():
    fig, _ = pc.break_figure(_pitches(), 'pitch_type', 'scatter', None, False)

    assert fig['layout']['xaxis']['title']['text'] == 'HB (in)'
    assert fig['layout']['yaxis']['title']['text'] == 'IVB (in)'


@pytest.mark.parametrize('view', pc.VIEWS)
def test_the_velocity_key_sits_inside_the_plot_so_it_cannot_resize_it(view):
    """A vertical bar in the margin widens the margin; this one is horizontal and in paper coords."""
    fig = pc.location_figure(_pitches(), 'Right', 'velo', view, (88.0, 94.0))

    bar = fig['data'][0].get('colorbar') or fig['data'][0]['marker']['colorbar']
    assert bar['orientation'] == 'h'
    assert bar['xref'] == bar['yref'] == 'paper'
    assert 0 < bar['x'] < 1 and 0 < bar['y'] <= 1


def test_the_plot_margins_are_the_same_in_every_color_mode():
    pitch_type = pc.location_figure(_pitches(), 'Right', 'pitch_type', 'scatter', None)
    velo = pc.location_figure(_pitches(), 'Right', 'velo', 'scatter', (88.0, 94.0))

    assert pitch_type['layout']['margin'] == velo['layout']['margin']


# --- legend ------------------------------------------------------------------

def test_legend_lists_present_types_with_counts_in_display_order():
    legend = pc.pitch_type_legend(_pitches(n_fastball=7, n_slider=3))

    assert [(e['abbreviation'], e['count']) for e in legend] == [('FB', 7), ('SL', 3)]


# --- serialisation ----------------------------------------------------------

@pytest.mark.parametrize('color_by', pc.COLOR_MODES)
@pytest.mark.parametrize('view', pc.VIEWS)
def test_every_figure_is_strict_json(color_by, view):
    """A bare NaN would serialise to `NaN`, which the browser's JSON.parse rejects."""
    rows = _pitches()
    rows.loc[:4, 'RelSpeed'] = np.nan
    lim = pc.velo_limits(rows)

    figures = [
        pc.location_figure(rows, 'Right', color_by, view, lim),
        pc.break_figure(rows, color_by, view, lim, True)[0],
    ]

    for fig in figures:
        text = json.dumps(fig, allow_nan=False)
        assert json.loads(text)['layout']['showlegend'] is False


# --- batted-ball spray ------------------------------------------------------------

def _batted(n_right=12, n_left=3, seed=5):
    rng = np.random.default_rng(seed)
    rows = []
    for side, n in (('Right', n_right), ('Left', n_left)):
        for i in range(n):
            rows.append({
                'TaggedPitchType': 'Fastball' if i % 3 else 'Slider', 'PitcherThrows': side,
                'PitchCall': 'InPlay', 'Bearing': rng.uniform(-40, 40), 'Distance': rng.uniform(40, 330),
                'ExitSpeed': rng.uniform(60, 105), 'Angle': rng.uniform(-10, 45), 'RelSpeed': rng.normal(90, 3)})
    rows.append({'TaggedPitchType': 'Fastball', 'PitcherThrows': 'Right', 'PitchCall': 'StrikeCalled',
                 'Bearing': None, 'Distance': None, 'ExitSpeed': None, 'Angle': None, 'RelSpeed': 92.0})
    return pd.DataFrame(rows)


def _spray_points(fig):
    return sum(len(t['x']) for t in fig['data'] if t.get('showlegend') is not True and t['type'] == 'scatter')


def test_spray_plots_only_batted_balls_against_the_requested_side():
    rows = _batted(12, 3)

    assert _spray_points(pc.spray_figure(rows, 'Right', 'pitch_type', 'scatter', None)) == 12
    assert _spray_points(pc.spray_figure(rows, 'Left', 'pitch_type', 'scatter', None)) == 3


def test_spray_marker_shape_is_the_batted_ball_type_in_every_color_mode():
    rows = _batted(30, 0)
    for color_by in pc.COLOR_MODES:
        fig = pc.spray_figure(rows, 'Right', color_by, 'scatter', (70.0, 95.0))
        symbols = {s for t in fig['data'] if t.get('showlegend') is not True
                   for s in (t['marker']['symbol'] if isinstance(t['marker']['symbol'], list) else [t['marker']['symbol']])}
        assert len(symbols) > 1, color_by
        assert symbols <= {'circle', 'star', 'x', 'cross'}


def test_spray_has_a_batted_ball_type_key_and_the_field():
    fig = pc.spray_figure(_batted(), 'Right', 'pitch_type', 'scatter', None)

    assert [t['name'] for t in fig['data'] if t.get('showlegend') is True] == ['Ground', 'Line', 'Fly', 'Pop']
    assert fig['layout']['showlegend'] is True
    assert len(fig['layout']['shapes']) >= 7                       # foul lines, wall, diamond, rings
    assert [a['text'] for a in fig['layout']['annotations']] == ['100', '200', '300', '400 ft']


def test_spray_velocity_color_is_exit_speed_pinned_to_the_scale():
    fig = pc.spray_figure(_batted(), 'Right', 'velo', 'scatter', (70.0, 95.0))

    marker = next(t for t in fig['data'] if t.get('showlegend') is not True)['marker']
    assert (marker['cmin'], marker['cmax']) == (70.0, 95.0)
    assert all(60 <= v <= 105 for v in marker['color'])             # ExitSpeed, not RelSpeed (~90)
    assert marker['colorbar']['title']['text'] == 'EV mph'


def test_spray_heatmap_is_a_density_when_there_are_enough_balls():
    fig = pc.spray_figure(_batted(40, 0), 'Right', 'pitch_type', 'heatmap', None)

    assert 'contour' in {t['type'] for t in fig['data']}


def test_spray_with_no_batted_balls_says_so():
    fig = pc.spray_figure(_batted(0, 0), 'Left', 'pitch_type', 'scatter', None)

    assert fig['data'] == []
    assert 'No batted balls vs Left-handed pitching' in fig['layout']['annotations'][-1]['text']


def test_spray_is_strict_json():
    rows = _batted()
    rows.loc[:2, 'ExitSpeed'] = np.nan
    for color_by in pc.COLOR_MODES:
        for view in pc.VIEWS:
            json.dumps(pc.spray_figure(rows, 'Right', color_by, view, pc.exit_velo_limits(rows)), allow_nan=False)


def test_exit_velo_limits_use_the_quartile_rule():
    rows = pd.DataFrame({'ExitSpeed': [60.0, 70.0, 80.0, 90.0, 100.0]})

    assert pc.exit_velo_limits(rows) == (70.0, 90.0)
    assert pc.exit_velo_limits(pd.DataFrame({'ExitSpeed': [80.0]})) is None
    assert pc.exit_velo_limits(pd.DataFrame({'Other': [1]})) is None


# --- catcher framing ---------------------------------------------------------------

def _taken(n=30, seed=9):
    rng = np.random.default_rng(seed)
    rows = pd.DataFrame({
        'TaggedPitchType': rng.choice(['Fastball', 'Slider'], n), 'RelSpeed': rng.normal(88, 4, n),
        'PlateLocSide': rng.normal(0, 0.8, n), 'PlateLocHeight': rng.normal(2.5, 0.8, n),
        'framing_value': rng.uniform(-0.5, 0.5, n)})
    rows.loc[:4, 'framing_value'] = 0.0      # toss-ups that matched the model's expectation
    return rows


def test_catcher_notable_chart_drops_the_toss_ups():
    rows = _taken()

    notable = pc.catcher_figure(rows, 'notable', 'pitch_type', 'scatter', None)
    everything = pc.catcher_figure(rows, 'all', 'pitch_type', 'scatter', None)

    assert sum(len(t['x']) for t in everything['data']) == len(rows)
    assert 0 < sum(len(t['x']) for t in notable['data']) < len(rows)


def test_catcher_framing_color_uses_a_fixed_lost_to_stolen_scale():
    fig = pc.catcher_figure(_taken(), 'all', 'framing', 'scatter', None)

    marker = fig['data'][0]['marker']
    assert (marker['cmin'], marker['cmax']) == pc.FRAMING_LIM
    assert marker['colorscale'][0][1] != marker['colorscale'][-1][1]
    assert marker['colorbar']['title']['text'] == 'framing'
    assert all(-0.5 <= v <= 0.5 for v in marker['color'])


def test_catcher_strongest_pitches_are_drawn_last():
    fig = pc.catcher_figure(_taken(), 'all', 'framing', 'scatter', None)

    values = [abs(v) for v in fig['data'][0]['marker']['color']]
    assert values == sorted(values)


def test_catcher_velocity_and_pitch_type_modes():
    rows = _taken()

    velo = pc.catcher_figure(rows, 'all', 'velo', 'scatter', (84.0, 92.0))
    kind = pc.catcher_figure(rows, 'all', 'pitch_type', 'scatter', None)

    assert (velo['data'][0]['marker']['cmin'], velo['data'][0]['marker']['cmax']) == (84.0, 92.0)
    assert [t['name'] for t in kind['data']] == ['FB', 'SL']


def test_catcher_framing_heatmap_is_a_mean_framing_surface():
    fig = pc.catcher_figure(_taken(80), 'all', 'framing', 'heatmap', None)

    assert fig['data'][0]['type'] == 'contour'
    assert (fig['data'][0]['zmin'], fig['data'][0]['zmax']) == pc.FRAMING_LIM


def test_catcher_empty_states_name_the_chart():
    nothing = _taken().iloc[0:0]
    toss_ups = _taken().assign(framing_value=0.0)

    assert 'No taken-pitch data' in pc.catcher_figure(nothing, 'all', 'framing', 'scatter', None)['layout']['annotations'][0]['text']
    assert 'No notable framing events' in pc.catcher_figure(toss_ups, 'notable', 'framing', 'scatter', None)['layout']['annotations'][0]['text']


def test_catcher_figures_are_strict_json():
    for kind in ('notable', 'all'):
        for color_by in ('framing', 'pitch_type', 'velo'):
            for view in pc.VIEWS:
                json.dumps(pc.catcher_figure(_taken(), kind, color_by, view, (84.0, 92.0)), allow_nan=False)
