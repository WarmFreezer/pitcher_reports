'''
Hitting analysis built from raw TrackMan rows.

Unlike the pitcher module this is fed by app.services.game_archive.load_range, so the
incoming frame usually spans several games. Nothing here assumes a single game; the
only per-row requirement is the TrackMan schema below.
'''

import json
from typing import Protocol, TypeVar, overload

import numpy as np
import pandas as pd

from app.services.custom_report_loader import load_custom_module
from app.services.hitter_stats import (
    BattedBallStat,
    BattedBallTable,
    CustomChart,
    CustomHitTypeStat,
    CustomHitTypeStatsTable,
    HitterDisciplineStat,
    HitterDisciplineTable,
    HitterPitchByPitchAtBat,
    HitterPitchByPitchReport,
)
from app.services.pitch_stats import CustomStat, CustomStatsTable, CustomPitchTypeStatsTable, PitchByPitchPitch
from app.services.report_theme import (
    format_result,
    in_zone,
    pitch_order,
)

# Launch-angle ceilings, in order, defining batted-ball buckets
hit_types = {
    'Ground': 10,
    'Line': 25,
    'Fly': 50,
    'Pop': 180,
}

hit_types_markers = {
    'Ground': 'o',     # Circle
    'Line': '*',       # Star
    'Fly': 'X',        # X
    'Pop': 'P',        # Filled plus
}

# TrackMan writes fouls as FoulBallNotFieldable or FoulBallFieldable depending on
# export version, and older files just say FoulBall -- match on the prefix so whiff
# and swing rates stay correct across all three.
FOUL_PREFIX = 'Foul'
SWING_CALLS = ['StrikeSwinging', 'InPlay']
HIT_RESULTS = ['Single', 'Double', 'Triple', 'HomeRun']
TOTAL_BASES = {'Single': 1, 'Double': 2, 'Triple': 3, 'HomeRun': 4}

HARD_HIT_MPH = 95.0

# Define required columns and their types
required_columns = {
    'Batter': 'string',
    'BatterId': 'numeric',
    'TaggedPitchType': 'string',
    'PlateLocHeight': 'numeric',
    'PlateLocSide': 'numeric',
    'PitcherThrows': 'string',
    'PitchCall': 'string',
    'PlayResult': 'string',
    'KorBB': 'string',
    'PitcherTeam': 'string',
    'BatterTeam': 'string',
    'Date': 'string',
    'Inning': 'numeric',
    'Balls': 'numeric',
    'Strikes': 'numeric',
    'ExitSpeed': 'numeric',
    'Angle': 'numeric',
    'Bearing': 'numeric',
    'Distance': 'numeric',
}


@overload
def calculate_x_y_coordinates(magnitude: float, angle: float) -> tuple[float, float]: ...
@overload
def calculate_x_y_coordinates(magnitude: float, angle: np.ndarray) -> tuple[np.ndarray, np.ndarray]: ...
@overload
def calculate_x_y_coordinates(magnitude: pd.Series, angle: pd.Series) -> tuple[pd.Series, pd.Series]: ...
def calculate_x_y_coordinates(
    magnitude: float | np.ndarray | pd.Series, angle: float | np.ndarray | pd.Series
) -> tuple[float | np.ndarray | pd.Series, float | np.ndarray | pd.Series]:
    """
    Polar TrackMan landing data to cartesian feet.

    Bearing is degrees off centre field, negative toward the left-field line, so a
    pulled ball from a right-handed hitter lands at negative x. Works on Series or
    scalars.
    """
    angle_rad = np.radians(angle)
    x = magnitude * np.sin(angle_rad)
    y = magnitude * np.cos(angle_rad)
    return x, y


def calculate_marker(angle: float) -> str:
    """Map a launch angle to its batted-ball marker. Scalar helper; plots use classify_hit_type."""
    for hit_type, threshold in hit_types.items():
        if angle <= threshold:
            return hit_types_markers[hit_type]
    return hit_types_markers['Pop']


def classify_hit_type(angles: pd.Series) -> pd.Series:
    """Vectorized launch angle to batted-ball bucket. Returns a Categorical."""
    return pd.cut(
        angles,
        bins=[-np.inf] + list(hit_types.values()),
        labels=list(hit_types.keys()),
    )


def _numeric(source: pd.DataFrame, column: str) -> pd.Series:
    """Column as float, or an all-NaN column when the export omitted it."""
    if column not in source.columns:
        return pd.Series(np.nan, index=source.index, dtype='float64')
    return pd.to_numeric(source[column], errors='coerce')


