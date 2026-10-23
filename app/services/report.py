from typing import Any, Protocol, TypeVar

import pandas as pd

from app.services.custom_report_loader import load_custom_module
from app.services.pitch_stats import (
    GameReportHeader,
    PitchTypeStat,
    PitcherGameReport,
    PitcherStatsTable,
    PitchUsageStat,
    PitchUsageTable,
    PitchUsageSides,
    CustomStat,
    CustomStatsTable,
    CustomPitchTypeStatsTable,
    PitchByPitchPitch,
    PitchByPitchAtBat,
    PitchByPitchReport,
    BreakMapLegendEntry,
)
from app.services.report_theme import (
    pitch_order,
    pitch_point_colors,
    format_result,
    in_zone as zone_mask,
)


class _HasPitchType(Protocol):
    @property
    def pitch_type(self) -> str: ...


_T = TypeVar('_T', bound=_HasPitchType)


def _top_pitches(stats: list[_T], sort_key: Any, limit: int = 6) -> list[_T]:
    """Keep the `limit` highest-sort_key entries, then reorder by the canonical pitch_order."""
    kept = sorted(stats, key=sort_key, reverse=True)[:limit]
    order_index = {abbr: i for i, abbr in enumerate(pitch_order.values())}
    kept.sort(key=lambda s: order_index.get(s.pitch_type, len(order_index)))
    return kept

# Define required columns and their types
required_columns = {
    'Pitcher': 'string', 
    'PitcherId': 'numeric', 
    'TaggedPitchType': 'string', 
    'PlateLocHeight': 'numeric', 
    'PlateLocSide': 'numeric', 
    'BatterSide': 'string',
    'RelSpeed': 'numeric', 
    'InducedVertBreak': 'numeric', 
    'HorzBreak': 'numeric', 
    'SpinRate': 'numeric', 
    'VertApprAngle': 'numeric', 
    'HorzApprAngle': 'numeric', 
    'RelHeight': 'numeric', 
    'RelSide': 'numeric', 
    'Extension': 'numeric', 
    'Tilt': 'string',
    'ZoneTime': 'numeric', 
    'PitchCall': 'string',
    'PitcherTeam': 'string',
    'BatterTeam': 'string',
    'Date': 'string',
    'Inning': 'numeric',
    'PAofInning': 'numeric',
    'PitchofPA': 'numeric',
    'BatterId': 'numeric',
    'Balls': 'numeric',
    'Strikes': 'numeric'
}

STRIKES = ['StrikeCalled', 'StrikeSwinging', 'FoulBallNotFieldable']

