"""
One pitcher's report, computed for the current filters.

Shared by the web preview (JSON card) and the PDF export, so both are built from the same
filtered pitches. Pure Python/pandas, no Flask and no db.session -- the caller resolves
anything request-bound (school flags, roster metadata) and passes it in. See
app/services/CLAUDE.md.
"""
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services import plotly_charts, report
from app.services.chart_prefs import ChartPrefs
from app.services.pitch_filters import PitchFilters
from app.services.pitch_stats import (
    BreakMapLegendEntry,
    CustomPitchTypeStatsTable,
    CustomStatsTable,
    PitcherGameReport,
    PitchUsageSides,
)


@dataclass
class PitcherCharts:
    figures: dict[str, dict[str, Any]]
    legend: list[BreakMapLegendEntry]
    arm_angle: float | None
    pitch_count: int


@dataclass
class PitcherData:
    pitcher_name: str
    game_report: PitcherGameReport
    usage_sides: PitchUsageSides
    custom_stats: CustomStatsTable | None
    custom_pitch_type_stats: list[CustomPitchTypeStatsTable] | None
    legend: list[BreakMapLegendEntry]


def pitcher_name_in(source: pd.DataFrame, pitcher_id: int) -> str | None:
    rows = source.loc[source['PitcherId'] == pitcher_id, 'Pitcher']
    return str(rows.iloc[0]) if not rows.empty else None


def build_pitcher_charts(
    source: pd.DataFrame, pitcher_id: int, filters: PitchFilters, prefs: ChartPrefs,
) -> PitcherCharts:
    """
    The three charts (location vs LHH/RHH, movement), their legend and the arm angle.

    `source` is the *unfiltered* frame: the velocity color scale is pinned to this
    pitcher's own quartiles before filtering, so it doesn't shift as the sliders move.
    """
    full = source[source['PitcherId'] == pitcher_id]
    velo_lim = plotly_charts.velo_limits(full)
    rows = filters.apply(full)

    break_fig, arm_angle = plotly_charts.break_figure(
        rows, prefs.color_by, prefs.view, velo_lim, prefs.show_arrows)
    return PitcherCharts(
        figures={
            'heat_left': plotly_charts.location_figure(rows, 'Left', prefs.color_by, prefs.view, velo_lim),
            'heat_right': plotly_charts.location_figure(rows, 'Right', prefs.color_by, prefs.view, velo_lim),
            'break': break_fig,
        },
        legend=report.pitch_break_map_legend(rows, pitcher_id),
        arm_angle=arm_angle,
        pitch_count=len(rows),
    )


def build_pitcher_data(
    source: pd.DataFrame, pitcher_id: int, filters: PitchFilters, *, school_id: int, is_active: bool,
) -> PitcherData | None:
    """
    Stat tables and custom stats for one pitcher over the filtered pitches.

    Returns None when no pitch passes the filters (the page shows an empty card).
    Raises ValueError if the tables can't be built from rows that do exist.
    """
    filtered = filters.apply(source)
    if not (filtered['PitcherId'] == pitcher_id).any():
        return None

    custom_stats = custom_pitch_type_stats = None
    # Gated only on whether the school has a master-uploaded custom report script,
    # not on the chart tier -- see report.custom_stats_table.
    if is_active:
        custom_stats = report.custom_stats_table(filtered, pitcher_id, school_id)
        custom_pitch_type_stats = report.custom_pitch_type_stats_table(filtered, pitcher_id, school_id)

    game_report = report.build_table(filtered, pitcher_id)
    if game_report is None:
        raise ValueError(f'Failed to build table data for pitcher ID {pitcher_id}')

    usage_sides = report.usage_table(filtered, pitcher_id)
    if usage_sides is None:
        raise ValueError(f'Failed to build pitch usage table for pitcher ID {pitcher_id}')

    return PitcherData(
        pitcher_name=game_report.header.pitcher_name,
        game_report=game_report,
        usage_sides=usage_sides,
        custom_stats=custom_stats,
        custom_pitch_type_stats=custom_pitch_type_stats,
        legend=report.pitch_break_map_legend(filtered, pitcher_id),
    )


def charts_payload(charts: PitcherCharts) -> dict[str, Any]:
    return {
        'figures': charts.figures,
        'legend': [{'abbreviation': e.abbreviation, 'color': e.color, 'count': e.count}
                   for e in charts.legend],
        'arm_angle': f'{charts.arm_angle:.1f}°' if charts.arm_angle is not None else '',
        'pitch_count': charts.pitch_count,
    }


def tables_payload(data: PitcherData) -> dict[str, Any]:
    custom_stats = data.custom_stats
    custom_tables = data.custom_pitch_type_stats
    return {
        'pitcher_table': data.game_report.stats.to_html('pitcher-data-table'),
        'left_usage_table': data.usage_sides.left.to_html('pitch-usage-table'),
        'right_usage_table': data.usage_sides.right.to_html('pitch-usage-table'),
        # Rendered as tiles on the page (see .summary-grid), matching the PDF's
        # generate_stats_grid -- name/value pairs, not tabular data.
        'custom_stats': {row.name: row.value for row in custom_stats.rows} if custom_stats else None,
        'custom_pitch_type_stats_tables': [
            {'title': t.title or 'Custom Pitch Type Stats', 'html': t.to_html('custom-stats-table')}
            for t in custom_tables
        ] if custom_tables else None,
    }
