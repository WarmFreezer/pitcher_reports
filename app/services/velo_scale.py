"""
The velocity color scale shared by every chart: the web (Plotly) charts and the native
ReportLab at-bat panels in the pitch-by-pitch PDFs, so one pitch is the same color everywhere.

Pure Python, no Flask -- see app/services/CLAUDE.md.
"""
from typing import Sequence

# Cool -> hot, centered on a pale midpoint so the median pitch reads neutral and the
# tails read as clearly slow (blue) or fast (red).
TEMPERATURE: list[tuple[float, str]] = [
    (0.0, '#2c7bb6'), (0.25, '#abd9e9'), (0.5, '#ffffbf'), (0.75, '#fdae61'), (1.0, '#d7191c'),
]

MIN_SPAN_MPH = 1.0


def velo_scale(velos: Sequence[float]) -> tuple[float, float] | None:
    """
    The (low, high) ends of the color scale for a set of pitches: their first and third
    quartile, so one badly tracked pitch can't wash out the rest. A very consistent arm gets
    a minimum span so the scale stays readable. None when there is no velocity at all.
    """
    values = sorted(v for v in velos if v == v)   # drops NaN
    if not values:
        return None
    if len(values) == 1:
        return values[0] - MIN_SPAN_MPH / 2, values[0] + MIN_SPAN_MPH / 2

    def quantile(q: float) -> float:
        pos = (len(values) - 1) * q
        lo = int(pos)
        hi = min(lo + 1, len(values) - 1)
        return values[lo] + (values[hi] - values[lo]) * (pos - lo)

    lo, hi = quantile(0.25), quantile(0.75)
    if hi - lo < MIN_SPAN_MPH:
        mid = (lo + hi) / 2
        lo, hi = mid - MIN_SPAN_MPH / 2, mid + MIN_SPAN_MPH / 2
    return lo, hi