def _text(source: pd.DataFrame, column: str) -> pd.Series:
    """Column as string, blank where the export omitted it or the cell was null."""
    if column not in source.columns:
        return pd.Series('', index=source.index, dtype='object')
    return source[column].fillna('').astype(str)


def batter_rows(source: pd.DataFrame, batter_id: str | int) -> pd.DataFrame:
    """Every pitch seen by one batter. Ids are compared numerically to dodge int/float/str drift."""
    if source.empty or 'BatterId' not in source.columns:
        return source.iloc[0:0]

    ids = pd.to_numeric(source['BatterId'], errors='coerce')
    try:
        target = float(batter_id)
    except (TypeError, ValueError):
        return source.iloc[0:0]

    return source[ids == target]


def batter_name(source: pd.DataFrame, batter_id: str | int) -> str:
    """Display name for a batter id, falling back to the id itself if unresolved."""
    rows = batter_rows(source, batter_id)
    if rows.empty or 'Batter' not in rows.columns:
        return str(batter_id)
    names = rows['Batter'].dropna()
    return str(names.iloc[0]) if not names.empty else str(batter_id)


# GameID (not just Date) so a multi-game selection can't collide two different
# games' "Inning 1, 1st PA" into one at-bat. Mirrors report.py's _AB_KEY_COLUMNS.
_AB_KEY_COLUMNS = ['GameID', 'Inning', 'Top/Bottom', 'PAofInning']


def build_pitch_by_pitch_report(source: pd.DataFrame, batter_id: str | int, date_range: str) -> HitterPitchByPitchReport | None:
    """
    Group one hitter's plate appearances into at-bats for the simplified
    pitch-by-pitch report: a header (hitter, date range) plus every pitch seen,
    numbered in the order thrown. Mirrors report.build_pitch_by_pitch_report,
    grouped from the hitter's perspective -- the opponent per at-bat is the
    pitcher faced, not a batter.
    """
    try:
        rows = batter_rows(source, batter_id)
        if rows.empty:
            return None

        hitter_name = batter_name(source, batter_id)

        table = rows.reindex(columns=_AB_KEY_COLUMNS + [
            'Pitcher', 'PitcherThrows', 'PitchofPA', 'TaggedPitchType', 'RelSpeed',
            'Balls', 'Strikes', 'PitchCall', 'PlayResult', 'KorBB',
            'PlateLocSide', 'PlateLocHeight',
        ])
        table = table.dropna(subset=_AB_KEY_COLUMNS)
        table = table.sort_values(['Inning', 'PAofInning', 'PitchofPA'], kind='stable')

        at_bats: list[HitterPitchByPitchAtBat] = []
        for _, group in table.groupby(_AB_KEY_COLUMNS, sort=False):
            pitches_df = group.sort_values('PitchofPA', kind='stable')
            if pitches_df.empty:
                continue

            first_row = pitches_df.iloc[0]
            last_row = pitches_df.iloc[-1]
            pitcher_name = str(first_row['Pitcher']) if pd.notna(first_row['Pitcher']) else ''
            pitcher_throws = str(first_row['PitcherThrows']) if pd.notna(first_row['PitcherThrows']) else ''
            # The final-outcome result only lands on the pitch that ended the AB --
            # everything before it is 'Undefined', so read it off the last pitch.
            result = last_row['PlayResult'] if pd.notna(last_row['PlayResult']) and last_row['PlayResult'] != 'Undefined' else last_row['KorBB']
            result = format_result(str(result)) if pd.notna(result) else ''
            inning_label = f"{first_row['Top/Bottom']} {int(first_row['Inning'])}" if pd.notna(first_row['Inning']) else ''

            pitches: list[PitchByPitchPitch] = [
                PitchByPitchPitch(
                    number=i,
                    pitch_type=pitch_order.get(pitch['TaggedPitchType'], str(pitch['TaggedPitchType'])) if pd.notna(pitch['TaggedPitchType']) else '',
                    velo=float(pitch['RelSpeed']) if pd.notna(pitch['RelSpeed']) else None,
                    balls=int(pitch['Balls']) if pd.notna(pitch['Balls']) else 0,
                    strikes=int(pitch['Strikes']) if pd.notna(pitch['Strikes']) else 0,
                    result=format_result(str(pitch['PitchCall'])) if pd.notna(pitch['PitchCall']) else '',
                    plate_loc_side=float(pitch['PlateLocSide']) if pd.notna(pitch['PlateLocSide']) else None,
                    plate_loc_height=float(pitch['PlateLocHeight']) if pd.notna(pitch['PlateLocHeight']) else None,
                )
                for i, (_, pitch) in enumerate(pitches_df.iterrows(), start=1)
            ]

            at_bats.append(HitterPitchByPitchAtBat(
                inning=inning_label, pitcher_name=pitcher_name, pitcher_throws=pitcher_throws,
                result=result, pitches=pitches,
            ))

        return HitterPitchByPitchReport(hitter_name=hitter_name, date_range=date_range, at_bats=at_bats)
    except Exception as e:
        print(f"Error building pitch-by-pitch report for batter ID {batter_id}: {e}")
        return None


