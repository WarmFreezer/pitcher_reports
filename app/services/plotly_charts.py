"""
Plotly figure specs for the report charts, built as plain JSON-ready dicts.

No `plotly` Python dependency on purpose: the browser's Plotly.js is what draws them
(and what renders the PNGs the PDF export uses), so the server only has to emit
{'data': [...], 'layout': {...}}. Every number is converted with `_floats` so a NaN
becomes null -- json.dumps would otherwise emit a bare `NaN`, which JSON.parse rejects.

Figures are built with the light theme's colors. The page re-colors text, grid and zone
lines for dark mode client-side (see static/js/charts.js); the shapes carry a `name`
of 'ink' or 'muted' so it knows which is which.

Every chart is a cloud of points in some coordinate system, drawn the same few ways:
colored by pitch type, or by a numeric measurement (a ValueScale), as points or as a
density. `_cloud_traces` does that once; the public figure functions (pitch location,
pitch movement, batted-ball spray, catcher framing) only choose the axes, the field
drawing and which measurement the color means.

Pure Python/numpy/pandas, no Flask -- see app/services/CLAUDE.md.
"""
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.services.catching_report import MIN_NOTABLE_FRAMING_VALUE
from app.services.hitter_report import classify_hit_type
from app.services.velo_scale import TEMPERATURE, velo_scale
from app.services.report_theme import (
    BASEBALL_WIDTH,
    ZONE_BOTTOM,
    ZONE_SIDE,
    ZONE_TOP,
    pitch_order,
    pitch_point_colors,
)

COLOR_MODES = ('pitch_type', 'velo')
VIEWS = ('heatmap', 'scatter')

# Below this many pitches of one type a density surface overstates how confident its
# shape is, so that type falls back to points even in heatmap view (see
# report._show_heatmap, the matplotlib version of the same rule).
HEATMAP_MIN_PITCHES = 8

LOCATION_XLIM = (-2.5, 2.5)
LOCATION_YLIM = (0.0, 5.0)
BREAK_LIM = (-25.0, 25.0)
SPRAY_XLIM = (-350.0, 350.0)
SPRAY_YLIM = (-20.0, 450.0)

INK = '#111111'
MUTED = '#444444'
GRID = 'rgba(68,68,68,0.25)'

_SYMBOL_BY_ABBR = {
    'FB': 'circle', '4S': 'circle', 'SK': 'triangle-down', '2S': 'triangle-down',
    'CT': 'hexagon', 'SL': 'diamond', 'SW': 'diamond-wide', 'CB': 'triangle-up',
    'CH': 'square', 'SP': 'cross', 'KB': 'star', 'UN': 'x',
}

# Batted-ball type is the marker shape on the spray chart, in every color mode.
_SYMBOL_BY_HIT_TYPE = {'Ground': 'circle', 'Line': 'star', 'Fly': 'x', 'Pop': 'cross'}

# Lost framing (red) through a call that matched the model (pale) to stolen (blue).
FRAMING_COLORSCALE = ((0.0, '#b2182b'), (0.5, '#f7f7f7'), (1.0, '#2166ac'))
FRAMING_LIM = (-0.5, 0.5)

_GRID_POINTS = 64


@dataclass(frozen=True)
class ValueScale:
    """A measurement the color encodes: which column, the ends of its color scale, and
    how it is labelled on the key and in hover text."""
    column: str
    lim: tuple[float, float] | None
    colorscale: tuple[tuple[float, str], ...] = tuple(TEMPERATURE)
    key_title: str = 'mph'
    hover_suffix: str = ' mph'
    digits: int = 1
    missing_label: str = 'No velo'

    def with_lim(self, lim: tuple[float, float] | None) -> 'ValueScale':
        return ValueScale(self.column, lim, self.colorscale, self.key_title,
                          self.hover_suffix, self.digits, self.missing_label)


PITCH_VELO = ValueScale('RelSpeed', None)
EXIT_VELO = ValueScale('ExitSpeed', None, key_title='EV mph', missing_label='No exit velo')
FRAMING = ValueScale('framing_value', FRAMING_LIM, FRAMING_COLORSCALE, key_title='framing',
                     hover_suffix='', digits=2, missing_label='No value')


# --------------------------------------------------------------------------- helpers

def _floats(values: Any, digits: int = 3) -> list[float | None]:
    return [round(float(v), digits) if math.isfinite(v) else None for v in values]


def _style(pitch_type: str) -> dict[str, str]:
    abbr = pitch_order.get(pitch_type, pitch_type)
    return {
        'abbr': abbr,
        'color': pitch_point_colors.get(pitch_type, '#888888'),
        'symbol': _SYMBOL_BY_ABBR.get(abbr, 'circle'),
    }


