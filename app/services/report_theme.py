import matplotlib
import numpy as np
import pandas as pd

# Use a non-interactive backend for matplotlib
matplotlib.use('Agg')

from matplotlib.colors import Colormap, LinearSegmentedColormap, to_rgb
from matplotlib.patches import Rectangle
import matplotlib.patches as patches

baseball_width = 0.24  # Approximate width of a baseball in feet

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

# Order to display pitch types in tables and plots
pitch_order = {
    'Fastball': 'FB',
    'Curveball': 'CB',
    'Slider': 'SL',
    'ChangeUp': 'CH',
    'Splitter': 'SP',
    'Knuckleball': 'KB',
    'Cutter': 'CT',
    'Sinker': 'SK',
    'Four-Seam': 'FF',
    'Undefined': 'UN'
}
    
pitch_point_colors = {
    'Fastball': '#d22d49',
    'Curveball': '#00d1ed',
    'Slider': '#004400',
    'ChangeUp': '#1dbe3a',
    'Splitter': '#4f0010',
    'Knuckleball': '#472cee',
    'Cutter': '#933f2c',
    'Sinker': '#fe9d00',
    'Four-Seam': '#FF0088',
    'Undefined': '#888888'
}

def make_strike_zone() -> Rectangle:
    """Dashed outline of the rulebook strike zone, in plate-location feet."""
    return Rectangle((-0.83, 1.5), 1.66, 2.0,
        linewidth=2, edgecolor=matplotlib.rcParams['text.color'], facecolor='none', linestyle='--')

def make_shadow_zone() -> Rectangle:
    """Dotted outline one baseball-width outside the strike zone, for borderline pitches."""
    return Rectangle(
        (-0.83 - baseball_width, 1.5 - baseball_width),
        1.66 + 2 * baseball_width, 2.0 + 2 * baseball_width,
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