def build_table(source: pd.DataFrame, pitcher_id: int) -> PitcherGameReport | None:
    """Per-pitch-type stats for one pitcher, aggregated across every row in source."""
    try:
        try:
            date = source['Date'].mode()[0] if 'Date' in source.columns else ''
            away_team = source['BatterTeam'].iloc[0] if 'BatterTeam' in source.columns else ''
            home_team = source['PitcherTeam'].iloc[0] if 'PitcherTeam' in source.columns else ''
        except Exception as e:
            date = ''
            away_team = ''
            home_team = ''

        # ExitSpeed/Angle are batted-ball-only fields and aren't in required_columns
        # (unlike hitter_report.py's own required_columns, which does require them) --
        # reindex rather than a plain [[...]] selection so an export that omits them
        # fills NaN instead of KeyError-ing the whole report.
        table = source.reindex(columns=[
            'Pitcher', 'PitcherId', 'TaggedPitchType', 'RelSpeed', 'InducedVertBreak', 'HorzBreak',
            'SpinRate', 'VertApprAngle', 'HorzApprAngle', 'RelHeight', 'RelSide', 'Extension', 'Tilt',
            'ZoneTime', 'PlateLocHeight', 'PlateLocSide', 'PitchCall', 'ExitSpeed', 'Angle',
        ])

        pitcher_data = table[table['PitcherId'] == pitcher_id]
        pitcher = pitcher_data['Pitcher'].iloc[0]

        stats: list[PitchTypeStat] = []

        # Parse through each pitch type for the pitcher
        for pitch_type in pitcher_data['TaggedPitchType'].unique():
            pitch_type_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
            # If type is defined
            if (pitch_type != 'n/a'):
                # Tilt is stored as a clock-face string (e.g. "12:30") in multiple possible
                # formats depending on the TrackMan export version — try each before giving up
                tilt_text = pitch_type_data['Tilt'].astype(str).str.strip()
                tilt_parsed = pd.to_datetime(tilt_text, format='%H:%M', errors='coerce')
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%H:%M:%S', errors='coerce'))
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%I:%M:%S %p', errors='coerce'))
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%I:%M %p', errors='coerce')).dropna()
                axis_mean = tilt_parsed.mean()
                axis_time = axis_mean.strftime('%H:%M') if not pd.isna(axis_mean) else 'N/A'

                # Chase %: pitch was outside the zone AND the batter swung
                chase_count = 0
                for _, row in pitch_type_data.iterrows():
                    outside = (row['PlateLocHeight'] < 1.5) or (row['PlateLocHeight'] > 3.5)
                    outside_height = abs(row['PlateLocSide']) > 0.83
                    batter_swung = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay', 'HitByPitch']
                    if (outside or outside_height) and batter_swung:
                        chase_count += 1

                # Calculate Whiff %
                whiff_count = 0
                for _, row in pitch_type_data.iterrows():
                    swing_and_miss = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable']

                    if swing_and_miss:
                        whiff_count += 1

                # Calculate Called Strikes %
                called_strike_count = 0
                for _, row in pitch_type_data.iterrows():
                    if (row['PitchCall'] in ['StrikeCalled']):
                        called_strike_count += 1

                # Calculate Swing and Miss %
                swinging_strike_count = 0
                for _, row in pitch_type_data.iterrows():
                    if (row['PitchCall'] in ['StrikeSwinging']):
                        swinging_strike_count += 1

                # CSW (Called Strike + Whiff) % — industry-standard pitcher effectiveness metric
                csw_percent = (called_strike_count + swinging_strike_count) / len(pitch_type_data) * 100.00

                # Damage %: of this pitch type's balls in play, how many were hit
                # 90+ mph with a 10-35 deg launch angle. NaN ExitSpeed/Angle (untracked
                # contact) compare False rather than raising, so they're excluded --
                # same "untracked isn't evidence" reasoning as report_theme.in_zone().
                in_play_mask = pitch_type_data['PitchCall'] == 'InPlay'
                in_play_count = int(in_play_mask.sum())
                damage_count = (
                    in_play_mask
                    & (pitch_type_data['ExitSpeed'] >= 90.0)
                    & (pitch_type_data['Angle'] > 10.0)
                    & (pitch_type_data['Angle'] <= 35.0)
                ).sum()
                damage_percent = (damage_count / in_play_count * 100.00) if in_play_count > 0 else 0.0

                in_zone = zone_mask(pitch_type_data['PlateLocSide'], pitch_type_data['PlateLocHeight'])

                stats.append(PitchTypeStat(
                    pitch_type=pitch_order.get(pitch_type, pitch_type),
                    thrown_pct=len(pitch_type_data) / len(pitcher_data) * 100,
                    velo_low=pitch_type_data['RelSpeed'].min(),
                    velo_avg=pitch_type_data['RelSpeed'].mean(),
                    velo_high=pitch_type_data['RelSpeed'].max(),
                    ivb=pitch_type_data['InducedVertBreak'].mean(),
                    hb=pitch_type_data['HorzBreak'].mean(),
                    spin=pitch_type_data['SpinRate'].mean(),
                    vaa=pitch_type_data['VertApprAngle'].mean(),
                    haa=pitch_type_data['HorzApprAngle'].mean(),
                    rel_height=pitch_type_data['RelHeight'].mean(),
                    rel_side=pitch_type_data['RelSide'].mean(),
                    extension=pitch_type_data['Extension'].mean(),
                    axis=axis_time,
                    zone_pct=in_zone.sum() / len(pitch_type_data) * 100,
                    chase_pct=chase_count / len(pitch_type_data) * 100.00,
                    csw_pct=csw_percent,
                    damage_pct=damage_percent,
                ))

        # Top 6 most-thrown pitches, then sorted into the canonical pitch_order
        stats = _top_pitches(stats, sort_key=lambda s: s.thrown_pct)

        header = GameReportHeader(date=date, home_team=home_team, away_team=away_team, pitcher_name=str(pitcher))
        return PitcherGameReport(header=header, stats=PitcherStatsTable(stats))

    except Exception as e:
        print(f"Error building table for pitcher ID {pitcher_id}: {e}")
        return None

