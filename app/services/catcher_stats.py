"""
Typed value objects for catching reports, following the same StatTable pattern
as pitch_stats.py/hitter_stats.py -- see app/services/CLAUDE.md.
"""
from dataclasses import dataclass

from app.services.stat_table import Column, ColumnFormat, StatTable


@dataclass(frozen=True)
class CatcherFramingRow:
    """One game's framing summary for a catcher."""
    session: str    # game date
    home_team: str
    away_team: str
    framing_total: float  # SLAA (Strikes Looking Above Average) -- sum of every taken pitch's signed framing value this game
    framing_rate: float    # SL+ -- (stolen - lost) per 100 taken pitches: +1 per stolen pitch, -1 per lost pitch, rate-scaled
    correct: int             # taken pitches called the way the model expected
    stolen: int          # taken pitches called a strike the model expected a ball
    lost: int              # taken pitches called a ball the model expected a strike


class CatcherFramingTable(StatTable[CatcherFramingRow]):
    """Per-game framing summary table shown on a catcher report."""
    columns = [
        Column('session', 'Session', ColumnFormat.TEXT),
        Column('home_team', 'Home Team', ColumnFormat.TEXT),
        Column('away_team', 'Away Team', ColumnFormat.TEXT),
        Column('framing_total', 'Framing Value', ColumnFormat.DECIMAL2),
        Column('framing_rate', 'Framing Rate', ColumnFormat.DECIMAL1),
        Column('correct', 'Correct', ColumnFormat.INT),
        Column('stolen', 'Stolen', ColumnFormat.INT),
        Column('lost', 'Lost', ColumnFormat.INT),
    ]


@dataclass
class CatcherReportRequest:
    """Everything PDF_Generator.generate_catcher_report() needs to build one catcher's report."""
    catcher_name: str = 'Catcher'
    catcher_id: str = ''
    date_range: str = ''
    team: str = ''
    games: int = 0
    framing_table: CatcherFramingTable | None = None
    heat_map: str | None = None
    pitch_location_chart: str | None = None
