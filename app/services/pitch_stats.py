"""
Typed value objects for pitcher stat reports, replacing the DataFrame report.py
used to build and report_lab_generator.py used to render.

report.build_table()/usage_table() still do the same pandas aggregation over
the raw TrackMan rows -- only what they assemble at the end changed, from a
dict -> pd.DataFrame -> post-hoc string-formatting to these dataclasses.
"""
from dataclasses import dataclass

import pandas as pd

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
    # % of this pitch type's balls in play hit 90+ mph exit velo with a 10-35 deg
    # launch angle (TODO's "Damage by type" definition -- not the per-school custom
    # report scripts' own "damage" stats, which use a different metric/threshold).
    damage_pct: float


class PitcherStatsTable(StatTable[PitchTypeStat]):
    """The 18-column per-pitch-type stats table shown on a pitcher report."""
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
        Column('damage_pct', 'Damage', ColumnFormat.PERCENT),
    ]


@dataclass(frozen=True)
class PitcherGameReport:
    """Replaces build_table()'s positional [date, home_team, away_team, pitcher_name, DataFrame] return."""
    header: GameReportHeader
    stats: PitcherStatsTable


@dataclass(frozen=True)
class PitchByPitchPitch:
    """One pitch within an at-bat, for the numbered pitch-by-pitch report."""
    number: int
    pitch_type: str
    velo: float | None
    balls: int
    strikes: int
    result: str  # this pitch's own PitchCall (e.g. "StrikeSwinging", "BallCalled", "InPlay")


@dataclass(frozen=True)
class PitchByPitchAtBat:
    """One plate appearance faced, with every pitch thrown during it."""
    inning: str  # e.g. "Top 3"
    batter_name: str
    batter_side: str
    result: str  # final PA outcome (PlayResult, or KorBB for a walk/strikeout)
    pitches: list[PitchByPitchPitch]


@dataclass(frozen=True)
class PitchByPitchReport:
    """
    Simplified pitch-by-pitch report data: a header plus every at-bat this
    pitcher faced. Replaces the old raw-CSV-plus-chart-ZIP export.
    """
    pitcher_name: str
    date: str
    matchup: str
    at_bats: list[PitchByPitchAtBat]


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


@dataclass(frozen=True)
class CustomStat:
    """One school-defined stat computed in report.py's custom_stats_table()."""
    name: str
    value: str  # pre-formatted by report.py -- a table column has one static format for every row


class CustomStatsTable(StatTable[CustomStat]):
    """The custom statistics table shown on the tier 3 custom pitcher report."""
    columns = [
        Column('name', 'Stat Name', ColumnFormat.TEXT),
        Column('value', 'Value', ColumnFormat.TEXT),
    ]

@dataclass(frozen=True)
class CustomPitchTypeStat:
    """One pitch type's row in a runtime-defined custom stats table."""
    pitch_type: str
    stats: dict[str, str]  # stat name -> pre-formatted value; keys are whatever the custom module tracks


class CustomPitchTypeStatsTable(StatTable[CustomPitchTypeStat]):
    """
    Pitch-type-broken-out custom stats table for the tier 3 custom pitcher report.

    Unlike PitcherStatsTable/PitchUsageTable, the stat columns aren't fixed at
    class-definition time -- custom_pitcher_report.py adds whatever stat/value
    pairs it wants per pitch type, so headers are derived from the union of
    each row's `stats` keys instead of a static `columns` list.

    A report may need more than one of these (e.g. a left/right split, like
    pitch_usage_left/right) -- `title` labels a table so PitcherReportRequest
    can carry them as a plain list without a parallel list of titles.
    """
    def __init__(self, rows: list[CustomPitchTypeStat], title: str = '', col_widths: list[float] | None = None) -> None:
        super().__init__(rows, col_widths)
        self.title = title
        seen: dict[str, None] = {}
        for row in rows:
            seen.update(dict.fromkeys(row.stats))
        self.stat_names = list(seen)

    def to_reportlab_rows(self) -> list[list[str]]:
        header = ['Pitch'] + self.stat_names
        body = [[row.pitch_type] + [row.stats.get(name, '') for name in self.stat_names] for row in self.rows]
        return [header] + body

    def to_dict(self) -> list[dict[str, str]]:
        return [{'Pitch': row.pitch_type, **{name: row.stats.get(name, '') for name in self.stat_names}} for row in self.rows]

    def to_html(self, css_class: str = '') -> str:
        if not self.rows:
            return ''
        df = pd.DataFrame(self.to_dict())
        return df.to_html(index=False, border=0, classes=css_class, escape=False, justify='left', na_rep='')


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
    # 'vs' reads correctly for an aggregated range (home_team/away_team aren't a
    # real single-game home/away pair here -- see routes/pitching.py). Callers
    # set '@' only for a genuine single selected game.
    matchup_separator: str = 'vs'
    pitcher_height: str = ''
    pitcher_weight: str = ''
    pitcher_age: int | None = None
    pitch_stats: PitcherStatsTable | None = None
    pitch_usage_left: PitchUsageTable | None = None
    pitch_usage_right: PitchUsageTable | None = None
    pitch_heat_map_left: str | None = None
    pitch_heat_map_right: str | None = None
    pitch_break_map: str | None = None
    custom_stats: CustomStatsTable | None = None
    custom_pitch_type_stats: list[CustomPitchTypeStatsTable] | None = None