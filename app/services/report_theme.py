import math
from typing import NamedTuple

import matplotlib
import numpy as np
import pandas as pd

# Use a non-interactive backend for matplotlib
matplotlib.use('Agg')

from matplotlib.colors import Colormap, LinearSegmentedColormap, to_rgb
from matplotlib.patches import Rectangle
import matplotlib.patches as patches

BASEBALL_WIDTH = 0.24  # Approximate width of a baseball in feet

# Strike zone bounds in feet. make_strike_zone() draws exactly this box, so any
# zone/chase calculation must read from here rather than repeating the numbers.
ZONE_SIDE = 0.83    # half-width, so the zone spans -0.83 to 0.83
ZONE_BOTTOM = 1.5
ZONE_TOP = 3.5


def in_zone(plate_loc_side: pd.Series, plate_loc_height: pd.Series) -> pd.Series:
    """
    Boolean mask for pitches inside the strike zone.

    Accepts Series (vectorized) or scalars. NaN locations fall out as False, which
    is the safe reading -- an untracked pitch is not evidence of a strike.
    """
    return (
        (plate_loc_side.abs() <= ZONE_SIDE)
        & (plate_loc_height >= ZONE_BOTTOM)
        & (plate_loc_height <= ZONE_TOP)
    )

STRIKE_PROB_TRANSITION_FT = 0.25  # 50%->~88%/~12% band straddling the rulebook edge


def strike_probability(plate_loc_side: float, plate_loc_height: float) -> float:
    """
    Fixed geometric model of the probability a pitch at this location gets
    called a strike, based purely on its distance from the rulebook zone edge --
    no archived-pitch-history dependency, so it's identical for every school
    from day one.

    Exactly 50% right on the edge (the catching report's own "true toss-up
    point"), approaching 100% toward the center of the zone, approaching 0%
    a few inches outside it.
    """
    dx = max(0.0, abs(plate_loc_side) - ZONE_SIDE)
    dy = max(0.0, ZONE_BOTTOM - plate_loc_height, plate_loc_height - ZONE_TOP)
    if dx > 0 or dy > 0:
        signed_distance = (dx ** 2 + dy ** 2) ** 0.5  # outside the zone: positive
    else:
        signed_distance = -min(
            ZONE_SIDE - abs(plate_loc_side),
            plate_loc_height - ZONE_BOTTOM,
            ZONE_TOP - plate_loc_height,
        )  # inside the zone: negative (distance to the nearest edge)
    return 1 / (1 + math.exp(signed_distance / STRIKE_PROB_TRANSITION_FT))


def out_of_zone(plate_loc_side: pd.Series, plate_loc_height: pd.Series) -> pd.Series:
    """
    Boolean mask for pitches outside the strike zone.

    Accepts Series (vectorized) or scalars. NaN locations fall out as True, which
    is the safe reading -- an untracked pitch is not evidence of a strike.
    """
    return (
        (plate_loc_side.abs() > ZONE_SIDE)
        | (plate_loc_height < ZONE_BOTTOM)
        | (plate_loc_height > ZONE_TOP)
    )

# Exit velocity is a magnitude, so it takes a sequential ramp -- one that climbs
# steadily in lightness, not a rainbow that makes the reader decode an arbitrary
# hue order.
#
# One ramp serves both themes, deliberately. This used to flip to Reds_r on dark
# so the hardest contact stayed the most visible against a transparent
# background, but that inverted what a colour *means*: 120 mph read deep red on a
# light page and pale on a dark one, so anyone who learned the scale in one theme
# read it backwards in the other. A legend that changes direction is worse than
# one that is slightly less loud.
#
# Legibility is handled without flipping. Both ends of the base ramp are trimmed
# off, so it never reaches the near-white that vanishes on a light page or the
# near-black that vanishes on a dark one, and every marker already carries a
# theme-coloured outline that locates it whatever its fill.
EV_MIN_MPH = 60.0
EV_MAX_MPH = 120.0

_EV_BASE_CMAP = 'YlOrRd'
_EV_RANGE = (0.15, 0.85)    # fraction of the base ramp kept, low end first


def ev_colormap(theme: str = 'light') -> Colormap:
    """
    Sequential colormap for exit velocity: warm yellow at EV_MIN_MPH through to
    deep red at EV_MAX_MPH, identically in every theme.

    theme is accepted and ignored. Callers pass it, and keeping it in the
    signature leaves the door open if a theme ever does need its own ramp -- but
    see above for why reversing this one is not the way to do it.
    """
    base = matplotlib.colormaps[_EV_BASE_CMAP]
    cmap = LinearSegmentedColormap.from_list(
        'exit_velocity', base(np.linspace(*_EV_RANGE, 256)))
    # Balls in play without a tracked exit speed still have a landing spot, so
    # they are plotted -- in neutral gray rather than silently at the ramp's end.
    cmap.set_bad('#888888')
    return cmap


