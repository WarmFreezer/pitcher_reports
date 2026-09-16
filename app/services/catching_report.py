import os
from typing import Any

import matplotlib
import pandas as pd

from app.services.catcher_stats import CatcherFramingRow, CatcherFramingTable
from app.services.report_theme import (
    THEME_COLORS,
    make_strike_zone,
    make_shadow_zone,
    make_homeplate,
    strike_probability,
)

from matplotlib import pyplot as plt

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


def _catcher_rows(source: pd.DataFrame, catcher_id: str | int) -> pd.DataFrame:
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


def _taken_pitches(source: pd.DataFrame, catcher_id: str | int) -> pd.DataFrame:
    """This catcher's taken (not swung at) pitches, with a framing_value column added."""
    table = _catcher_rows(source, catcher_id)
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
    rows = _catcher_rows(source, catcher_id)
    if rows.empty or 'Catcher' not in rows.columns:
        return str(catcher_id)
    names = rows['Catcher'].dropna()
    return str(names.iloc[0]) if not names.empty else str(catcher_id)


def build_catcher_framing_table(source: pd.DataFrame, catcher_id: str | int) -> CatcherFramingTable | None:
    """Per-game framing (SLAA) summary for one catcher, aggregated across every session in source."""
    taken = _taken_pitches(source, catcher_id)
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


def _zone_axes(ax: Any) -> None:
    ax.set_xlabel('Plate Location Side (ft)', fontsize=18, labelpad=8)
    ax.set_ylabel('Plate Location Height (ft)', fontsize=18, labelpad=8)
    ax.set_xlim(-2.5, 2.5)
    ax.set_ylim(0, 5)
    ax.set_aspect('equal', adjustable='box')
    ax.add_patch(make_strike_zone())
    ax.add_patch(make_shadow_zone())
    ax.add_patch(make_homeplate())


# Below this magnitude a taken pitch is a near-toss-up call barely stolen/lost
# (e.g. 52% strike probability called a ball) -- real, but not a notable framing
# event, and plotting every one of them buried the notable ones in noise.
MIN_NOTABLE_FRAMING_VALUE = 0.1


def _sort_by_strength(df: pd.DataFrame) -> pd.DataFrame:
    """Weaker-magnitude pitches first, stronger ones last -- drawing a scatter
    in this order renders the most notable points on top of overlapping weaker
    ones instead of letting draw order bury them arbitrarily."""
    return df.reindex(df['framing_value'].abs().sort_values().index)


def catcher_framing_heat_map(
    source: pd.DataFrame, id: int, output_path: str, catcher_id: str | int, theme: str = 'light',
) -> None:
    """
    Save a scatter of this catcher's notable (non-toss-up) framing events to
    output_path. A companion to catcher_pitch_location_chart's full point cloud --
    that one shows everything, this one drops the near-toss-up pitches so what's
    left is only the pitches that actually moved the needle.
    """
    matplotlib.rcParams.update(THEME_COLORS.get(theme, THEME_COLORS['light']))
    taken = _taken_pitches(source, catcher_id)
    notable = taken[taken['framing_value'].abs() >= MIN_NOTABLE_FRAMING_VALUE] if not taken.empty else taken

    fig, ax = plt.subplots(1, 1, figsize=(9, 8))
    _zone_axes(ax)

    if notable.empty:
        ax.text(0, 2.5, 'No notable framing events for this catcher', ha='center', va='center', fontsize=14)
    else:
        notable = _sort_by_strength(notable)
        scatter = ax.scatter(
            notable['PlateLocSide'], notable['PlateLocHeight'], c=notable['framing_value'],
            cmap='RdBu', vmin=-0.5, vmax=0.5, s=110, edgecolors='black', linewidth=0.6, zorder=5)
        fig.colorbar(scatter, ax=ax, label='Framing value (lost ← → stolen)')

    fig.savefig(
        os.path.join(output_path, f'{id}_catcher_{catcher_id}_heat_map_{theme}.png'),
        pad_inches=0.3, dpi=300, bbox_inches='tight', transparent=True)
    plt.close(fig)


def catcher_pitch_location_chart(
    source: pd.DataFrame, id: int, output_path: str, catcher_id: str | int, theme: str = 'light',
) -> None:
    """
    Save a scatter of every taken pitch, colored by its own framing value, to
    output_path. Stronger-magnitude pitches are drawn last so they render on
    top of weaker, overlapping ones rather than getting buried by draw order.
    """
    matplotlib.rcParams.update(THEME_COLORS.get(theme, THEME_COLORS['light']))
    taken = _taken_pitches(source, catcher_id)

    fig, ax = plt.subplots(1, 1, figsize=(9, 8))
    _zone_axes(ax)

    if taken.empty:
        ax.text(0, 2.5, 'No taken-pitch data for this catcher', ha='center', va='center', fontsize=14)
    else:
        taken = _sort_by_strength(taken)
        scatter = ax.scatter(
            taken['PlateLocSide'], taken['PlateLocHeight'], c=taken['framing_value'],
            cmap='RdBu', vmin=-0.5, vmax=0.5, s=90, edgecolors='black', linewidth=0.6, zorder=5)
        fig.colorbar(scatter, ax=ax, label='Framing value (lost ← → stolen)')

    fig.savefig(
        os.path.join(output_path, f'{id}_catcher_{catcher_id}_pitch_location_{theme}.png'),
        pad_inches=0.3, dpi=300, bbox_inches='tight', transparent=True)
    plt.close(fig)