def _swings(pitch_calls: pd.Series) -> pd.Series:
    """Whether each pitch call was a swing: a whiff, ball in play, or foul."""
    return pitch_calls.isin(SWING_CALLS) | pitch_calls.str.startswith(FOUL_PREFIX)


def build_hitter_summary(source: pd.DataFrame, batter_id: str | int) -> dict[str, str]:
    """
    Slash line and batted-ball profile for one hitter, as a label -> display-string dict
    suitable for PDF_Generator.generate_stats_grid and for direct rendering on the page.

    A plate appearance ends on a strikeout, a walk, a hit by pitch, or a ball in play,
    so those are the rows counted rather than every pitch seen.
    """
    rows = batter_rows(source, batter_id)
    if rows.empty:
        return {}

    pitch_call = _text(rows, 'PitchCall')
    play_result = _text(rows, 'PlayResult')
    kor_bb = _text(rows, 'KorBB')

    walks = int((kor_bb == 'Walk').sum())
    strikeouts = int((kor_bb == 'Strikeout').sum())
    hbp = int((pitch_call == 'HitByPitch').sum())
    in_play = int((pitch_call == 'InPlay').sum())

    plate_appearances = walks + strikeouts + hbp + in_play
    sacrifices = int((play_result == 'Sacrifice').sum())

    hits = int(play_result.isin(HIT_RESULTS).sum())
    doubles = int((play_result == 'Double').sum())
    triples = int((play_result == 'Triple').sum())
    homers = int((play_result == 'HomeRun').sum())
    total_bases = int(play_result.map(TOTAL_BASES).fillna(0).sum())

    at_bats = plate_appearances - walks - hbp - sacrifices
    on_base_chances = at_bats + walks + hbp + sacrifices

    average = hits / at_bats if at_bats > 0 else 0.0
    on_base = (hits + walks + hbp) / on_base_chances if on_base_chances > 0 else 0.0
    slugging = total_bases / at_bats if at_bats > 0 else 0.0

    batted = pitch_call == 'InPlay'
    exit_speed = _numeric(rows, 'ExitSpeed')[batted].dropna()
    launch_angle = _numeric(rows, 'Angle')[batted].dropna()
    hard_hit = int((exit_speed >= HARD_HIT_MPH).sum())

    def rate(value: float) -> str:
        # Baseball convention drops the leading zero on sub-1.000 rate stats
        return f"{value:.3f}".lstrip('0') if value < 1 else f"{value:.3f}"

    return {
        'PA': str(plate_appearances),
        'AB': str(at_bats),
        'H': str(hits),
        'AVG': rate(average),
        'OBP': rate(on_base),
        'SLG': rate(slugging),
        'OPS': rate(on_base + slugging),
        '2B': str(doubles),
        '3B': str(triples),
        'HR': str(homers),
        'BB%': f"{walks / plate_appearances * 100:.1f}%" if plate_appearances else '-',
        'K%': f"{strikeouts / plate_appearances * 100:.1f}%" if plate_appearances else '-',
        'Avg EV': f"{exit_speed.mean():.1f}" if not exit_speed.empty else '-',
        'Max EV': f"{exit_speed.max():.1f}" if not exit_speed.empty else '-',
        'Hard-Hit%': f"{hard_hit / len(exit_speed) * 100:.1f}%" if not exit_speed.empty else '-',
        'Avg LA': f"{launch_angle.mean():.1f}" if not launch_angle.empty else '-',
    }


class _HasPitchType(Protocol):
    @property
    def pitch_type(self) -> str: ...


_HD = TypeVar('_HD', bound=_HasPitchType)


