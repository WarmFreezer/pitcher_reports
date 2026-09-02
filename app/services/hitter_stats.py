"""
Typed value objects for hitter stat reports, replacing the DataFrames
hitter_report.py used to build and report_lab_generator.py used to render.
"""
from dataclasses import dataclass, field

import pandas as pd

from app.services.pitch_stats import CustomStatsTable, CustomPitchTypeStatsTable
from app.services.stat_table import Column, ColumnFormat, StatTable


@dataclass(frozen=True)
class HitterDisciplineStat:
    """One pitch type's plate-discipline stats for a hitter's selected outing(s)."""
    pitch_type: str
    seen: int
    usage_pct: float
    zone_pct: float
    swing_pct: float
    whiff_pct: float
    chase_pct: float
    contact_pct: float


class HitterDisciplineTable(StatTable[HitterDisciplineStat]):
    """The plate-discipline-by-pitch-type table shown on a hitter report."""
    columns = [
        Column('pitch_type', 'Pitch', ColumnFormat.TEXT),
        Column('seen', 'Seen', ColumnFormat.INT),
        Column('usage_pct', 'Usage', ColumnFormat.PERCENT),
        Column('zone_pct', 'Zone', ColumnFormat.PERCENT),
        Column('swing_pct', 'Swing', ColumnFormat.PERCENT),
        Column('whiff_pct', 'Whiff', ColumnFormat.PERCENT),
        Column('chase_pct', 'Chase', ColumnFormat.PERCENT),
        Column('contact_pct', 'Contact', ColumnFormat.PERCENT),
    ]


@dataclass(frozen=True)
class BattedBallStat:
    """One launch-angle bucket's batted-ball profile for a hitter's selected outing(s)."""
    hit_type: str
    count: int
    rate_pct: float
    avg_ev: float | None            # None when no ball in the bucket tracked an exit speed
    max_ev: float | None
    avg_launch_angle: float | None
    avg_distance: float | None


class BattedBallTable(StatTable[BattedBallStat]):
    """The batted-ball-mix table shown on a hitter report."""
    columns = [
        Column('hit_type', 'Type', ColumnFormat.TEXT),
        Column('count', 'Count', ColumnFormat.INT),
        Column('rate_pct', 'Rate', ColumnFormat.PERCENT),
        Column('avg_ev', 'Avg EV', ColumnFormat.DECIMAL1, none_display='-'),
        Column('max_ev', 'Max EV', ColumnFormat.DECIMAL1, none_display='-'),
        Column('avg_launch_angle', 'Avg LA', ColumnFormat.DECIMAL1, none_display='-'),
        Column('avg_distance', 'Avg Dist', ColumnFormat.DECIMAL0, none_display='-'),
    ]


@dataclass(frozen=True)
class CustomHitTypeStat:
    """One batted-ball bucket's row in a runtime-defined custom stats table."""
    hit_type: str
    stats: dict[str, str]  # stat name -> pre-formatted value; keys are whatever the custom module tracks


class CustomHitTypeStatsTable(StatTable[CustomHitTypeStat]):
    """
    Hit-type-broken-out custom stats table for the tier 3 custom hitter report.

    Same dynamic-column design as pitch_stats.CustomPitchTypeStatsTable -- headers
    are derived from the union of each row's `stats` keys instead of a static
    `columns` list, since a school's custom_hitter_report.py can add whatever
    stat names it wants per hit type.
    """
    def __init__(self, rows: list[CustomHitTypeStat], title: str = '', col_widths: list[float] | None = None) -> None:
        super().__init__(rows, col_widths)
        self.title = title
        seen: dict[str, None] = {}
        for row in rows:
            seen.update(dict.fromkeys(row.stats))
        self.stat_names = list(seen)

    def to_reportlab_rows(self) -> list[list[str]]:
        header = ['Type'] + self.stat_names
        body = [[row.hit_type] + [row.stats.get(name, '') for name in self.stat_names] for row in self.rows]
        return [header] + body

    def to_dict(self) -> list[dict[str, str]]:
        return [{'Type': row.hit_type, **{name: row.stats.get(name, '') for name in self.stat_names}} for row in self.rows]

    def to_html(self, css_class: str = '') -> str:
        if not self.rows:
            return ''
        df = pd.DataFrame(self.to_dict())
        return df.to_html(index=False, border=0, classes=css_class, escape=False, justify='left', na_rep='')


@dataclass
class HitterReportRequest:
    """
    Everything PDF_Generator.generate_hitter_report() needs to build one
    hitter's report. Replaces the ad hoc dict app/routes/batting.py used to
    build, mirroring PitcherReportRequest in pitch_stats.py.
    """
    hitter_name: str = 'Hitter'
    hitter_id: str = ''
    date_range: str = ''
    team: str = ''
    games: int = 0
    summary: dict[str, str] = field(default_factory=dict)
    discipline_table: HitterDisciplineTable | None = None
    batted_ball_table: BattedBallTable | None = None
    spray_chart_left: str | None = None
    spray_chart_right: str | None = None
    custom_stats: CustomStatsTable | None = None
    custom_hit_type_stats: list[CustomHitTypeStatsTable] | None = None
    custom_pitch_type_stats: list[CustomPitchTypeStatsTable] | None = None
    custom_chart_paths: list[tuple[str, str]] | None = None  # (title, image path)
