"""
Typed value objects for pitcher stat reports, replacing the DataFrame report.py
used to build and report_lab_generator.py used to render.

report.build_table()/usage_table() still do the same pandas aggregation over
the raw TrackMan rows -- only what they assemble at the end changed, from a
dict -> pd.DataFrame -> post-hoc string-formatting to these dataclasses.
"""
from dataclasses import dataclass

from app.services.stat_table import Column, ColumnFormat, StatTable


@dataclass(frozen=True)
class GameReportHeader:
    """Game context shown above a pitcher's stats table."""
    date: str
    home_team: str
    away_team: str
    pitcher_name: str


@dataclass(frozen=True)
class PitchTypeStat:
    """One pitch type's aggregated stats for a pitcher's selected outing(s)."""
    pitch_type: str          # display abbreviation, e.g. "FB" (already resolved via report_theme.pitch_order)
    thrown_pct: float
    velo_low: float
    velo_avg: float
    velo_high: float
    ivb: float
    hb: float
    spin: float
    vaa: float
    haa: float
    rel_height: float
    rel_side: float
    extension: float
    axis: str                # "12:30" or "N/A" -- already text, formatted at aggregation time
    zone_pct: float
    chase_pct: float
    csw_pct: float


class PitcherStatsTable(StatTable[PitchTypeStat]):
    """The 17-column per-pitch-type stats table shown on a pitcher report."""
    columns = [
        Column('pitch_type', 'Pitch', ColumnFormat.TEXT),
        Column('thrown_pct', 'Thrown', ColumnFormat.PERCENT),
        Column('velo_low', 'Low', ColumnFormat.DECIMAL2),
        Column('velo_avg', 'Vel.', ColumnFormat.DECIMAL2),
        Column('velo_high', 'High', ColumnFormat.DECIMAL2),
        Column('ivb', 'IVB', ColumnFormat.DECIMAL2),
        Column('hb', 'HB', ColumnFormat.DECIMAL2),
        Column('spin', 'Spin', ColumnFormat.DECIMAL2),
        Column('vaa', 'VAA', ColumnFormat.DECIMAL2),
        Column('haa', 'HAA', ColumnFormat.DECIMAL2),
        Column('rel_height', 'RelH', ColumnFormat.DECIMAL2),
        Column('rel_side', 'RelS', ColumnFormat.DECIMAL2),
        Column('extension', 'Ext.', ColumnFormat.DECIMAL2),
        Column('axis', 'Axis', ColumnFormat.TEXT),
        Column('zone_pct', 'Zone', ColumnFormat.PERCENT),
        Column('chase_pct', 'Chase', ColumnFormat.PERCENT),
        Column('csw_pct', 'CSW', ColumnFormat.PERCENT),
    ]


@dataclass(frozen=True)
class PitcherGameReport:
    """Replaces build_table()'s positional [date, home_team, away_team, pitcher_name, DataFrame] return."""
    header: GameReportHeader
    stats: PitcherStatsTable


@dataclass(frozen=True)
class PitchUsageStat:
    """One pitch type's usage-by-count-situation stats, for one batter side."""
    pitch_type: str
    count: int
    strike_pct: float
    first_pitch_pct: float       # usage on the first pitch of a plate appearance (0-0 counts)
    hitter_favorable_pct: float  # usage when balls > strikes
    pitcher_favorable_pct: float  # usage when strikes > balls
    two_strike_pct: float
    whiff_pct: float


class PitchUsageTable(StatTable[PitchUsageStat]):
    """The pitch-usage-by-count table shown for one batter side on a pitcher report."""
    columns = [
        Column('pitch_type', 'Pitch', ColumnFormat.TEXT),
        Column('count', 'Count', ColumnFormat.INT),
        Column('strike_pct', 'Strike', ColumnFormat.PERCENT),
        Column('first_pitch_pct', '0-0', ColumnFormat.PERCENT),
        Column('hitter_favorable_pct', "Hitter's", ColumnFormat.PERCENT),
        Column('pitcher_favorable_pct', "Pitcher's", ColumnFormat.PERCENT),
        Column('two_strike_pct', '2k', ColumnFormat.PERCENT),
        Column('whiff_pct', 'Whiff', ColumnFormat.PERCENT),
    ]


@dataclass(frozen=True)
class PitchUsageSides:
    """Replaces usage_table()'s positional [left_df, right_df] return."""
    left: PitchUsageTable
    right: PitchUsageTable


@dataclass
class PitcherReportRequest:
    """
    Everything PDF_Generator.generate_pitcher_report() needs to build one
    pitcher's report. Replaces the ad hoc dict built in app/routes/pitching.py
    that mixed primitive strings/ints, DataFrames, and image-path strings --
    every DataFrame value had to be defensively isinstance()-checked before
    use, since a plain dict gives no guarantee of what's actually inside.
    """
    pitcher_name: str = 'Pitcher'
    pitcher_id: str = ''
    date: str = ''
    home_team: str = ''
    away_team: str = ''
    pitcher_height: str = ''
    pitcher_weight: str = ''
    pitcher_age: int | None = None
    pitch_stats: PitcherStatsTable | None = None
    pitch_usage_left: PitchUsageTable | None = None
    pitch_usage_right: PitchUsageTable | None = None
    pitch_heat_map_left: str | None = None
    pitch_heat_map_right: str | None = None
    pitch_break_map: str | None = None
