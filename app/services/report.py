import numpy as np
import pandas as pd
import matplotlib

# Use a non-interactive backend for matplotlib
matplotlib.use('Agg') 

from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.patches import Rectangle
from matplotlib import pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import os

def _cmap(hex_color, name):
    r, g, b = to_rgb(hex_color)
    return LinearSegmentedColormap.from_list(name, [(r, g, b, 0), (r, g, b, 1)])

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

# Order to display pitch types in tables and plots
pitch_order = {
    'Fastball': 'FB',
    'Curveball': 'CB',
    'Slider': 'SL',
    'ChangeUp': 'CH',
    'Splitter': 'SP',
    'Knuckleball': 'KB',
    'Cutter': 'CT',
    'Sinker': 'SK',
    'Four-Seam': 'FF',
    'Undefined': 'UN'
}
    
pitch_point_colors = {
    'Fastball': '#d22d49',
    'Curveball': '#00d1ed',
    'Slider': '#004400',
    'ChangeUp': '#1dbe3a',
    'Splitter': '#4f0010',
    'Knuckleball': '#472cee',
    'Cutter': '#933f2c',
    'Sinker': '#fe9d00',
    'Four-Seam': '#FF0088',
    'Undefined': '#888888'
}

# Define colors for each pitch type
pitch_colors = {k: _cmap(v, k) for k, v in pitch_point_colors.items()}

STRIKES = ['StrikeCalled', 'StrikeSwinging', 'FoulBallNotFieldable']

baseball_width = 0.24  # Approximate width of a baseball in feet