THEME_COLORS = {
    'light': {
        'figure.facecolor': 'none',
        'figure.edgecolor': 'none',
        'axes.facecolor':   'none',
        'text.color':       '#111111',
        'axes.edgecolor':   '#111111',
        'axes.titlecolor':  '#111111',
        'axes.labelcolor':  '#111111',
        'xtick.color':      '#444444',
        'ytick.color':      '#444444',
        'grid.color':       '#444444',
        'grid.alpha':       0.3,
    },
    'dark': {
        'figure.facecolor': 'none',
        'figure.edgecolor': 'none',
        'axes.facecolor':   'none',
        'text.color':       '#e0e0e0',
        'axes.edgecolor':   '#e0e0e0',
        'axes.titlecolor':  '#e0e0e0',
        'axes.labelcolor':  '#e0e0e0',
        'xtick.color':      '#aaaaaa',
        'ytick.color':      '#aaaaaa',
        'grid.color':       '#aaaaaa',
        'grid.alpha':       0.3,
    },
}

matplotlib.rcParams.update({
    'font.family': 'Cambria',
    'font.size': 18,
    'font.weight': 'bold',
})

# Single source of truth for the pitch type name list -- pitch_order and
# pitch_point_colors below are kept as plain dicts (not folded into one lookup)
# because school-owned custom report scripts (app/storage/schools/*/assets/*.py,
# exec'd server-side) import and .get()/.map() them directly by name.
class _PitchType(NamedTuple):
    abbreviation: str
    color: str

_PITCH_TYPES: dict[str, _PitchType] = {
    'Fastball':    _PitchType('FB', '#d22d49'),
    'Curveball':   _PitchType('CB', '#00d1ed'),
    'Slider':      _PitchType('SL', '#004400'),
    'ChangeUp':    _PitchType('CH', '#1dbe3a'),
    'Splitter':    _PitchType('SP', '#4f0010'),
    'Knuckleball': _PitchType('KB', '#472cee'),
    'Cutter':      _PitchType('CT', '#933f2c'),
    'Sinker':      _PitchType('SK', '#fe9d00'),
    'Four-Seam':   _PitchType('FF', '#FF0088'),
    'Undefined':   _PitchType('UN', '#888888'),
}

# Order to display pitch types in tables and plots
pitch_order = {name: pt.abbreviation for name, pt in _PITCH_TYPES.items()}
pitch_point_colors = {name: pt.color for name, pt in _PITCH_TYPES.items()}

def make_strike_zone() -> Rectangle:
    """Dashed outline of the rulebook strike zone, in plate-location feet."""
    return Rectangle((-ZONE_SIDE, ZONE_BOTTOM), 2 * ZONE_SIDE, ZONE_TOP - ZONE_BOTTOM,
        linewidth=2, edgecolor=matplotlib.rcParams['text.color'], facecolor='none', linestyle='--')

def make_shadow_zone() -> Rectangle:
    """Dotted outline one baseball-width outside the strike zone, for borderline pitches."""
    return Rectangle(
        (-ZONE_SIDE - BASEBALL_WIDTH, ZONE_BOTTOM - BASEBALL_WIDTH),
        2 * ZONE_SIDE + 2 * BASEBALL_WIDTH, 2.0 + 2 * BASEBALL_WIDTH,
        linewidth=1, edgecolor=matplotlib.rcParams['xtick.color'], facecolor='none', linestyle=(0, (1, 10)))

def make_homeplate() -> patches.Polygon:
    """Home plate outline drawn at the front of the strike zone, for orientation."""
    return patches.Polygon([(-0.35, 0.025), (0.35, 0.025), (0.35, 0.45), (0, 0.8), (-0.35, 0.45)],
        linewidth=1, edgecolor=matplotlib.rcParams['xtick.color'], facecolor='none', linestyle='-')

def cmap(hex_color: str, name: str) -> LinearSegmentedColormap:
    """Transparency ramp from invisible to hex_color, for one pitch type's KDE fill."""
    # Build a transparency gradient from fully transparent to the pitch color,
    # so overlapping KDE fills blend cleanly on the white plot background
    r, g, b = to_rgb(hex_color)
    return LinearSegmentedColormap.from_list(name, [(r, g, b, 0), (r, g, b, 1)])