def _pitch_types(rows: pd.DataFrame) -> list[str]:
    """Pitch types in `rows` (excluding untyped), in the canonical display order."""
    order = {name: i for i, name in enumerate(pitch_order)}
    found = [t for t in rows['TaggedPitchType'].dropna().unique() if t != 'n/a']
    return sorted(found, key=lambda t: (order.get(t, len(order)), t))


def _quartile_limits(rows: pd.DataFrame, column: str) -> tuple[float, float] | None:
    if column not in rows.columns:
        return None
    values = pd.to_numeric(rows[column], errors='coerce').dropna()
    if len(values) < 2:
        return None
    return velo_scale(values.tolist())


def velo_limits(rows: pd.DataFrame) -> tuple[float, float] | None:
    """
    First and third quartile of release speed -- the ends of the temperature scale.

    Computed from the pitcher's pitches *before* the user's filters, so colors keep
    their meaning while the sliders move; the quartiles (not min/max) so one badly
    tracked pitch can't wash out the rest of the scale.
    """
    return _quartile_limits(rows, 'RelSpeed')


def exit_velo_limits(rows: pd.DataFrame) -> tuple[float, float] | None:
    """The same quartile rule applied to a hitter's exit speeds -- see velo_limits."""
    return _quartile_limits(rows, 'ExitSpeed')


def pitch_type_legend(rows: pd.DataFrame) -> list[dict[str, Any]]:
    """Legend entries (abbreviation, color, count) for the pitch types present in `rows`."""
    counts = rows['TaggedPitchType'].value_counts()
    return [
        {'abbreviation': pitch_order.get(t, t),
         'color': pitch_point_colors.get(t, '#888888'),
         'count': int(counts[t])}
        for t in _pitch_types(rows)
    ]


def _kde_grid(
    x: np.ndarray, y: np.ndarray, xlim: tuple[float, float], ylim: tuple[float, float],
    bw_adjust: float, values: np.ndarray | None = None,
) -> tuple[list[float], list[float], np.ndarray, np.ndarray | None]:
    """
    Gaussian KDE of (x, y) on a regular grid over the axes' own limits, Scott's-rule
    bandwidth like seaborn's kdeplot (times bw_adjust). Returns (gx, gy, density, mean)
    where density is scaled to a 0-1 peak and `mean` -- only when `values` is given --
    is the kernel-weighted mean of `values` at each grid cell (None where there's no
    density to speak of).

    Evaluated in chunks so the (cells x pitches) weight matrix never gets large.
    """
    pts = np.column_stack([x, y])
    n = len(pts)
    cov = np.cov(pts.T) + np.eye(2) * 1e-6
    kernel_cov = cov * (n ** (-1 / 6) * bw_adjust) ** 2
    inv = np.linalg.inv(kernel_cov)

    gx = np.linspace(xlim[0], xlim[1], _GRID_POINTS)
    gy = np.linspace(ylim[0], ylim[1], _GRID_POINTS)
    cells = np.column_stack([np.repeat(gx, _GRID_POINTS), np.tile(gy, _GRID_POINTS)])

    density = np.empty(len(cells))
    weighted = np.empty(len(cells)) if values is not None else None
    for start in range(0, len(cells), 256):
        diff = cells[start:start + 256, None, :] - pts[None, :, :]
        w = np.exp(-0.5 * np.einsum('cni,ij,cnj->cn', diff, inv, diff))
        density[start:start + 256] = w.sum(axis=1)
        if weighted is not None and values is not None:
            weighted[start:start + 256] = (w * values[None, :]).sum(axis=1)

    peak = density.max()
    norm = density / peak if peak > 0 else density
    mean = None
    if weighted is not None:
        with np.errstate(invalid='ignore', divide='ignore'):
            mean = np.where(norm > 0.08, weighted / density, np.nan)
    # density[i * G + j] is (gx[i], gy[j]); plotly wants z[row=y][col=x]
    z = norm.reshape(_GRID_POINTS, _GRID_POINTS).T
    mean_grid = mean.reshape(_GRID_POINTS, _GRID_POINTS).T if mean is not None else None
    return gx.tolist(), gy.tolist(), z, mean_grid


# ----------------------------------------------------------------------------- traces

def _marker_line() -> dict[str, Any]:
    return {'color': 'rgba(0,0,0,0.55)', 'width': 0.5}


def _hover(scale: ValueScale) -> str:
    return f'<b>%{{customdata[0]}}</b><br>%{{customdata[1]:.{scale.digits}f}}{scale.hover_suffix}<extra></extra>'


def _names(rows: pd.DataFrame, default: str, label_col: str | None) -> list[str]:
    return rows[label_col].tolist() if label_col else [default] * len(rows)