def build_table(source, pitcher_id):
    try:
        try:     
            date = source['Date'].mode()[0] if 'Date' in source.columns else ''
            away_team = source['BatterTeam'].iloc[0] if 'BatterTeam' in source.columns else ''
            home_team = source['PitcherTeam'].iloc[0] if 'PitcherTeam' in source.columns else ''
        except Exception as e:
            date = ''
            away_team = ''
            home_team = ''

        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'RelSpeed', 'InducedVertBreak', 'HorzBreak', 'SpinRate', 'VertApprAngle', 'HorzApprAngle', 'RelHeight', 'RelSide', 'Extension', 'Tilt', 'ZoneTime', 'PlateLocHeight', 'PlateLocSide', 'PitchCall']] 

        pitcher_data = table[table['PitcherId'] == pitcher_id]
        pitcher = pitcher_data['Pitcher'].iloc[0]

        # Dictionary to hold data for each pitch type per game
        game_report = {'Pitch': [],
                    'Thrown': [],
                    'Low' : [],
                    'Vel.': [],
                    'High': [],
                    'IVB': [],
                    'HB': [],
                    'Spin': [],
                    'VAA': [],
                    'HAA': [],
                    'RelH': [],
                    'RelS': [],
                    'Ext.': [],
                    'Axis': [],
                    'Zone': [],
                    'Chase': [],
                    'CSW': []}
                        
        # Parse through each pitch type for the pitcher
        for pitch_type in pitcher_data['TaggedPitchType'].unique():
            pitch_type_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
            # If type is defined
            if (pitch_type != 'n/a'):
                # Add the stats of the pitch type to the report 
                game_report['Pitch'].append(pitch_type)
                game_report['Thrown'].append(len(pitch_type_data) / len(pitcher_data) * 100)
                game_report['Low'].append(pitch_type_data['RelSpeed'].min())
                game_report['Vel.'].append(pitch_type_data['RelSpeed'].mean())
                game_report['High'].append(pitch_type_data['RelSpeed'].max())
                game_report['IVB'].append(pitch_type_data['InducedVertBreak'].mean())
                game_report['HB'].append(pitch_type_data['HorzBreak'].mean())
                game_report['Spin'].append(pitch_type_data['SpinRate'].mean())
                game_report['VAA'].append(pitch_type_data['VertApprAngle'].mean())
                game_report['HAA'].append(pitch_type_data['HorzApprAngle'].mean())
                game_report['RelH'].append(pitch_type_data['RelHeight'].mean())
                game_report['RelS'].append(pitch_type_data['RelSide'].mean())
                game_report['Ext.'].append(pitch_type_data['Extension'].mean())

                # Parse Tilt values and report only hour:minute
                tilt_text = pitch_type_data['Tilt'].astype(str).str.strip()
                tilt_parsed = pd.to_datetime(tilt_text, format='%H:%M', errors='coerce')
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%H:%M:%S', errors='coerce'))
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%I:%M:%S %p', errors='coerce'))
                tilt_parsed = tilt_parsed.fillna(pd.to_datetime(tilt_text, format='%I:%M %p', errors='coerce')).dropna()
                axis_mean = tilt_parsed.mean()
                axis_time = axis_mean.strftime('%H:%M') if not pd.isna(axis_mean) else 'N/A'

                game_report['Axis'].append(axis_time) 
                game_report['Zone'].append(pitch_type_data['ZoneTime'].mean() * 100)

                # Calculate Chase %
                chase_count = 0
                for _, row in pitch_type_data.iterrows():
                    outside = (row['PlateLocHeight'] < 1.5) or (row['PlateLocHeight'] > 3.5)
                    outside_height = abs(row['PlateLocSide']) > 0.83
                    batter_swung = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay', 'HitByPitch']
                    
                    if (outside or outside_height) and batter_swung:
                        chase_count += 1
                        
                game_report['Chase'].append(chase_count / len(pitch_type_data) * 100.00)
                
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
                
                csw_percent = (called_strike_count + swinging_strike_count) / len(pitch_type_data) * 100.00
                game_report['CSW'].append(csw_percent)

        
        # Set panda options to show all rows/columns
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_colwidth', None)

        # Build and map pitch abbreviations to report dataframe
        report_df = pd.DataFrame(game_report)
        report_df['Pitch'] = report_df['Pitch'].map(pitch_order)
        report_df['Thrown'] = report_df['Thrown'].map(lambda x: f"{x:.1f}%")
        report_df['Zone'] = report_df['Zone'].map(lambda x: f"{x:.1f}%")
        report_df['Chase'] = report_df['Chase'].map(lambda x: f"{x:.1f}%")
        report_df['CSW'] = report_df['CSW'].map(lambda x: f"{x:.1f}%")

        # Take the top 4 most thrown pitches for the report
        report_df = report_df.sort_values('Thrown', ascending=False).head(6)

        # Sort by constant order
        pitch_order_list = list(pitch_order.values())
        report_df['Pitch'] = pd.Categorical(report_df['Pitch'], categories=pitch_order_list, ordered=True)
        report_df.sort_values('Pitch', inplace=True)

        return [date, home_team, away_team, str(pitcher), report_df]
        
    except Exception as e:
        print(f"Error building table for pitcher ID {pitcher_id}: {e}")
        return None

