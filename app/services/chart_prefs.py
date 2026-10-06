"""
The chart options a report page sends with each request: what the color means and whether
the charts are points or densities. Shared by the pitcher, hitter and catcher cards.

Pure Python, no Flask -- see app/services/CLAUDE.md.
"""
from dataclasses import dataclass
from typing import Any

from app.services import plotly_charts


@dataclass(frozen=True)
class ChartPrefs:
    """color_by/view come from the page's controls (seeded from the user's account
    defaults); show_arrows is the account's break-arrow preference (pitcher page only)."""
    color_by: str = 'pitch_type'
    view: str = 'heatmap'
    show_arrows: bool = True

    @classmethod
    def from_request(
        cls, raw: Any, show_arrows: bool = True,
        allowed_colors: tuple[str, ...] = plotly_charts.COLOR_MODES,
    ) -> 'ChartPrefs':
        """Validate the page's options. Raises ValueError. `allowed_colors` widens the set for
        a page with its own meaningful color (the catcher page adds 'framing')."""
        raw = raw if isinstance(raw, dict) else {}
        color_by = raw.get('color_by', 'pitch_type')
        view = raw.get('view', 'heatmap')
        if color_by not in allowed_colors or view not in plotly_charts.VIEWS:
            raise ValueError('Invalid chart options.')
        return cls(color_by=color_by, view=view, show_arrows=show_arrows)