def _points_trace(
    rows: pd.DataFrame, xcol: str, ycol: str, name: str, color: str,
    symbol: str | list[str], scale: ValueScale, label_col: str | None = None,
) -> dict[str, Any]:
    values = _floats(pd.to_numeric(rows[scale.column], errors='coerce'), scale.digits)
    return {
        'type': 'scatter', 'mode': 'markers', 'name': name, 'showlegend': False,
        'x': _floats(rows[xcol]), 'y': _floats(rows[ycol]),
        'customdata': [[n, v] for n, v in zip(_names(rows, name, label_col), values)],
        'hovertemplate': _hover(scale),
        'marker': {'color': color, 'symbol': symbol, 'size': 9, 'opacity': 0.7, 'line': _marker_line()},
    }


def _mean_marker(rows: pd.DataFrame, xcol: str, ycol: str, color: str) -> dict[str, Any]:
    return {
        'type': 'scatter', 'mode': 'markers', 'showlegend': False, 'hoverinfo': 'skip',
        'x': [round(float(rows[xcol].mean()), 3)], 'y': [round(float(rows[ycol].mean()), 3)],
        'marker': {'color': color, 'size': 11, 'line': {'color': '#ffffff', 'width': 1.5}},
    }


def _density_trace(
    rows: pd.DataFrame, xcol: str, ycol: str, color: str,
    xlim: tuple[float, float], ylim: tuple[float, float],
) -> dict[str, Any]:
    n = len(rows)
    gx, gy, z, _ = _kde_grid(
        rows[xcol].to_numpy(float), rows[ycol].to_numpy(float), xlim, ylim,
        bw_adjust=1.5 if n < 20 else 1.0)
    return {
        'type': 'contour', 'x': _floats(gx), 'y': _floats(gy),
        'z': [_floats(r, 4) for r in z],
        'showscale': False, 'hoverinfo': 'skip', 'line': {'width': 0},
        'colorscale': [[0, _with_alpha(color, 0)], [1, color]],
        'contours': {'coloring': 'fill', 'showlines': False, 'start': 0.12, 'end': 1.0, 'size': 0.088},
    }


def _value_density_trace(
    rows: pd.DataFrame, xcol: str, ycol: str, scale: ValueScale,
    lim: tuple[float, float], xlim: tuple[float, float], ylim: tuple[float, float],
) -> dict[str, Any]:
    n = len(rows)
    gx, gy, _, mean = _kde_grid(
        rows[xcol].to_numpy(float), rows[ycol].to_numpy(float), xlim, ylim,
        bw_adjust=1.5 if n < 20 else 1.0, values=rows[scale.column].to_numpy(float))
    assert mean is not None
    lo, hi = lim
    return {
        'type': 'contour', 'x': _floats(gx), 'y': _floats(gy),
        'z': [_floats(r, 3) for r in mean],
        'zmin': round(lo, 3), 'zmax': round(hi, 3), 'connectgaps': False,
        'hovertemplate': f'%{{z:.{scale.digits}f}}{scale.hover_suffix}<extra></extra>', 'line': {'width': 0},
        'colorscale': [list(stop) for stop in scale.colorscale], 'opacity': 0.9,
        'contours': {'coloring': 'fill', 'showlines': False, 'start': lo, 'end': hi, 'size': (hi - lo) / 10},
        'colorbar': _colorbar(scale),
    }


def _colorbar(scale: ValueScale) -> dict[str, Any]:
    """
    The color key: a short horizontal bar laid over the top edge of the plot.

    Placed inside the plot area on purpose. A vertical bar in the right margin makes
    Plotly widen that margin, which shrinks the plot every time the user switches to
    a value color mode; inside the plot it can't change the plot's size. The top strip
    (above a 4.5 ft pitch, past +-22 in of break) is nearly always empty.
    """
    return {
        'orientation': 'h', 'x': 0.5, 'xanchor': 'center', 'y': 0.995, 'yanchor': 'top',
        'xref': 'paper', 'yref': 'paper', 'len': 0.6, 'lenmode': 'fraction', 'thickness': 9,
        'outlinewidth': 0, 'xpad': 0, 'ypad': 0, 'tickfont': {'size': 10},
        'title': {'text': scale.key_title, 'side': 'right', 'font': {'size': 10}},
    }


