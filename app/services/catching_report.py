import pandas as pd

from app.services.catcher_stats import CatcherFramingRow, CatcherFramingTable
from app.services.report_theme import strike_probability

TAKEN_CALLS = ['BallCalled', 'StrikeCalled']


def framing_value(prob: float, called_strike: bool) -> float:
    """
    Signed SLAA value for one taken pitch: positive for a stolen strike (the
    model expected a ball, umpire called it a strike), negative for a lost
    strike (the model expected a strike, umpire called it a ball), zero when
    the call matched the model's own expectation.
    """
    if called_strike and prob < 0.5:
        return 0.5 - prob
    if not called_strike and prob > 0.5:
        return -(prob - 0.5)
    return 0.0


def catcher_rows(source: pd.DataFrame, catcher_id: str | int) -> pd.DataFrame:
    """This catcher's rows. Ids are compared numerically to dodge int/float/str
    drift -- see hitter_report.batter_rows, which solves the same problem."""
    if source.empty or 'CatcherId' not in source.columns:
        return source.iloc[0:0]

    ids = pd.to_numeric(source['CatcherId'], errors='coerce')
    try:
        target = float(catcher_id)
    except (TypeError, ValueError):
        return source.iloc[0:0]

    return source[ids == target]


def taken_pitches(source: pd.DataFrame, catcher_id: str | int) -> pd.DataFrame:
    """This catcher's taken (not swung at) pitches, with a framing_value column added."""
    table = catcher_rows(source, catcher_id)
    table = table[table['PitchCall'].isin(TAKEN_CALLS)]
    table = table.dropna(subset=['PlateLocSide', 'PlateLocHeight'])
    # Same plausible-location bounds _zone_axes() plots against -- a "strike"
    # tracked a foot outside the zone or six feet in the air is bad tracking
    # data, not a stolen call, but strike_probability() has no way to tell the
    # difference from a genuinely well-framed borderline pitch: both are just
    # "far outside," and a bad point that far out swamps the framing total
    # with the single largest possible value (~0.5) it can produce.
    table = table[table['PlateLocSide'].between(-2.5, 2.5) & table['PlateLocHeight'].between(0, 5)]
    if table.empty:
        return table

    probs = [strike_probability(side, height) for side, height in
              zip(table['PlateLocSide'], table['PlateLocHeight'])]
    called_strike = table['PitchCall'] == 'StrikeCalled'
    values = [framing_value(p, cs) for p, cs in zip(probs, called_strike)]

    table = table.copy()
    table['strike_prob'] = probs
    table['framing_value'] = values
    return table


def catcher_name(source: pd.DataFrame, catcher_id: str | int) -> str:
    """Display name for a catcher id, falling back to the id itself if unresolved."""
    rows = catcher_rows(source, catcher_id)
    if rows.empty or 'Catcher' not in rows.columns:
        return str(catcher_id)
    names = rows['Catcher'].dropna()
    return str(names.iloc[0]) if not names.empty else str(catcher_id)


def build_catcher_framing_table(source: pd.DataFrame, catcher_id: str | int) -> CatcherFramingTable | None:
    """Per-game framing (SLAA) summary for one catcher, aggregated across every session in source."""
    taken = taken_pitches(source, catcher_id)
    if taken.empty:
        return None

    rows: list[CatcherFramingRow] = []
    group_cols = [c for c in ('Date', 'PitcherTeam', 'BatterTeam') if c in taken.columns]
    if not group_cols:
        return None

    for keys, game in taken.groupby(group_cols, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        by_col = dict(zip(group_cols, keys))
        values = game['framing_value']
        stolen = int((values > 0).sum())
        lost = int((values < 0).sum())
        taken_count = len(values)
        rows.append(CatcherFramingRow(
            session=str(by_col.get('Date', '')),
            home_team=str(by_col.get('PitcherTeam', '')),
            away_team=str(by_col.get('BatterTeam', '')),
            framing_total=round(float(values.sum()), 2),
            framing_rate=round((stolen - lost) / taken_count * 100, 1) if taken_count else 0.0,
            correct=int((values == 0).sum()),
            stolen=stolen,
            lost=lost,
        ))

    rows.sort(key=lambda r: r.session)
    return CatcherFramingTable(rows) if rows else None


# Below this magnitude a taken pitch is a near-toss-up call barely stolen/lost
# (e.g. 52% strike probability called a ball) -- real, but not a notable framing
# event, and plotting every one of them buried the notable ones in noise.
MIN_NOTABLE_FRAMING_VALUE = 0.1