def pitch_break_map_legend(source: pd.DataFrame, pitcher_id: int) -> list[BreakMapLegendEntry]:
    """
    Legend entries (abbreviation, color, pitch count) for pitch_break_map's
    chart -- one per pitch type actually plotted there. Kept separate from
    pitch_break_map itself (which no longer draws a legend on the chart) so
    callers can render it as their own element instead, and so it's computed
    once rather than once per light/dark theme render.
    """
    pitcher_data = source[source['PitcherId'] == pitcher_id]
    pitch_types = [pt for pt in pitcher_data['TaggedPitchType'].unique() if pt != 'n/a']
    return [
        BreakMapLegendEntry(
            abbreviation=pitch_order.get(pt, pt),
            color=pitch_point_colors.get(pt, '#888888'),
            count=int((pitcher_data['TaggedPitchType'] == pt).sum()),
        )
        for pt in pitch_types
    ]

def usage_table(source: pd.DataFrame, pitcher_id: int) -> PitchUsageSides | None:
    """Pitch-usage-by-count-situation tables for one pitcher, one per batter side (left, right)."""
    try:
        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PitchCall', 'BatterId', 'Inning', 'PAofInning', 'PitchofPA', 'BatterSide', 'Balls', 'Strikes', 'KorBB', 'PlayResult']]
        pitcher_data = table[table['PitcherId'] == pitcher_id]

        sides: dict[str, PitchUsageTable] = {}

        for batter_side in ['Left', 'Right']:
            side_data = pitcher_data[pitcher_data['BatterSide'] == batter_side]

            total_first_pitch_count = side_data[side_data['PitchofPA'] == 1].shape[0]
            total_hitter_favorable_count = (side_data['Balls'] > side_data['Strikes']).sum()
            total_pitcher_favorable_count = (side_data['Strikes'] > side_data['Balls']).sum()
            total_two_strike_count = (side_data['Strikes'] == 2).sum()

            stats: list[PitchUsageStat] = []

            for pitch_type in side_data['TaggedPitchType'].unique():
                pitch_type_data = side_data[side_data['TaggedPitchType'] == pitch_type]
                swing_data = pitch_type_data[pitch_type_data['PitchCall'].isin(['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay'])]

                strike_count = pitch_type_data['PitchCall'].isin(STRIKES).sum()
                first_pitch_count = pitch_type_data[pitch_type_data['PitchofPA'] == 1].shape[0]
                hitter_favorable_count = (pitch_type_data['Balls'] > pitch_type_data['Strikes']).sum()
                pitcher_favorable_count = (pitch_type_data['Strikes'] > pitch_type_data['Balls']).sum()
                two_strike_count = (pitch_type_data['Strikes'] == 2).sum()
                whiff_count = pitch_type_data[pitch_type_data['PitchCall'].isin(['StrikeSwinging', 'FoulBallNotFieldable'])].shape[0]

                stats.append(PitchUsageStat(
                    pitch_type=pitch_order.get(pitch_type, pitch_type),
                    count=len(pitch_type_data),
                    strike_pct=strike_count / len(pitch_type_data) * 100,
                    first_pitch_pct=first_pitch_count / total_first_pitch_count * 100 if total_first_pitch_count else 0,
                    hitter_favorable_pct=hitter_favorable_count / total_hitter_favorable_count * 100 if total_hitter_favorable_count else 0,
                    pitcher_favorable_pct=pitcher_favorable_count / total_pitcher_favorable_count * 100 if total_pitcher_favorable_count else 0,
                    two_strike_pct=two_strike_count / total_two_strike_count * 100 if total_two_strike_count else 0,
                    whiff_pct=(whiff_count / len(swing_data) if len(swing_data) > 0 else 0) * 100,
                ))

            # Top 6 most-thrown pitches, then sorted into the canonical pitch_order
            stats = _top_pitches(stats, sort_key=lambda s: s.count)
            sides[batter_side] = PitchUsageTable(stats)

            # A plate appearance ends on its last pitch: a walk/strikeout, a ball in play, or a HBP.
            # shortcut: a pitch filter that hides the PA-ending pitch drops that PA from the denominator too.
            ends_pa = (side_data['KorBB'].isin(['Walk', 'Strikeout'])
                       | side_data['PlayResult'].notna() & (side_data['PlayResult'] != 'Undefined')
                       | (side_data['PitchCall'] == 'HitByPitch'))
            pa = int(ends_pa.sum())
            if pa:
                bb = int((side_data['KorBB'] == 'Walk').sum())
                k = int((side_data['KorBB'] == 'Strikeout').sum())
                sides[batter_side].summary = f"{pa} PA · BB% {bb / pa * 100:.1f} · K% {k / pa * 100:.1f}"

        return PitchUsageSides(left=sides['Left'], right=sides['Right'])

    except Exception as e:
        print(f"Error building table for pitcher ID {pitcher_id}: {e}")
        return None