def _with_alpha(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f'rgba({r},{g},{b},{alpha})'


def _value_points_traces(
    rows: pd.DataFrame, xcol: str, ycol: str, scale: ValueScale,
    symbol_col: str | None, label_col: str | None,
) -> list[dict[str, Any]]:
    """One trace colored by the measurement, a symbol per point (pitch type, or the
    caller's own column) so identity still reads, and a gray trace for points with no
    value rather than dropping them."""
    values = pd.to_numeric(rows[scale.column], errors='coerce')
    tracked = rows[values.notna()]
    untracked = rows[values.isna()]
    traces: list[dict[str, Any]] = []

    if not untracked.empty:
        traces.append({
            **_points_trace(untracked, xcol, ycol, scale.missing_label, '#888888', 'circle', scale),
            'customdata': [[scale.missing_label, None]] * len(untracked),
        })
    if not tracked.empty:
        lo, hi = scale.lim or (float(values.min()), float(values.max()))
        if hi - lo < 1e-9:
            lo, hi = lo - 0.5, hi + 0.5
        symbols = tracked[symbol_col].tolist() if symbol_col else [
            _style(t)['symbol'] for t in tracked['TaggedPitchType']]
        default_names = [pitch_order.get(t, t) for t in tracked['TaggedPitchType']]
        names = tracked[label_col].tolist() if label_col else default_names
        traces.append({
            'type': 'scatter', 'mode': 'markers', 'name': 'Points', 'showlegend': False,
            'x': _floats(tracked[xcol]), 'y': _floats(tracked[ycol]),
            'customdata': [[n, v] for n, v in zip(names, _floats(tracked[scale.column], scale.digits))],
            'hovertemplate': _hover(scale),
            'marker': {
                'color': _floats(tracked[scale.column], scale.digits),
                'colorscale': [list(stop) for stop in scale.colorscale],
                'cmin': round(lo, 3), 'cmax': round(hi, 3), 'showscale': True,
                'colorbar': _colorbar(scale),
                'symbol': symbols, 'size': 9, 'opacity': 0.8, 'line': _marker_line(),
            },
        })
    return traces


def _cloud_traces(
    rows: pd.DataFrame, xcol: str, ycol: str, color_by: str, view: str, scale: ValueScale,
    xlim: tuple[float, float], ylim: tuple[float, float],
    symbol_col: str | None = None, label_col: str | None = None,
) -> list[dict[str, Any]]:
    """
    The data layer every chart shares. color_by 'pitch_type' draws one trace (or density)
    per pitch type; anything else colors by `scale`. view picks points or a density --
    except that a group too small to trust a density (HEATMAP_MIN_PITCHES) stays points.
    """
    rows = rows.assign(**{col: pd.to_numeric(rows[col], errors='coerce') for col in (xcol, ycol, scale.column)})
    rows = rows.dropna(subset=[xcol, ycol])
    rows = rows[rows['TaggedPitchType'] != 'n/a']
    if rows.empty:
        return []

    if color_by != 'pitch_type':
        values = rows[scale.column]
        has_value = rows[values.notna()]
        if view == 'heatmap' and len(has_value) >= HEATMAP_MIN_PITCHES:
            lim = scale.lim or (float(values.min()), float(values.max()))
            if lim[1] - lim[0] < 1e-9:
                lim = (lim[0] - 0.5, lim[1] + 0.5)
            traces = [_value_density_trace(has_value, xcol, ycol, scale, lim, xlim, ylim)]
            untracked = rows[values.isna()]
            if not untracked.empty:
                traces.append(_points_trace(untracked, xcol, ycol, scale.missing_label, '#888888', 'circle', scale))
            return traces
        return _value_points_traces(rows, xcol, ycol, scale, symbol_col, label_col)

    traces = []
    for pitch_type in _pitch_types(rows):
        subset = rows[rows['TaggedPitchType'] == pitch_type]
        style = _style(pitch_type)
        if view == 'heatmap' and len(subset) >= HEATMAP_MIN_PITCHES:
            traces.append(_density_trace(subset, xcol, ycol, style['color'], xlim, ylim))
            traces.append(_mean_marker(subset, xcol, ycol, style['color']))
        else:
            symbol: str | list[str] = subset[symbol_col].tolist() if symbol_col else style['symbol']
            traces.append(_points_trace(subset, xcol, ycol, style['abbr'], style['color'], symbol,
                                        scale, label_col))
    return traces


# ----------------------------------------------------------------------------- layout

def _layout(
    xtitle: str, ytitle: str, xlim: tuple[float, float], ylim: tuple[float, float],
    shapes: list[dict[str, Any]], zeroline: bool = False, equal_aspect: bool = True,
) -> dict[str, Any]:
    axis = {
        'showgrid': True, 'gridcolor': GRID, 'zeroline': zeroline, 'zerolinecolor': MUTED,
        'linecolor': MUTED, 'ticks': 'outside', 'fixedrange': True,
    }
    return {
        'paper_bgcolor': 'rgba(0,0,0,0)', 'plot_bgcolor': 'rgba(0,0,0,0)',
        'font': {'family': 'Cambria, Georgia, serif', 'color': INK, 'size': 12},
        'margin': {'l': 46, 'r': 10, 't': 8, 'b': 42},
        'showlegend': False, 'dragmode': False, 'hoverlabel': {'font': {'color': INK}, 'bgcolor': '#ffffff'},
        'xaxis': {**axis, 'range': list(xlim), 'title': {'text': xtitle, 'standoff': 4}, 'constrain': 'domain'},
        'yaxis': {**axis, 'range': list(ylim), 'title': {'text': ytitle, 'standoff': 4},
                  **({'scaleanchor': 'x', 'scaleratio': 1, 'constrain': 'domain'} if equal_aspect else {})},
        'shapes': shapes,
        'annotations': [],
    }


def base_layout(
    xtitle: str, ytitle: str, xlim: tuple[float, float], ylim: tuple[float, float],
    shapes: list[dict[str, Any]] | None = None, *, equal_aspect: bool = True,
) -> dict[str, Any]:
    """
    The app's standard chart layout -- fonts, grid, margins, transparent background -- for a
    school's custom chart (see hitter_stats.CustomChart). Pass equal_aspect=False for axes that
    aren't both feet or inches (exit velocity against launch angle, say).
    """
    return _layout(xtitle, ytitle, xlim, ylim, shapes or [], equal_aspect=equal_aspect)


def floats(values: Any, digits: int = 3) -> list[float | None]:
    """Numbers as JSON-safe floats (NaN becomes null), for a custom chart's traces."""
    return _floats(values, digits)


def _zone_shapes() -> list[dict[str, Any]]:
    """Strike zone (dashed), the shadow zone one baseball out (dotted) and home plate."""
    pad = BASEBALL_WIDTH
    return [
        {'type': 'rect', 'name': 'ink', 'layer': 'above',
         'x0': -ZONE_SIDE, 'x1': ZONE_SIDE, 'y0': ZONE_BOTTOM, 'y1': ZONE_TOP,
         'line': {'color': INK, 'width': 2, 'dash': 'dash'}},
        {'type': 'rect', 'name': 'muted', 'layer': 'above',
         'x0': -ZONE_SIDE - pad, 'x1': ZONE_SIDE + pad, 'y0': ZONE_BOTTOM - pad, 'y1': ZONE_TOP + pad,
         'line': {'color': MUTED, 'width': 1, 'dash': 'dot'}},
        {'type': 'path', 'name': 'muted', 'layer': 'above',
         'path': 'M -0.35,0.025 L 0.35,0.025 L 0.35,0.45 L 0,0.8 L -0.35,0.45 Z',
         'line': {'color': MUTED, 'width': 1}},
    ]


def _empty_note(layout: dict[str, Any], text: str, x: float, y: float) -> None:
    layout['annotations'].append(
        {'x': x, 'y': y, 'xref': 'x', 'yref': 'y', 'text': text, 'showarrow': False,
         'font': {'size': 14}})


# ------------------------------------------------------------------ pitch location + movement

def location_figure(
    rows: pd.DataFrame, batter_side: str, color_by: str, view: str,
    velo_lim: tuple[float, float] | None,
) -> dict[str, Any]:
    """Plate-location chart for one pitcher's pitches to `batter_side` ('Left'/'Right')."""
    layout = _layout('Plate Location Side (ft)', 'Plate Location Height (ft)',
                     LOCATION_XLIM, LOCATION_YLIM, _zone_shapes())
    side_rows = rows[rows['BatterSide'] == batter_side]
    data = _cloud_traces(side_rows, 'PlateLocSide', 'PlateLocHeight', color_by, view,
                         PITCH_VELO.with_lim(velo_lim), LOCATION_XLIM, LOCATION_YLIM)
    if not data:
        _empty_note(layout, f'No data for {batter_side}-handed batters', 0, 2.5)
    return {'data': data, 'layout': layout}


def break_figure(
    rows: pd.DataFrame, color_by: str, view: str, velo_lim: tuple[float, float] | None,
    show_arrows: bool,
) -> tuple[dict[str, Any], float | None]:
    """
    Movement chart (horizontal vs induced vertical break) and the pitcher's overall arm
    angle -- the direction of the average movement vector, None with no data.

    The arm angle is computed even when show_arrows is off; it's shown outside the chart.
    """
    layout = _layout('HB (in)', 'IVB (in)',
                     BREAK_LIM, BREAK_LIM, [], zeroline=True)
    rows = rows.dropna(subset=['HorzBreak', 'InducedVertBreak'])
    rows = rows[rows['TaggedPitchType'] != 'n/a']
    data = _cloud_traces(rows, 'HorzBreak', 'InducedVertBreak', color_by, view,
                         PITCH_VELO.with_lim(velo_lim), BREAK_LIM, BREAK_LIM)
    if not data:
        _empty_note(layout, 'No movement data', 0, 0)
        return {'data': data, 'layout': layout}, None

    arm_angle = float(np.degrees(np.arctan2(rows['InducedVertBreak'].mean(), rows['HorzBreak'].mean())))
    if show_arrows:
        for pitch_type in _pitch_types(rows):
            subset = rows[rows['TaggedPitchType'] == pitch_type]
            layout['annotations'].append(_arrow(
                subset['HorzBreak'].mean(), subset['InducedVertBreak'].mean(),
                _style(pitch_type)['color'], 2))
        layout['annotations'].append(_arrow(
            rows['HorzBreak'].mean(), rows['InducedVertBreak'].mean(), '#888888', 3, name='overall'))
    return {'data': data, 'layout': layout}, arm_angle


FLIGHT_COLUMNS = ('x0', 'y0', 'z0', 'vx0', 'vy0', 'vz0', 'ax0', 'ay0', 'az0')
_PLATE_FRONT_FT = 17 / 12
_GRAVITY = 32.174
_TIME_STEPS = 31


def flight_path_figure(
    rows: pd.DataFrame, show_pitch_paths: bool = True, show_no_spin: bool = True,
) -> dict[str, Any]:
    """
    Experimental: the pitcher's-eye view of each pitch type's flight -- where the ball is,
    left/right and up/down, from release to the front of the plate. Solid is the actual path
    (averaged over the pitches of that type); dotted is the path the same release would take
    with no spin (a straight line, bent only by gravity), so the gap between them is the
    movement. It needs no spin data, only TrackMan's fitted trajectory: with constant
    acceleration, position = p0 + v0*t + a*t^2/2 (checked against PlateLocSide/PlateLocHeight,
    r > 0.999).

    TrackMan's x is already the pitcher's view (positive = the pitcher's right; it is
    PlateLocSide, the catcher's view, negated), so it is plotted as is.
    """
    layout = _layout('Horizontal position, pitcher\'s view (ft)', 'Height (ft)', (-3, 3), (0, 8),
                     _zone_shapes())
    rows = rows[rows['TaggedPitchType'] != 'n/a']
    if not set(FLIGHT_COLUMNS) <= set(rows.columns):
        _empty_note(layout, 'No trajectory data', 0, 4)
        return {'data': [], 'layout': layout}
    rows = rows.assign(**{c: pd.to_numeric(rows[c], errors='coerce') for c in FLIGHT_COLUMNS})

    steps = np.linspace(0, 1, _TIME_STEPS)
    marker_size = [7] + [0] * (_TIME_STEPS - 2) + [9]  # release point and arrival at the plate
    traces: list[dict[str, Any]] = []
    for pitch_type in _pitch_types(rows):
        subset = rows[rows['TaggedPitchType'] == pitch_type].dropna(subset=list(FLIGHT_COLUMNS))
        # Flight time: the earlier root of y0 + vy0*t + ay0*t^2/2 = front of the plate.
        disc = subset['vy0'] ** 2 - 2 * subset['ay0'] * (subset['y0'] - _PLATE_FRONT_FT)
        subset = subset[disc >= 0]
        if subset.empty:
            continue
        flight = (-subset['vy0'] - np.sqrt(disc[disc >= 0])) / subset['ay0']
        t = flight.to_numpy()[:, None] * steps[None, :]
        col = lambda name: subset[name].to_numpy()[:, None]  # noqa: E731
        x = col('x0') + col('vx0') * t + col('ax0') * t ** 2 / 2
        z = col('z0') + col('vz0') * t + col('az0') * t ** 2 / 2
        x_ref = col('x0') + col('vx0') * t
        z_ref = col('z0') + col('vz0') * t - _GRAVITY * t ** 2 / 2
        distance = -(col('vy0') * t + col('ay0') * t ** 2 / 2)
        style = _style(pitch_type)
        # Every pitch behind the average, as one trace (NaN column = gap between pitches).
        # The fewer the pitches, the more opaque each line, so a lone pitch isn't a ghost.
        if show_pitch_paths:
            gap = np.full((len(subset), 1), np.nan)
            traces.append({
                'type': 'scatter', 'mode': 'lines', 'name': f"{style['abbr']} each pitch",
                'x': _floats(np.hstack([x, gap]).ravel(), 3), 'y': _floats(np.hstack([z, gap]).ravel(), 3),
                'line': {'color': style['color'], 'width': 1},
                'opacity': round(min(0.4, max(0.06, 3 / len(subset))), 2), 'hoverinfo': 'skip',
            })
        for label, xs, zs, line, size in (
            ('actual', x, z, {'width': 2.5}, marker_size),
            ('no spin', x_ref, z_ref, {'width': 1.5, 'dash': 'dot'}, [0] * _TIME_STEPS),
        ):
            if label == 'no spin' and not show_no_spin:
                continue
            traces.append({
                'type': 'scatter', 'mode': 'lines+markers', 'name': f"{style['abbr']} {label}",
                'x': _floats(xs.mean(axis=0), 3), 'y': _floats(zs.mean(axis=0), 3),
                'customdata': _floats(distance.mean(axis=0), 1),
                'line': {'color': style['color'], **line},
                'marker': {'color': style['color'], 'size': size},
                'hovertemplate': '%{fullData.name}<br>%{customdata:.0f} ft from release<extra></extra>',
            })
    if not traces:
        _empty_note(layout, 'No trajectory data', 0, 4)
        return {'data': [], 'layout': layout}

    xs_all = [v for tr in traces for v in tr['x'] if v is not None]
    zs_all = [v for tr in traces for v in tr['y'] if v is not None]
    reach = max(2.5, math.ceil(max(abs(min(xs_all)), abs(max(xs_all))) * 2) / 2)
    layout['xaxis']['range'] = [-reach, reach]
    layout['yaxis']['range'] = [0, max(7.5, math.ceil(max(zs_all)) + 0.5)]
    layout['annotations'].append(
        {'xref': 'paper', 'yref': 'paper', 'x': 0.01, 'y': 0.99, 'xanchor': 'left', 'yanchor': 'top',
         'text': 'Solid: actual path · Dotted: no-spin path' if show_no_spin else 'Solid: actual path',
         'showarrow': False, 'font': {'size': 11}})
    return {'data': traces, 'layout': layout}


def _arrow(x: float, y: float, color: str, width: float, name: str = '') -> dict[str, Any]:
    return {
        'name': name, 'x': round(float(x), 3), 'y': round(float(y), 3), 'ax': 0, 'ay': 0,
        'xref': 'x', 'yref': 'y', 'axref': 'x', 'ayref': 'y', 'text': '', 'showarrow': True,
        'arrowhead': 2, 'arrowsize': 1, 'arrowwidth': width, 'arrowcolor': color,
    }


# ------------------------------------------------------------------------- batted-ball spray

DISTANCE_RINGS_FT = (100, 200, 300, 400)


def _polar(distance: Any, bearing_deg: Any) -> tuple[Any, Any]:
    """TrackMan landing data to feet: bearing is degrees off center field, negative toward
    the left-field line, so a pulled ball from a right-handed hitter lands at negative x."""
    rad = np.radians(bearing_deg)
    return distance * np.sin(rad), distance * np.cos(rad)


def _arc_path(feet: float) -> str:
    xs, ys = _polar(feet, np.linspace(-45, 45, 60))
    return 'M ' + ' L '.join(f'{x:.1f},{y:.1f}' for x, y in zip(xs, ys))


def _field_shapes() -> list[dict[str, Any]]:
    """Foul lines, outfield wall, infield diamond and dotted distance rings."""
    fx, fy = _polar(400, 45)
    bx, by = _polar(90, 45)
    shapes: list[dict[str, Any]] = [
        {'type': 'line', 'name': 'muted', 'x0': 0, 'y0': 0, 'x1': -fx, 'y1': fy,
         'line': {'color': MUTED, 'width': 1}, 'opacity': 0.6},
        {'type': 'line', 'name': 'muted', 'x0': 0, 'y0': 0, 'x1': fx, 'y1': fy,
         'line': {'color': MUTED, 'width': 1}, 'opacity': 0.6},
        {'type': 'path', 'name': 'muted', 'path': _arc_path(400),
         'line': {'color': MUTED, 'width': 1}, 'opacity': 0.6},
        {'type': 'path', 'name': 'muted',
         'path': f'M 0,0 L {bx:.1f},{by:.1f} L 0,{2 * by:.1f} L {-bx:.1f},{by:.1f} Z',
         'line': {'color': MUTED, 'width': 1}, 'opacity': 0.45},
    ]
    for feet in DISTANCE_RINGS_FT[:-1]:
        shapes.append({'type': 'path', 'name': 'muted', 'path': _arc_path(feet),
                       'line': {'color': MUTED, 'width': 0.9, 'dash': 'dot'}, 'opacity': 0.35})
    return shapes


def _distance_labels() -> list[dict[str, Any]]:
    """Ring distances along the first-base line, nudged into foul ground where no batted
    ball can plot -- without them a landing spot reads as a direction only."""
    along = np.array(_polar(1, 45))
    normal = np.array([along[1], -along[0]])
    labels = []
    for feet in DISTANCE_RINGS_FT:
        at = np.array(_polar(feet, 45)) + normal * 24
        labels.append({
            'x': round(float(at[0]), 1), 'y': round(float(at[1]), 1), 'xref': 'x', 'yref': 'y',
            'text': f'{feet} ft' if feet == DISTANCE_RINGS_FT[-1] else str(feet),
            'showarrow': False, 'textangle': -45, 'font': {'size': 10},
        })
    return labels


def spray_figure(
    rows: pd.DataFrame, pitcher_side: str, color_by: str, view: str,
    ev_lim: tuple[float, float] | None,
) -> dict[str, Any]:
    """
    Where one hitter's batted balls landed against `pitcher_side` ('Left'/'Right') pitching.

    Landing spots come from Bearing and Distance (PitchLastMeasuredX/Z are empty in TrackMan
    exports). Marker shape is the batted-ball type in every mode; color is the pitch type
    or, for 'velo', exit velocity on a scale pinned to ev_lim (the hitter's own unfiltered
    quartiles).
    """
    axis = {'visible': False, 'fixedrange': True, 'showgrid': False, 'zeroline': False}
    layout = _layout('', '', SPRAY_XLIM, SPRAY_YLIM, _field_shapes())
    layout['margin'] = {'l': 6, 'r': 6, 't': 6, 'b': 6}
    layout['xaxis'] = {**axis, 'range': list(SPRAY_XLIM), 'constrain': 'domain'}
    layout['yaxis'] = {**axis, 'range': list(SPRAY_YLIM), 'scaleanchor': 'x', 'scaleratio': 1,
                       'constrain': 'domain'}
    layout['annotations'] = _distance_labels()

    side = rows[rows['PitcherThrows'].fillna('').astype(str) == pitcher_side] if 'PitcherThrows' in rows else rows.iloc[0:0]
    side = side[side['PitchCall'].fillna('').astype(str) == 'InPlay'] if 'PitchCall' in side else side.iloc[0:0]
    side = side.assign(**{col: pd.to_numeric(side[col], errors='coerce') for col in ('Bearing', 'Distance', 'Angle')
                          if col in side.columns})
    side = side.dropna(subset=['Bearing', 'Distance'])
    if 'ExitSpeed' not in side.columns:
        side = side.assign(ExitSpeed=np.nan)

    if side.empty:
        _empty_note(layout, f'No batted balls vs {pitcher_side}-handed pitching', 0, 215)
        return {'data': [], 'layout': layout}

    x, y = _polar(side['Distance'].to_numpy(float), side['Bearing'].to_numpy(float))
    hit_type = classify_hit_type(side['Angle'] if 'Angle' in side.columns else pd.Series(np.nan, index=side.index))
    hit_names = hit_type.astype(object).where(hit_type.notna(), 'Pop')
    side = side.assign(
        _x=x, _y=y,
        _symbol=[_SYMBOL_BY_HIT_TYPE.get(str(h), 'circle') for h in hit_names],
        _label=[f'{pitch_order.get(t, t)} · {h}' for t, h in zip(side['TaggedPitchType'], hit_names)])
    if 'TaggedPitchType' not in side.columns:
        side = side.assign(TaggedPitchType='n/a')

    data = _cloud_traces(side, '_x', '_y', color_by, view, EXIT_VELO.with_lim(ev_lim),
                         SPRAY_XLIM, SPRAY_YLIM, symbol_col='_symbol', label_col='_label')
    if not data:
        _empty_note(layout, f'No batted balls vs {pitcher_side}-handed pitching', 0, 215)
        return {'data': data, 'layout': layout}

    # Marker shape is the batted-ball type, so that key stays: legend-only traces, parked in
    # the bottom-right corner (foul ground, where no batted ball can plot).
    for label, symbol in _SYMBOL_BY_HIT_TYPE.items():
        data.append({
            'type': 'scatter', 'mode': 'markers', 'x': [None], 'y': [None], 'name': label,
            'showlegend': True, 'hoverinfo': 'skip',
            'marker': {'symbol': symbol, 'color': '#888888', 'size': 9, 'line': _marker_line()},
        })
    layout['showlegend'] = True
    layout['legend'] = {'x': 0.995, 'y': 0.005, 'xanchor': 'right', 'yanchor': 'bottom',
                        'bgcolor': 'rgba(0,0,0,0)', 'font': {'size': 10}, 'itemsizing': 'constant'}
    return {'data': data, 'layout': layout}


# ------------------------------------------------------------------------ catcher framing

def catcher_figure(
    taken: pd.DataFrame, kind: str, color_by: str, view: str,
    velo_lim: tuple[float, float] | None,
) -> dict[str, Any]:
    """
    Taken pitches (called balls and strikes) a catcher received, with their framing value.

    kind 'notable' keeps only the pitches that moved the needle (|framing value| at least
    MIN_NOTABLE_FRAMING_VALUE); 'all' keeps every taken pitch. color_by is 'framing'
    (lost -> stolen on a fixed scale), 'pitch_type' or 'velo'. The strongest pitches are
    drawn last so they sit on top of weaker, overlapping ones.
    """
    layout = _layout('Plate Location Side (ft)', 'Plate Location Height (ft)',
                     LOCATION_XLIM, LOCATION_YLIM, _zone_shapes())
    rows = taken
    if kind == 'notable' and not rows.empty:
        rows = rows[rows['framing_value'].abs() >= MIN_NOTABLE_FRAMING_VALUE]
    if not rows.empty:
        rows = rows.iloc[rows['framing_value'].abs().argsort(kind='stable')]

    scale = {'framing': FRAMING, 'velo': PITCH_VELO.with_lim(velo_lim)}.get(color_by, PITCH_VELO)
    data = _cloud_traces(rows, 'PlateLocSide', 'PlateLocHeight', color_by, view, scale,
                         LOCATION_XLIM, LOCATION_YLIM) if not rows.empty else []
    if not data:
        _empty_note(layout, 'No notable framing events for this catcher' if kind == 'notable'
                    else 'No taken-pitch data for this catcher', 0, 2.5)
    return {'data': data, 'layout': layout}