def pitch_heat_map_by_batter_side(source, id, output_path, pitcher_id, threshold=0.1):
    try:        
        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PlateLocHeight', 'PlateLocSide', 'BatterSide']] 
        pitcher_data = table[table['PitcherId'] == pitcher_id]
        
        # Create subplots for left and right handed batters
        fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(18, 8))
        
        # Process each batter side
        for batter_side, ax in [('Left', ax_left), ('Right', ax_right)]:
            batter_data = pitcher_data[pitcher_data['BatterSide'] == batter_side]
            
            if len(batter_data) == 0:
                ax.text(0, 2.5, f'No data for {batter_side}-handed batters', 
                    ha='center', va='center', fontsize=14)
                ax.set_xlim(-2.5, 2.5)
                ax.set_ylim(0, 5)
                continue
            
            # Get unique pitch types for this batter side
            pitch_types = batter_data['TaggedPitchType'].unique()
            pitch_types = [pt for pt in pitch_types if pt != 'n/a']
            
            # Plot each pitch type
            for pitch_type in pitch_types:
                pitch_data = batter_data[batter_data['TaggedPitchType'] == pitch_type]
                cmap = pitch_colors.get(pitch_type, 'viridis')
                point_color = pitch_point_colors.get(pitch_type, '#000000')
                
                # Use KDE for pitch types with 5 or more pitches
                if len(pitch_data) >= 5:
                    # Adjust bandwidth for better smoothing with sparse data
                    bw_adjust = 1.5 if len(pitch_data) < 20 else 1.0
                    
                    point_color = pitch_point_colors.get(pitch_type, '#000000')
                    sns.kdeplot(
                        x=pitch_data['PlateLocSide'],
                        y=pitch_data['PlateLocHeight'],
                        fill=True,
                        thresh=threshold,       
                        cmap=cmap,
                        bw_adjust=bw_adjust,
                        ax=ax,
                        levels=10
                    )

                    # Plot average pitch location for pitch type
                    avg_side = pitch_data['PlateLocSide'].mean()
                    avg_height = pitch_data['PlateLocHeight'].mean()
                    ax.scatter(
                        avg_side, 
                        avg_height,
                        color=point_color,
                        marker='.',
                        s=100,
                        zorder=5,
                        label=f'{pitch_order.get(pitch_type)}: {len(pitch_data)} pitches'
                    )
                else:
                    # Plot individual points
                    ax.scatter(
                        pitch_data['PlateLocSide'],
                        pitch_data['PlateLocHeight'],
                        color=point_color,
                        alpha=0.6,
                        s=50,
                        zorder=5,
                        edgecolors='black',
                        linewidth=0.5,
                        label=f'{pitch_order.get(pitch_type, pitch_type)}: {len(pitch_data)} pitches'
                    )
            
            # Set plot properties
            ax.set_title(f'vs {batter_side}-Handed Batters (n={len(batter_data)})', fontsize=14, fontweight='bold', pad=10)
            ax.set_xlabel('Plate Location Side (ft)', fontsize=12, labelpad=8)
            ax.set_ylabel('Plate Location Height (ft)', fontsize=12, labelpad=8)
            ax.set_xlim(-2.5, 2.5)
            ax.set_ylim(0, 5)
            ax.set_aspect('equal', adjustable='box')
            
            # Add strike zone rectangle (approximate)
            strike_zone = Rectangle((-0.83, 1.5), 1.66, 2.0, 
                                linewidth=2, edgecolor='black', 
                                facecolor='none', linestyle='--')
            ax.add_patch(strike_zone)

            # Add shadow zone rectangle (approximate)
            shadow_zone = Rectangle(
                (-0.83 - baseball_width, 1.5 - baseball_width), 
                1.66 + 2 *baseball_width, 
                2.0 + 2 * baseball_width, 
                                linewidth=1, edgecolor='gray', 
                                facecolor='none', linestyle=(0, (1, 10)))
            ax.add_patch(shadow_zone)
            
        # Adjust spacing to make room for title
        plt.subplots_adjust(left=0.06, right=0.96, top=0.88, bottom=0.1, wspace=0.2)

        # Save the figure in the output folder for report building
        plt.savefig(os.path.join(output_path, f'{id}_pitcher_{pitcher_id}_heat_map.png'), pad_inches=0.3, dpi=300, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f"Error generating heat map for pitcher ID {pitcher_id}: {e}")