# GameID (not just Date) so a multi-game selection can't collide two different
# games' "Inning 1, 1st PA" into one at-bat.
_AB_KEY_COLUMNS = ['GameID', 'Inning', 'Top/Bottom', 'PAofInning']


def build_pitch_by_pitch_report(source: pd.DataFrame, pitcher_id: int) -> PitchByPitchReport | None:
    """
    Group one pitcher's pitches into at-bats for the simplified pitch-by-pitch
    report: a header (pitcher, date range, matchup) plus every plate appearance
    faced, each with its pitches numbered in the order thrown. Replaces the old
    raw-CSV-plus-chart-ZIP export, which dumped the full Trackman column set.
    """
    try:
        pitcher_data = source[source['PitcherId'] == pitcher_id]
        if pitcher_data.empty:
            return None

        pitcher_name = str(pitcher_data['Pitcher'].iloc[0]) if 'Pitcher' in pitcher_data.columns else ''
        # A multi-game selection can mix .xlsx sources (Date already parsed to
        # pandas Timestamp) with .csv ones (Date still a plain string) -- sorting
        # the raw column crashes comparing Timestamp to str. Route everything
        # through pd.to_datetime first, matching game_archive._game_date's fix
        # for the identical problem.
        if 'Date' in pitcher_data.columns:
            dates = sorted(pd.to_datetime(pitcher_data['Date'], errors='coerce').dropna().dt.date.unique())
        else:
            dates = []
        date_display = dates[0].isoformat() if len(dates) == 1 else f'{dates[0].isoformat()} - {dates[-1].isoformat()}' if dates else ''
        pitcher_team = pitcher_data['PitcherTeam'].mode()[0] if 'PitcherTeam' in pitcher_data.columns and not pitcher_data['PitcherTeam'].empty else ''
        batter_team = pitcher_data['BatterTeam'].mode()[0] if 'BatterTeam' in pitcher_data.columns and not pitcher_data['BatterTeam'].empty else ''
        matchup = f'{pitcher_team} vs {batter_team}' if pitcher_team and batter_team else (pitcher_team or batter_team)

        table = pitcher_data.reindex(columns=_AB_KEY_COLUMNS + [
            'Batter', 'BatterSide', 'PitchofPA', 'TaggedPitchType', 'RelSpeed',
            'Balls', 'Strikes', 'PitchCall', 'PlayResult', 'KorBB',
            'PlateLocSide', 'PlateLocHeight',
        ])
        table = table.dropna(subset=_AB_KEY_COLUMNS)
        table = table.sort_values(['Inning', 'PAofInning', 'PitchofPA'], kind='stable')

        at_bats: list[PitchByPitchAtBat] = []
        for _, group in table.groupby(_AB_KEY_COLUMNS, sort=False):
            pitches_df = group.sort_values('PitchofPA', kind='stable')
            if pitches_df.empty:
                continue

            first_row = pitches_df.iloc[0]
            last_row = pitches_df.iloc[-1]
            batter = str(first_row['Batter']) if pd.notna(first_row['Batter']) else ''
            batter_side = str(first_row['BatterSide']) if pd.notna(first_row['BatterSide']) else ''
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

            at_bats.append(PitchByPitchAtBat(
                inning=inning_label, batter_name=batter, batter_side=batter_side,
                result=result, pitches=pitches,
            ))

        return PitchByPitchReport(
            pitcher_name=pitcher_name, date=date_display, matchup=matchup, at_bats=at_bats,
        )
    except Exception as e:
        print(f"Error building pitch-by-pitch report for pitcher ID {pitcher_id}: {e}")
        return None


