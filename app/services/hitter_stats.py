"""
Typed value objects for hitter stat reports, replacing the DataFrames
hitter_report.py used to build and report_lab_generator.py used to render.
"""
from dataclasses import dataclass

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
