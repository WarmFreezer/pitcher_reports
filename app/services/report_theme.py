import math
import re
from typing import NamedTuple

import pandas as pd

BASEBALL_WIDTH = 0.24  # Approximate width of a baseball in feet

# Strike zone bounds in feet. The charts draw exactly this box, so any
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

# Single source of truth for the pitch type name list -- pitch_order and
# pitch_point_colors below are kept as plain dicts (not folded into one lookup)
# because school-owned custom report scripts (app/storage/schools/*/assets/*.py,
# exec'd server-side) import and .get()/.map() them directly by name.
class _PitchType(NamedTuple):
    abbreviation: str
    color: str

_PITCH_TYPES: dict[str, _PitchType] = {
    'Fastball':    _PitchType('FB', '#Ff0000'),
    'Curveball':   _PitchType('CB', '#1000FC'),
    'Slider':      _PitchType('SL', '#00FCC5'),
    'ChangeUp':    _PitchType('CH', '#008B13'),
    'Splitter':    _PitchType('SP', '#FC00CA'),
    'Knuckleball': _PitchType('KB', '#472cee'),
    'Cutter':      _PitchType('CT', '#FCBB00'),
    'Sinker':      _PitchType('SK', '#BDFC00'),
    'Four-Seam':   _PitchType('4S', '#fc1c00'),
    'FourSeamFastBall':   _PitchType('4S', '#fc1c00'),
    'Two-Seam':    _PitchType('2S', '#FC9C00'),
    'TwoSeamFastBall':    _PitchType('2S', '#FC9C00'),
    'Sweeper':     _PitchType('SW', '#0090FC'),
    'Undefined':   _PitchType('UN', '#888888'),
}

# Order to display pitch types in tables and plots
pitch_order = {name: pt.abbreviation for name, pt in _PITCH_TYPES.items()}
pitch_point_colors = {name: pt.color for name, pt in _PITCH_TYPES.items()}


def format_result(value: str) -> str:
    """Turn a raw TrackMan enum value (PitchCall/PlayResult/KorBB) like
    'StrikeCalled' or 'InPlay' into a readable 'Strike Called' / 'In Play' for
    display on the pitch-by-pitch report -- splits before every interior
    capital letter, so multi-word values expand the same way without a lookup
    table of every enum value TrackMan exports."""
    if not value:
        return value
    return re.sub(r'(?<!^)(?=[A-Z])', ' ', value)