def pitch_break_map(source, id, output_path, pitcher_id, threshold=0.1):
    try:
        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'InducedVertBreak', 'HorzBreak', ]] 
        pitcher_data = table[table['PitcherId'] == pitcher_id]

        # Create subplot for pitch break
        fig, ax = plt.subplots(figsize=(9, 8))
        
        if len(pitcher_data) == 0:
            ax.text(0, 2.5, f'No data for pitcher ID {pitcher_id}', 
                ha='center', va='center', fontsize=14)
            ax.set_xlim(-2.5, 2.5)
            ax.set_ylim(0, 5)
            plt.savefig(os.path.join(output_path, f'{id}_pitcher_{pitcher_id}_break_map.png'), pad_inches=0.3, dpi=300, bbox_inches='tight')
            plt.close(fig)
            return
        
        # Get unique pitch types for this pitcher
        pitch_types = pitcher_data['TaggedPitchType'].unique()
        pitch_types = [pt for pt in pitch_types if pt != 'n/a']
        
        # Plot each pitch type
        for pitch_type in pitch_types:
            pitch_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
            cmap = pitch_colors.get(pitch_type, 'viridis')
            point_color = pitch_point_colors.get(pitch_type, '#000000')
            
            # Use KDE for pitch types with 5 or more pitches
            if len(pitch_data) >= 5:
                # Adjust bandwidth for better smoothing with sparse data
                bw_adjust = 1.5 if len(pitch_data) < 20 else 1.0
                
                point_color = pitch_point_colors.get(pitch_type, '#000000')
                sns.kdeplot(
                    x=pitch_data['HorzBreak'],
                    y=pitch_data['InducedVertBreak'],
                    fill=True,
                    thresh=threshold,       
                    cmap=cmap,
                    bw_adjust=bw_adjust,
                    ax=ax,
                    levels=10
                )

                # Plot average pitch location for pitch type
                avg_side = pitch_data['HorzBreak'].mean()
                avg_height = pitch_data['InducedVertBreak'].mean()
                ax.scatter(
                    avg_side, 
                    avg_height,
                    color=point_color,
                    marker='.',
                    s=100,
                    zorder=5,
                    label=f'{pitch_order.get(pitch_type, pitch_type)}: {len(pitch_data)} pitches'
                )
            else:
                # Plot individual points
                ax.scatter(
                    pitch_data['HorzBreak'],
                    pitch_data['InducedVertBreak'],
                    color=point_color,
                    alpha=0.6,
                    s=50,
                    zorder=5,
                    edgecolors='black',
                    linewidth=0.5,
                    label=f'{pitch_order.get(pitch_type, pitch_type)}: {len(pitch_data)} pitches'
                )

            # Plot pitch type average movement vector for the pitcher
            ax.quiver(0, 0, pitch_data['HorzBreak'].mean(), pitch_data['InducedVertBreak'].mean(), angles='xy', scale_units='xy', scale=1, color=pitch_point_colors.get(pitch_type, 'gray'), width=0.005)

        # Plot overall average movement vector for the pitcher
        arm_angle = np.degrees(np.arctan2(pitcher_data['InducedVertBreak'].mean(), pitcher_data['HorzBreak'].mean()))
        ax.quiver(0, 0, pitcher_data['HorzBreak'].mean(), pitcher_data['InducedVertBreak'].mean(), angles='xy', scale_units='xy', scale=1, color='gray', width=0.01)

        # Set plot properties
        ax.set_title(f'Pitch Break (n={len(pitcher_data)}), Arm Angle: {arm_angle:.1f}°', fontsize=14, fontweight='bold', pad=10)
        ax.set_xlabel('Horizontal Break (in)', fontsize=12, labelpad=8)
        ax.set_ylabel('Induced Vertical Break (in)', fontsize=12, labelpad=8)
        ax.set_xlim(-25, 25)
        ax.set_ylim(-25, 25)
        ax.grid(True, linestyle='--', alpha=0.5)
        ax.set_aspect('equal', adjustable='box')
        
        # Add legend
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), loc='lower right', fontsize=12)
        
        # Adjust spacing to make room for title
        plt.subplots_adjust(left=0.06, right=0.96, top=0.88, bottom=0.1, wspace=0.2)

        # Save the figure in the output folder for report building
        plt.savefig(os.path.join(output_path, f'{id}_pitcher_{pitcher_id}_break_map.png'), pad_inches=0.3, dpi=300, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        print(f"Error reading file for pitcher ID {pitcher_id}: {e}")
        return

def usage_table(source, pitcher_id):
    try:
        table = source[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PitchCall', 'BatterId', 'Inning', 'PAofInning', 'PitchofPA', 'BatterSide', 'Balls', 'Strikes']] 
        pitcher_data = table[table['PitcherId'] == pitcher_id]

        tables = []

        for batter_side in ['Left', 'Right']:
            side_data = pitcher_data[pitcher_data['BatterSide'] == batter_side]
            # Dictionary to hold data for each pitch type per game
            game_report = {'Pitch': [],
                            'Count': [],
                            'Strike': [],
                            '0-0': [],
                            "Hitter's" : [],
                            "Pitcher's": [],
                            '2k': [],
                            'Whiff': []}

            total_first_pitch_count = side_data[side_data['PitchofPA'] == 1].shape[0]
            total_hitter_favorable_count = (side_data['Balls'] > side_data['Strikes']).sum()
            total_pitcher_favorable_count = (side_data['Strikes'] > side_data['Balls']).sum()
            total_two_strike_count = (side_data['Strikes'] == 2).sum()

            for pitch_type in side_data['TaggedPitchType'].unique():
                pitch_type_data = side_data[side_data['TaggedPitchType'] == pitch_type]

                strike_count = pitch_type_data['PitchCall'].isin(STRIKES).sum()
                first_pitch_count = pitch_type_data[pitch_type_data['PitchofPA'] == 1].shape[0]
                hitter_favorable_count = (pitch_type_data['Balls'] > pitch_type_data['Strikes']).sum()
                pitcher_favorable_count = (pitch_type_data['Strikes'] > pitch_type_data['Balls']).sum()
                two_strike_count = (pitch_type_data['Strikes'] == 2).sum()
                whiff_count = pitch_type_data[pitch_type_data['PitchCall'].isin(['StrikeSwinging', 'FoulBallNotFieldable'])].shape[0]

                # Add the stats of the pitch type to the report 
                game_report['Pitch'].append(pitch_type)
                game_report['Strike'].append(strike_count / len(pitch_type_data) * 100)
                game_report['Count'].append(len(pitch_type_data))
                game_report['0-0'].append(first_pitch_count / total_first_pitch_count * 100)
                game_report["Hitter's"].append(hitter_favorable_count / total_hitter_favorable_count * 100)
                game_report["Pitcher's"].append(pitcher_favorable_count / total_pitcher_favorable_count * 100)
                game_report['2k'].append(two_strike_count / total_two_strike_count * 100)
                game_report['Whiff'].append(whiff_count / len(pitch_type_data) * 100)
    
            report = pd.DataFrame(game_report)
            report['Pitch'] = report['Pitch'].map(pitch_order)
            report['Strike'] = report['Strike'].map(lambda x: f"{x:.1f}%")
            report['0-0'] = report['0-0'].map(lambda x: f"{x:.1f}%")
            report["Hitter's"] = report["Hitter's"].map(lambda x: f"{x:.1f}%")
            report["Pitcher's"] = report["Pitcher's"].map(lambda x: f"{x:.1f}%")
            report['2k'] = report['2k'].map(lambda x: f"{x:.1f}%")
            report['Whiff'] = report['Whiff'].map(lambda x: f"{x:.1f}%")

            # Limit to top 4 most thrown pitches for the report
            report = report.sort_values('Count', ascending=False).head(6)

            # Sort by dictionary order
            pitch_order_list = list(pitch_order.values())
            report['Pitch'] = pd.Categorical(report['Pitch'], categories=pitch_order_list, ordered=True)
            report.sort_values('Pitch', inplace=True)

            tables.append(report)

        # Set panda options to show all rows/columns
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        pd.set_option('display.max_rows', None)
        pd.set_option('display.max_colwidth', None)

        return tables
        
    except Exception as e:
        print(f"Error building table for pitcher ID {pitcher_id}: {e}")
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

if __name__ == "__main__":
    input_file = "C:\\Users\\thoma\\Downloads\\20260221-WinthropUniversity-1_unverified.csv"
    source_df = pd.read_csv(input_file)

    print(usage_table(source_df, 10106264))