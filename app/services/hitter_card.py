"""
One hitter's report, computed for the current filters.

Shared by the web preview (JSON card) and the PDF export, so both are built from the same
filtered pitches. Pure Python/pandas, no Flask and no db.session -- the caller resolves
anything request-bound and passes it in. See app/services/CLAUDE.md.
"""
from dataclasses import dataclass
from typing import Any

import pandas as pd

from app.services import hitter_report, plotly_charts
from app.services.chart_prefs import ChartPrefs
from app.services.hitter_stats import BattedBallTable, CustomHitTypeStatsTable, HitterDisciplineTable
from app.services.pitch_filters import PitchFilters
from app.services.pitch_stats import CustomPitchTypeStatsTable, CustomStatsTable


@dataclass
class HitterCharts:
    figures: dict[str, dict[str, Any]]
    legend: list[dict[str, Any]]
    batted_balls: int


@dataclass
class HitterData:
    name: str
    games: int
    summary: dict[str, str]
    discipline: HitterDisciplineTable
    batted_ball: BattedBallTable
    custom_stats: CustomStatsTable | None
    custom_hit_type_stats: list[CustomHitTypeStatsTable] | None
    custom_pitch_type_stats: list[CustomPitchTypeStatsTable] | None
    # The filtered frame the stats above were computed from, for callers that go on to ask
    # a school script for more (custom charts) over exactly the same pitches.
    source: pd.DataFrame


def _batted(rows: pd.DataFrame) -> pd.DataFrame:
    if 'PitchCall' not in rows.columns:
        return rows.iloc[0:0]
    return rows[rows['PitchCall'].fillna('').astype(str) == 'InPlay']


def build_hitter_charts(
    source: pd.DataFrame, batter_id: str | int, filters: PitchFilters, prefs: ChartPrefs,
) -> HitterCharts:
    """
    The two spray charts (vs LHP / RHP), the pitch-type key and the batted-ball count.

    `source` is the *unfiltered* frame: the exit-velocity color scale is pinned to this
    hitter's own quartiles before filtering, so it doesn't shift as the sliders move.
    """
    full = hitter_report.batter_rows(source, batter_id)
    ev_lim = plotly_charts.exit_velo_limits(_batted(full))
    rows = filters.apply(full)

    return HitterCharts(
        figures={
            'spray_left': plotly_charts.spray_figure(rows, 'Left', prefs.color_by, prefs.view, ev_lim),
            'spray_right': plotly_charts.spray_figure(rows, 'Right', prefs.color_by, prefs.view, ev_lim),
        },
        legend=plotly_charts.pitch_type_legend(_batted(rows)),
        batted_balls=len(_batted(rows)),
    )


def build_hitter_data(
    source: pd.DataFrame, batter_id: str | int, filters: PitchFilters, *, school_id: int, is_active: bool,
    filtered: pd.DataFrame | None = None,
) -> HitterData | None:
    """
    Stat tables and custom stats for one hitter over the filtered pitches.

    Returns None when no pitch he saw passes the filters (the page shows an empty card).
    `filtered` is filters.apply(source) when the caller is building several hitters from the
    same source and has already done it once.
    """
    if filtered is None:
        filtered = filters.apply(source)
    rows = hitter_report.batter_rows(filtered, batter_id)
    if rows.empty:
        return None

    custom_stats = custom_hit_type_stats = custom_pitch_type_stats = None
    # Gated only on whether the school has a master-uploaded custom report script, not on
    # the chart tier -- see hitter_report.custom_stats_table.
    if is_active:
        custom_stats = hitter_report.custom_stats_table(filtered, batter_id, school_id)
        custom_hit_type_stats = hitter_report.custom_hit_type_stats_table(filtered, batter_id, school_id)
        custom_pitch_type_stats = hitter_report.custom_pitch_type_stats_table(filtered, batter_id, school_id)

    return HitterData(
        name=hitter_report.batter_name(source, batter_id),
        games=int(rows['GameDate'].nunique()) if 'GameDate' in rows.columns else 0,
        summary=hitter_report.build_hitter_summary(filtered, batter_id),
        discipline=hitter_report.build_hitter_discipline_table(filtered, batter_id),
        batted_ball=hitter_report.build_batted_ball_table(filtered, batter_id),
        custom_stats=custom_stats,
        custom_hit_type_stats=custom_hit_type_stats,
        custom_pitch_type_stats=custom_pitch_type_stats,
        source=filtered,
    )


def charts_payload(charts: HitterCharts) -> dict[str, Any]:
    return {'figures': charts.figures, 'legend': charts.legend, 'batted_balls': charts.batted_balls}


def tables_payload(data: HitterData) -> dict[str, Any]:
    return {
        'hitter_name': data.name,
        'games': data.games,
        'summary': data.summary,
        'discipline_table': data.discipline.to_html('pitcher-data-table'),
        'batted_ball_table': data.batted_ball.to_html('pitcher-data-table'),
        # Rendered as tiles on the page (see .summary-grid), matching the PDF's
        # generate_stats_grid -- name/value pairs, not tabular data.
        'custom_stats': {row.name: row.value for row in data.custom_stats.rows} if data.custom_stats else None,
        'custom_hit_type_stats_tables': [
            {'title': t.title or 'Custom Hit Type Stats', 'html': t.to_html('custom-stats-table')}
            for t in data.custom_hit_type_stats
        ] if data.custom_hit_type_stats else None,
        'custom_pitch_type_stats_tables': [
            {'title': t.title or 'Custom Pitch Type Stats', 'html': t.to_html('custom-stats-table')}
            for t in data.custom_pitch_type_stats
        ] if data.custom_pitch_type_stats else None,
    }