def _order_by_pitch_type(stats: list[_HD]) -> list[_HD]:
    """
    Sort into the shared pitch_order so tables read the same as the pitcher reports.

    Anything TrackMan tags outside that order -- a rare pitch like Screwball, or a
    school's own custom tag -- is appended as its own category, in first-seen order,
    rather than dropped.
    """
    order = list(pitch_order.values())
    order += [s.pitch_type for s in stats if s.pitch_type not in order]
    order_index = {p: i for i, p in enumerate(order)}
    return sorted(stats, key=lambda s: order_index[s.pitch_type])


def build_hitter_discipline_table(source: pd.DataFrame, batter_id: str | int) -> HitterDisciplineTable:
    """
    Plate discipline per pitch type.

    Whiff% is misses over swings and Chase% is swings over pitches outside the zone --
    the standard denominators, which differ from the per-pitch rates report.build_table
    uses for pitchers.
    """
    rows = batter_rows(source, batter_id)
    if rows.empty:
        return HitterDisciplineTable([])

    pitch_call = _text(rows, 'PitchCall')
    pitch_types = _text(rows, 'TaggedPitchType')

    plate_side = _numeric(rows, 'PlateLocSide')
    plate_height = _numeric(rows, 'PlateLocHeight')

    # in_zone reads a NaN location as "not in the zone", which is the safe answer
    # for a single pitch but the wrong one for a denominator -- an untracked pitch
    # is not evidence of a pitch off the plate. Counting it as such inflates the
    # chase denominator and deflates Zone%, and a swing at one would post as a
    # chase. Zone and Chase are therefore rated over located pitches only; Seen,
    # Usage, Swing, Whiff and Contact still cover every pitch.
    located = plate_side.notna() & plate_height.notna()
    zone = in_zone(plate_side, plate_height)

    swing = _swings(pitch_call)
    whiff = pitch_call == 'StrikeSwinging'

    stats: list[HitterDisciplineStat] = []
    total = len(rows)

    for pitch_type in pitch_types.unique():
        if pitch_type in ('', 'n/a', 'Other'):
            continue

        mask = pitch_types == pitch_type
        seen = int(mask.sum())
        if seen == 0:
            continue

        swings = int((swing & mask).sum())
        whiffs = int((whiff & mask).sum())

        tracked = int((mask & located).sum())
        in_strike_zone = int((zone & mask).sum())
        out_of_zone = int((~zone & mask & located).sum())
        chases = int((swing & ~zone & mask & located).sum())

        stats.append(HitterDisciplineStat(
            pitch_type=pitch_order.get(pitch_type, pitch_type),
            seen=seen,
            usage_pct=seen / total * 100,
            zone_pct=in_strike_zone / tracked * 100 if tracked else 0.0,
            swing_pct=swings / seen * 100,
            whiff_pct=whiffs / swings * 100 if swings else 0.0,
            chase_pct=chases / out_of_zone * 100 if out_of_zone else 0.0,
            contact_pct=(swings - whiffs) / swings * 100 if swings else 0.0,
        ))

    return HitterDisciplineTable(_order_by_pitch_type(stats))


def build_batted_ball_table(source: pd.DataFrame, batter_id: str | int) -> BattedBallTable:
    """Batted-ball mix with exit velocity and launch angle per bucket."""
    rows = batter_rows(source, batter_id)
    if rows.empty:
        return BattedBallTable([])

    batted = rows[_text(rows, 'PitchCall') == 'InPlay'].copy()
    if batted.empty:
        return BattedBallTable([])

    batted['_Angle'] = _numeric(batted, 'Angle')
    batted['_ExitSpeed'] = _numeric(batted, 'ExitSpeed')
    batted['_Distance'] = _numeric(batted, 'Distance')
    batted['_HitType'] = classify_hit_type(batted['_Angle'])

    total = len(batted)
    stats: list[BattedBallStat] = []

    for hit_type in hit_types:
        bucket = batted[batted['_HitType'] == hit_type]
        if bucket.empty:
            continue

        exit_speed = bucket['_ExitSpeed'].dropna()
        stats.append(BattedBallStat(
            hit_type=hit_type,
            count=len(bucket),
            rate_pct=len(bucket) / total * 100,
            avg_ev=exit_speed.mean() if not exit_speed.empty else None,
            max_ev=exit_speed.max() if not exit_speed.empty else None,
            avg_launch_angle=bucket['_Angle'].mean() if bucket['_Angle'].notna().any() else None,
            avg_distance=bucket['_Distance'].mean() if bucket['_Distance'].notna().any() else None,
        ))

    return BattedBallTable(stats)