'''
def strikeout_map(source, id, output_path, pitcher_id):
    try:
        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PlateLocHeight', 'PlateLocSide', 'KorBB']] 
        pitcher_data = table[table['PitcherId'] == pitcher_id]

        # Filter for strikeout pitches
        strikeout_data = pitcher_data[pitcher_data['KorBB'] == 'Strikeout']
        
        # Create subplot for strikeout map
        fig, ax = plt.subplots(figsize=(9, 8))
        
        if len(strikeout_data) == 0:
            ax.text(0, 2.5, f'No strikeout data for pitcher ID {pitcher_id}', 
                ha='center', va='center', fontsize=14)
            ax.set_xlim(-3, 3)
            ax.set_ylim(0, 5)
            plt.savefig(os.path.join(output_path, f'{id}_pitcher_{pitcher_id}_strikeout_map.png'), pad_inches=0.3, dpi=300, bbox_inches='tight')
            plt.close()
            return
        
        # Plot strikeout pitch locations
        ax.scatter(
            strikeout_data['PlateLocSide'],
            strikeout_data['PlateLocHeight'],
            color='red',
            alpha=0.6,
            s=50,
            zorder=5,
            edgecolors='black',
            linewidth=0.5,
            label=f'Strikeouts: {len(strikeout_data)}'
        )

        # Set plot properties
        ax.set_title(f'Strikeout Pitch Locations (n={len(strikeout_data)}) for Pitcher ID: {pitcher_id}', fontsize=14, fontweight='bold', pad=10)
        ax.set_xlabel('Plate Location Side (ft)', fontsize=12, labelpad=8)
        ax.set_ylabel('Plate Location Height (ft)', fontsize=12, labelpad=8)
        ax.set_xlim(-3, 3)
        ax.set_ylim(0, 5)
        ax.set_aspect('equal', adjustable='box')
        
        # Add strike zone rectangle (approximate)
        strike_zone = Rectangle((-0.83, 1.5), 1.66, 2.0, 
                            linewidth=2, edgecolor='black', 
                            facecolor='none', linestyle='--')
        ax.add_patch(strike_zone)

        shadow_zone = Rectangle(
            (-0.83 - baseball_width, 1.5 - baseball_width), 
            1.66 + 2 *baseball_width, 
            2.0 + 2 * baseball_width, 
                            linewidth=1, edgecolor='gray', 
                            facecolor='none', linestyle=(0, (1, 10)))
        ax.add_patch(shadow_zone)

    except Exception as e:
        print(f"Error generating strikeout map for pitcher ID {pitcher_id}: {e}")
        return
'''

def custom_stats_table(source: pd.DataFrame, pitcher_id: int, school_id: int) -> CustomStatsTable | None:
    """Custom statistics table for one pitcher, built by the school's custom_pitcher_report.py (tier 3)."""
    try:
        custom_module = load_custom_module(school_id, 'custom_pitcher_report.py')
        if custom_module is None:
            return None

        get_stats = getattr(custom_module, "get_stats", None)
        if get_stats is None:
            return None

        rows: list[CustomStat] = get_stats(source, pitcher_id) or []
        return CustomStatsTable(rows) if rows else None
    except Exception as e:
        print(f"Error generating custom pitcher stats table for pitcher ID {pitcher_id}: {e}")
        return None

def custom_pitch_type_stats_table(source: pd.DataFrame, pitcher_id: int, school_id: int) -> list[CustomPitchTypeStatsTable] | None:
    """Custom pitch-type-broken-out stats tables for one pitcher, built by the school's custom_pitcher_report.py (tier 3)."""
    try:
        custom_module = load_custom_module(school_id, 'custom_pitcher_report.py')
        if custom_module is None:
            return None

        get_pitch_type_stats = getattr(custom_module, "get_pitch_type_stats", None)
        if get_pitch_type_stats is None:
            return None

        tables: list[CustomPitchTypeStatsTable] = get_pitch_type_stats(source, pitcher_id) or []
        return tables or None
    except Exception as e:
        print(f"Error generating custom pitch-type stats table for pitcher ID {pitcher_id}: {e}")
        return None

if __name__ == "__main__":
    input_file = "C:\\Users\\thoma\\Downloads\\20260221-WinthropUniversity-1_unverified.csv"
    source_df = pd.read_csv(input_file)

    print(usage_table(source_df, 10106264))