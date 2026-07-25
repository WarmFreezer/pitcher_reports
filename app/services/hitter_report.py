import os
import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib

from app.services.plot_theme import (
    baseball_width,
    THEME_COLORS,
    make_strike_zone,
    make_shadow_zone,
    make_homeplate,
    cmap,
    pitch_order,
    pitch_point_colors
)

from matplotlib import pyplot as plt

# Define required columns and their types
required_columns = {
    'Batter': 'string', 
    'BatterId': 'numeric', 
    'TaggedPitchType': 'string', 
    'PlateLocHeight': 'numeric', 
    'PlateLocSide': 'numeric', 
    'PitcherSide': 'string',
    'PitchCall': 'string',
    'PitcherTeam': 'string',
    'BatterTeam': 'string',
    'Date': 'string',
    'Inning': 'numeric',
    'Balls': 'numeric',
    'Strikes': 'numeric'
}

def build_hitter_table(source, batter_id):
    # placeholder
    print(f"Building hitter table for batter_id: {batter_id} from source: {source}")

def hitter_heat_map_by_pitcher_side(source, batter_id):
    try:
        matplotlib.rcParams.update(THEME_COLORS.get(theme, THEME_COLORS['light']))

        table = source[['Batter', 'BatterId', 'TaggedPitchType', 'PlateLocHeight', 'PlateLocSide', 'PitcherSide']]
        # Batter Data is the data for the batter identified by batter_id
        batter_data = table[table['BatterId'] == batter_id]

        for pitcher_side in ['L', 'R']:
            fig = None
            try: 
                fig, ax = plt.subplots(figsize=(8, 6))
                # Pitcher Data is the data for the batter identified, filtered by the current pitcher side (L or R)
                # You can further sort it by the type of ball thrown, etc.
                pitcher_data = batter_data[batter_data['PitcherSide'] == pitcher_side]
                
                if len(pitcher_data) == 0:
                    ax.text(0, 2.5, f'No data for {pitcher_side}-handed pitches',
                        ha='center', va='center', fontsize=14)
                    ax.set_xlim(-2.5, 2.5)
                    ax.set_ylim(0, 5)
                else:
                    pitch_types = pitcher_data['TaggedPitchType'].unique()
                    pitch_types = [pt for pt in pitch_types if pt != 'n/a']

                    for pitch_type in pitch_types:
                        # Strike data is the pitcher data filtered by the current pitch type and a strike is called
                        swing_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type \
                            and pitcher_data['PitchCall'] == 'Strike']
                        ball_data
                        cmap = pitch_colors.get(pitch_type, 'viridis')
                        point_color = pitch_point_colors.get(pitch_type, '#000000')

                        bw_adjust = 1.5 if len(pitch_data) < 20 else 1.0
                        point_color = pitch_point_colors.get(pitch_type, '#000000')
                        ax.scatter(
                            avg_side,
                            avg_height,
                            color=point_color,
                            marker='.',
                            s=100,
                            zorder=5,
                            label=f'{pitch_order.get(pitch_type)}: {len(pitch_data)} pitches'
                        )

            except Exception as e:
                print(f"Error generating heat map ({batter_side}) for pitcher ID {pitcher_id}: {e}")
            finally:
                if fig is not None:
                    plt.close(fig)

    except Exception as e:
        print(f"Error generating heat maps for pitcher ID {pitcher_id}: {e}")

def hitter_spray_chart_by_pitcher_side(source, batter_id):
    # placeholder
    print(f"Generating hit spray chart by pitcher side for batter_id: {batter_id} from source: {source}")