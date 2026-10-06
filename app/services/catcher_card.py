"""
One catcher's report, computed for the current filters.

Shared by the web preview (JSON card) and the PDF export. Pure Python/pandas, no Flask and no
db.session -- see app/services/CLAUDE.md.
"""
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services import catching_report, plotly_charts
from app.services.catcher_stats import CatcherFramingTable
from app.services.chart_prefs import ChartPrefs
from app.services.pitch_filters import PitchFilters

# The page's own default: what a framing chart is *for* is framing value, not pitch type.
COLOR_MODES = ('framing', *plotly_charts.COLOR_MODES)


@dataclass
class CatcherCharts:
    figures: dict[str, dict[str, Any]]
    legend: list[dict[str, Any]]
    taken_pitches: int


@dataclass
class CatcherData:
    name: str
    framing_table: CatcherFramingTable | None


def build_catcher_charts(
    source: pd.DataFrame, catcher_id: str | int, filters: PitchFilters, prefs: ChartPrefs,
) -> CatcherCharts:
    """
    The notable-framing-events chart and the all-taken-pitches chart, plus the pitch-type key.

    `source` is the *unfiltered* frame so the velocity color scale is pinned to this catcher's
    own quartiles before filtering and doesn't shift as the sliders move. The framing scale is
    fixed (lost -> stolen, +-0.5).
    """
    full = catching_report.taken_pitches(source, catcher_id)
    velo_lim = plotly_charts.velo_limits(full) if not full.empty else None
    taken = catching_report.taken_pitches(filters.apply(source), catcher_id)

    return CatcherCharts(
        figures={
            'heat_map': plotly_charts.catcher_figure(taken, 'notable', prefs.color_by, prefs.view, velo_lim),
            'pitch_location': plotly_charts.catcher_figure(taken, 'all', prefs.color_by, prefs.view, velo_lim),
        },
        legend=plotly_charts.pitch_type_legend(taken) if not taken.empty else [],
        taken_pitches=len(taken),
    )


def build_catcher_data(
    source: pd.DataFrame, catcher_id: str | int, filters: PitchFilters,
) -> CatcherData | None:
    """Framing table for one catcher over the filtered pitches; None when none pass the filters."""
    filtered = filters.apply(source)
    if catching_report.catcher_rows(filtered, catcher_id).empty:
        return None
    return CatcherData(
        name=catching_report.catcher_name(source, catcher_id),
        framing_table=catching_report.build_catcher_framing_table(filtered, catcher_id),
    )


def charts_payload(charts: CatcherCharts) -> dict[str, Any]:
    return {'figures': charts.figures, 'legend': charts.legend, 'taken_pitches': charts.taken_pitches}


def tables_payload(data: CatcherData) -> dict[str, Any]:
    return {
        'catcher_name': data.name,
        'framing_table': data.framing_table.to_html('pitcher-data-table') if data.framing_table else None,
    }