def custom_stats_table(source: pd.DataFrame, batter_id: str | int, school_id: int) -> CustomStatsTable | None:
    """Custom statistics table for one hitter, built by the school's custom_hitter_report.py (tier 3)."""
    try:
        custom_module = load_custom_module(school_id, 'custom_hitter_report.py')
        if custom_module is None:
            return None

        get_stats = getattr(custom_module, "get_stats", None)
        if get_stats is None:
            return None

        rows: list[CustomStat] = get_stats(source, batter_id) or []
        return CustomStatsTable(rows) if rows else None
    except Exception as e:
        print(f"Error generating custom hitter stats table for batter ID {batter_id}: {e}")
        return None


def custom_hit_type_stats_table(source: pd.DataFrame, batter_id: str | int, school_id: int) -> list[CustomHitTypeStatsTable] | None:
    """Custom hit-type-broken-out stats tables for one hitter, built by the school's custom_hitter_report.py (tier 3)."""
    try:
        custom_module = load_custom_module(school_id, 'custom_hitter_report.py')
        if custom_module is None:
            return None

        get_hit_type_stats = getattr(custom_module, "get_hit_type_stats", None)
        if get_hit_type_stats is None:
            return None

        tables: list[CustomHitTypeStatsTable] = get_hit_type_stats(source, batter_id) or []
        return tables or None
    except Exception as e:
        print(f"Error generating custom hit-type stats table for batter ID {batter_id}: {e}")
        return None


def custom_pitch_type_stats_table(source: pd.DataFrame, batter_id: str | int, school_id: int) -> list[CustomPitchTypeStatsTable] | None:
    """Custom pitch-type-broken-out stats tables for one hitter, built by the school's custom_hitter_report.py (tier 3)."""
    try:
        custom_module = load_custom_module(school_id, 'custom_hitter_report.py')
        if custom_module is None:
            return None

        get_pitch_type_stats = getattr(custom_module, "get_pitch_type_stats", None)
        if get_pitch_type_stats is None:
            return None

        tables: list[CustomPitchTypeStatsTable] = get_pitch_type_stats(source, batter_id) or []
        return tables or None
    except Exception as e:
        print(f"Error generating custom pitch-type stats table for batter ID {batter_id}: {e}")
        return None


MAX_CUSTOM_CHARTS = 6
MAX_CUSTOM_FIGURE_BYTES = 1_000_000


def _valid_custom_chart(chart: object) -> CustomChart | None:
    """A chart a school's script returned, if it is one the page can safely draw: a title and a
    Plotly {'data': [...], 'layout': {...}} that is strict JSON (a bare NaN would break the
    stream the page reads) and not enormous. Anything else is logged and skipped."""
    if not isinstance(chart, CustomChart):
        print(f"Skipping custom chart: expected a CustomChart, got {type(chart).__name__} "
              "(a script still returning image paths needs updating)")
        return None
    figure = chart.figure
    if not (isinstance(chart.title, str) and chart.title and isinstance(figure, dict)
            and isinstance(figure.get('data'), list) and isinstance(figure.get('layout'), dict)):
        print(f"Skipping custom chart {chart.title!r}: figure must be {{'data': [...], 'layout': {{...}}}}")
        return None
    try:
        size = len(json.dumps(figure, allow_nan=False))
    except (TypeError, ValueError) as e:
        print(f"Skipping custom chart {chart.title!r}: figure is not strict JSON ({e})")
        return None
    if size > MAX_CUSTOM_FIGURE_BYTES:
        print(f"Skipping custom chart {chart.title!r}: figure is {size} bytes")
        return None
    return chart


def custom_charts(source: pd.DataFrame, batter_id: str | int, school_id: int) -> list[CustomChart] | None:
    """
    Custom charts for one hitter, built by the school's own custom_hitter_report.py (tier 3).

    The script's `get_charts(source, batter_id)` returns CustomChart(title, figure) -- a Plotly
    figure the browser draws and exports (see hitter_stats.CustomChart). Anything it returns that
    isn't a valid chart is logged and skipped, and so is a script that raises, so one bad chart
    degrades that chart only.
    """
    try:
        custom_module = load_custom_module(school_id, 'custom_hitter_report.py')
        if custom_module is None:
            return None

        get_charts = getattr(custom_module, "get_charts", None)
        if get_charts is None:
            return None

        returned = get_charts(source, batter_id) or []
        charts = [c for c in (_valid_custom_chart(item) for item in returned[:MAX_CUSTOM_CHARTS]) if c is not None]
        return charts or None
    except Exception as e:
        print(f"Error generating custom charts for batter ID {batter_id}: {e}")
        return None
