"""
The small strike-zone panel drawn above each at-bat in the pitch-by-pitch PDFs.

Every pitch is a numbered dot placed at its plate location and colored by release velocity
on the same cool-to-hot scale the web charts use. Drawn as native ReportLab vector shapes --
no matplotlib, no image files, no browser round trip -- so it stays sharp at any zoom and
costs almost nothing to build, which matters because a staff's bulk pitch-by-pitch download
draws one of these per at-bat.

Pure Python, no Flask -- see app/services/CLAUDE.md.
"""
from typing import Sequence

from reportlab.graphics.shapes import Circle, Drawing, Line, Polygon, Rect, String
from reportlab.lib.colors import Color, HexColor

from app.services.pitch_stats import PitchByPitchPitch
from app.services.velo_scale import TEMPERATURE, velo_scale
from app.services.report_theme import BASEBALL_WIDTH, ZONE_BOTTOM, ZONE_SIDE, ZONE_TOP

XLIM = (-2.5, 2.5)
YLIM = (0.0, 5.0)
# A pitch tracked well outside the panel (a badly missed target, or a bad location read)
# is pinned just inside the frame rather than clipped, so it stays a legible dot.
MARKER_MARGIN = 0.22

INK = HexColor('#111111')
MUTED = HexColor('#444444')
NO_VELO = HexColor('#888888')

_BAR_STEPS = 32
_BAR_WIDTH = 8.0
_BAR_GAP = 6.0
_LABEL_WIDTH = 20.0


def temperature_color(t: float) -> Color:
    """Color at position t (clamped to 0-1) along the cool-to-hot scale."""
    t = min(max(t, 0.0), 1.0)
    stops = [(pos, HexColor(hex_color)) for pos, hex_color in TEMPERATURE]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if t <= p1:
            f = (t - p0) / (p1 - p0)
            return Color(c0.red + (c1.red - c0.red) * f,
                         c0.green + (c1.green - c0.green) * f,
                         c0.blue + (c1.blue - c0.blue) * f)
    return stops[-1][1]


def _text_color_on(fill: Color) -> Color:
    """Black or white, whichever reads better on `fill` (W3C perceived brightness)."""
    brightness = 0.299 * fill.red + 0.587 * fill.green + 0.114 * fill.blue
    return INK if brightness > 0.5 else HexColor('#ffffff')


def _clamp(x: float, y: float) -> tuple[float, float]:
    return (min(max(x, XLIM[0] + MARKER_MARGIN), XLIM[1] - MARKER_MARGIN),
            min(max(y, YLIM[0] + MARKER_MARGIN), YLIM[1] - MARKER_MARGIN))


def ab_chart_drawing(
    pitches: Sequence[PitchByPitchPitch], width: float, velo_lim: tuple[float, float] | None = None,
) -> Drawing | None:
    """
    The panel for one at-bat, `width` points wide (the square plot plus a velocity key on
    its right). None when no pitch in it has a location -- the PDF then simply shows the
    table without a chart.

    velo_lim fixes the color scale so every at-bat in a report shares one; without it the
    scale comes from this at-bat's own pitches.
    """
    located = [p for p in pitches if p.plate_loc_side is not None and p.plate_loc_height is not None]
    if not located:
        return None

    lo_hi = velo_lim or velo_scale([p.velo for p in located if p.velo is not None])

    side = width - (_BAR_GAP + _BAR_WIDTH + _LABEL_WIDTH)   # the plot is square
    sx = side / (XLIM[1] - XLIM[0])
    sy = side / (YLIM[1] - YLIM[0])

    def px(x: float) -> float:
        return (x - XLIM[0]) * sx

    def py(y: float) -> float:
        return (y - YLIM[0]) * sy

    d = Drawing(width, side)

    # Frame at the panel's own bounds, so a pitch at the edge reads as "at the edge of what
    # this chart tracks" rather than centered just outside an unmarked canvas.
    d.add(Rect(0, 0, side, side, fillColor=None, strokeColor=INK, strokeWidth=0.8))
    d.add(Rect(px(-ZONE_SIDE - BASEBALL_WIDTH), py(ZONE_BOTTOM - BASEBALL_WIDTH),
               2 * (ZONE_SIDE + BASEBALL_WIDTH) * sx, (ZONE_TOP - ZONE_BOTTOM + 2 * BASEBALL_WIDTH) * sy,
               fillColor=None, strokeColor=MUTED, strokeWidth=0.6, strokeDashArray=[1, 3]))
    d.add(Rect(px(-ZONE_SIDE), py(ZONE_BOTTOM), 2 * ZONE_SIDE * sx, (ZONE_TOP - ZONE_BOTTOM) * sy,
               fillColor=None, strokeColor=INK, strokeWidth=1.2, strokeDashArray=[4, 3]))
    plate = [(-0.35, 0.025), (0.35, 0.025), (0.35, 0.45), (0.0, 0.8), (-0.35, 0.45)]
    d.add(Polygon([c for x, y in plate for c in (px(x), py(y))],
                  fillColor=None, strokeColor=MUTED, strokeWidth=0.6))

    radius = side * 0.034
    for pitch in located:
        assert pitch.plate_loc_side is not None and pitch.plate_loc_height is not None
        x, y = _clamp(pitch.plate_loc_side, pitch.plate_loc_height)
        if pitch.velo is not None and lo_hi is not None:
            fill = temperature_color((pitch.velo - lo_hi[0]) / (lo_hi[1] - lo_hi[0]))
        else:
            fill = NO_VELO   # located but no tracked velo: plotted in gray, not dropped
        d.add(Circle(px(x), py(y), radius, fillColor=fill, strokeColor=INK, strokeWidth=0.6))
        d.add(String(px(x), py(y) - radius * 0.38, str(pitch.number), fontName='Helvetica-Bold',
                     fontSize=radius * 1.25, fillColor=_text_color_on(fill), textAnchor='middle'))

    if lo_hi is not None:
        _add_velocity_key(d, side, lo_hi)
    return d


def _add_velocity_key(d: Drawing, plot_side: float, lo_hi: tuple[float, float]) -> None:
    """A vertical gradient bar to the right of the plot with the scale's low/mid/high speeds."""
    x0 = plot_side + _BAR_GAP
    height = plot_side * 0.6
    y0 = (plot_side - height) / 2
    step = height / _BAR_STEPS
    for i in range(_BAR_STEPS):
        d.add(Rect(x0, y0 + i * step, _BAR_WIDTH, step + 0.3,
                   fillColor=temperature_color((i + 0.5) / _BAR_STEPS), strokeColor=None, strokeWidth=0))
    d.add(Rect(x0, y0, _BAR_WIDTH, height, fillColor=None, strokeColor=INK, strokeWidth=0.4))

    lo, hi = lo_hi
    for frac, value in ((0.0, lo), (0.5, (lo + hi) / 2), (1.0, hi)):
        y = y0 + height * frac
        d.add(Line(x0 + _BAR_WIDTH, y, x0 + _BAR_WIDTH + 2, y, strokeColor=INK, strokeWidth=0.4))
        d.add(String(x0 + _BAR_WIDTH + 4, y - 2.2, f'{value:.0f}', fontName='Helvetica',
                     fontSize=6.5, fillColor=INK, textAnchor='start'))
    d.add(String(x0 + _BAR_WIDTH / 2, y0 + height + 5, 'mph', fontName='Helvetica-Bold',
                 fontSize=6.5, fillColor=INK, textAnchor='middle'))
