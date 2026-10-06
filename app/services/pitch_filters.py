"""
Pitch-type and velocity filters for the report pages.

One PitchFilters is parsed from the request, then `apply` runs once on the loaded
`source` DataFrame before anything else is computed -- so every stat table, chart
and school custom script downstream sees the same filtered pitches, instead of each
consumer re-implementing the filter.

Pure Python/pandas, no Flask -- see app/services/CLAUDE.md.
"""
import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services.report_theme import pitch_order, pitch_point_colors

MAX_PITCH_TYPES = 40
MAX_PITCH_TYPE_LEN = 40


@dataclass(frozen=True)
class PitchFilters:
    """
    pitch_types: None means "don't restrict by type"; an empty tuple means the user
    unchecked every type, which matches nothing.
    velo_min/velo_max: both None means "don't restrict by velocity". When set, a pitch
    with no tracked velocity is dropped -- it can't be shown to fall in the range.
    """
    pitch_types: tuple[str, ...] | None = None
    velo_min: float | None = None
    velo_max: float | None = None

    @classmethod
    def from_request(cls, raw: Any) -> 'PitchFilters':
        """Parse and validate the `filters` object a client sent. Raises ValueError."""
        if raw in (None, {}):
            return cls()
        if not isinstance(raw, dict):
            raise ValueError('Invalid filters.')

        pitch_types: tuple[str, ...] | None = None
        raw_types = raw.get('pitch_types')
        if raw_types is not None:
            if not isinstance(raw_types, list) or len(raw_types) > MAX_PITCH_TYPES:
                raise ValueError('Invalid pitch type filter.')
            if not all(isinstance(t, str) and len(t) <= MAX_PITCH_TYPE_LEN for t in raw_types):
                raise ValueError('Invalid pitch type filter.')
            pitch_types = tuple(raw_types)

        velo_min = velo_max = None
        raw_velo = raw.get('velo')
        if raw_velo is not None:
            if not isinstance(raw_velo, list) or len(raw_velo) != 2:
                raise ValueError('Invalid velocity filter.')
            lo, hi = raw_velo
            if isinstance(lo, bool) or isinstance(hi, bool) \
                    or not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)) \
                    or not math.isfinite(lo) or not math.isfinite(hi):
                raise ValueError('Invalid velocity filter.')
            velo_min, velo_max = float(min(lo, hi)), float(max(lo, hi))

        return cls(pitch_types=pitch_types, velo_min=velo_min, velo_max=velo_max)

    @property
    def is_active(self) -> bool:
        return self.pitch_types is not None or self.velo_min is not None

    def apply(self, source: pd.DataFrame) -> pd.DataFrame:
        """Rows of `source` that pass. Returns `source` itself when nothing is restricted."""
        if not self.is_active or source.empty:
            return source

        mask = pd.Series(True, index=source.index)
        if self.pitch_types is not None:
            mask &= source['TaggedPitchType'].isin(self.pitch_types)
        if self.velo_min is not None and self.velo_max is not None:
            speed = pd.to_numeric(source['RelSpeed'], errors='coerce')
            mask &= speed.between(self.velo_min, self.velo_max)  # NaN -> False
        return source[mask]


def pitch_type_options(source: pd.DataFrame) -> list[dict[str, Any]]:
    """Every pitch type in `source` (before filtering), canonical order first, with counts."""
    counts = source['TaggedPitchType'].value_counts()
    names = [n for n in counts.index if n != 'n/a']
    order = {name: i for i, name in enumerate(pitch_order)}
    names.sort(key=lambda n: (order.get(n, len(order)), n))
    return [
        {
            'name': n,
            'abbreviation': pitch_order.get(n, n),
            'color': pitch_point_colors.get(n, '#888888'),
            'count': int(counts[n]),
        }
        for n in names
    ]


def velo_bounds(source: pd.DataFrame) -> tuple[int, int] | None:
    """Whole-mph (floor, ceil) bounds of tracked release speed, or None with no data."""
    speed = pd.to_numeric(source['RelSpeed'], errors='coerce').dropna()
    if speed.empty:
        return None
    return int(math.floor(speed.min())), int(math.ceil(speed.max()))
