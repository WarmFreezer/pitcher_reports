import numpy as np
import pandas as pd
import matplotlib

# Use a non-interactive backend for matplotlib
matplotlib.use('Agg') 

from matplotlib import pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import os

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
    'SpinAxis': 'numeric', 
    'ZoneTime': 'numeric', 
    'PitchCall': 'string',
}

# Define colors for each pitch type
pitch_colors = {
        'Fastball': 'Reds',
        'Curveball': 'Blues',
        'Slider': 'Greens',
        'Changeup': 'Oranges',
        'Splitter': 'Purples',
        'Knuckleball': 'YlOrBr'
}
    
pitch_point_colors = {
    'Fastball': '#FF0000',
    'Curveball': '#0000FF',
    'Slider': '#00AA00',
    'Changeup': '#FF8800',
    'Splitter': '#AA00AA',
    'Knuckleball': '#CC8800'
}

def build_table(path, pitcherid):
    if path.endswith('.csv'):
        excel = pd.read_csv(path)
    elif path.endswith('.xlsx') or path.endswith('.xls'):
        excel = pd.read_excel(path)
    else: 
        raise ValueError("Unsupported file format. Please provide a .csv, .xlsx, or .xls file.")
    
    table = excel[['Pitcher', 'PitcherId', 'TaggedPitchType', 'RelSpeed', 'InducedVertBreak', 'HorzBreak', 'SpinRate', 'VertApprAngle', 'HorzApprAngle', 'RelHeight', 'RelSide', 'Extension', 'SpinAxis', 'ZoneTime', 'PlateLocHeight', 'PlateLocSide', 'PitchCall']] 

    pitcher_data = table[table['PitcherId'] == pitcherid]
    pitcher = pitcher_data['Pitcher'].iloc[0]

    # Dictionary to hold data for each pitch type per game
    game_report = {'Pitch': [],
                'Count': [],
                '% Thrown': [],
                'Vel.': [],
                'IVB': [],
                'HB': [],
                'Spin': [],
                'VAA': [],
                'HAA': [],
                'vRel': [],
                'hRel': [],
                'Ext.': [],
                'Axis': [],
                'Zone %': [],
                'Chase %': [],
                'Whiff %': []}
                    
    # Parse through each pitch type for the pitcher
    for pitch_type in pitcher_data['TaggedPitchType'].unique():
        pitch_type_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
        # If type is defined
        if (pitch_type != 'Undefined'):
            # Add the stats of the pitch type to the report 
            game_report['Pitch'].append(pitch_type)
            game_report['Count'].append(len(pitch_type_data))
            game_report['% Thrown'].append(len(pitch_type_data) / len(pitcher_data) * 100)
            game_report['Vel.'].append(pitch_type_data['RelSpeed'].mean())
            game_report['IVB'].append(pitch_type_data['InducedVertBreak'].mean())
            game_report['HB'].append(pitch_type_data['HorzBreak'].mean())
            game_report['Spin'].append(pitch_type_data['SpinRate'].mean())
            game_report['VAA'].append(pitch_type_data['VertApprAngle'].mean())
            game_report['HAA'].append(pitch_type_data['HorzApprAngle'].mean())
            game_report['vRel'].append(pitch_type_data['RelHeight'].mean())
            game_report['hRel'].append(pitch_type_data['RelSide'].mean())
            game_report['Ext.'].append(pitch_type_data['Extension'].mean())
            game_report['Axis'].append(pitch_type_data['SpinAxis'].mean()) 
            game_report['Zone %'].append(pitch_type_data['ZoneTime'].mean() * 100)

            chase_count = 0
            for _, row in pitch_type_data.iterrows():
                outside = (row['PlateLocHeight'] < 1.5) or (row['PlateLocHeight'] > 3.5)
                outside_height = abs(row['PlateLocSide']) > 0.83
                batter_swung = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay', 'HitByPitch']
                
                if (outside or outside_height) and batter_swung:
                    chase_count += 1
                    
            game_report['Chase %'].append(chase_count / len(pitch_type_data) * 100.00)
            
            whiff_count = 0
            for _, row in pitch_type_data.iterrows():
                swing_and_miss = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable']
                
                if swing_and_miss:
                    whiff_count += 1
            
            game_report['Whiff %'].append(whiff_count / len(pitch_type_data) * 100.00)
    
    # Set panda options to show all rows/columns
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_colwidth', None)

    # Build and print report dataframe
    report_df = pd.DataFrame(game_report)
    report_df.sort_values(by='Count', ascending=False, inplace=True)

    return [str(pitcher), report_df]

def pitch_heat_map_by_batter_side(path, pitcher_id, threshold=0.1):
    if path.endswith('.csv'):
        excel = pd.read_csv(path)
    elif path.endswith('.xlsx') or path.endswith('.xls'):
        excel = pd.read_excel(path)
    else: 
        raise ValueError("Unsupported file format. Please provide a .csv, .xlsx, or .xls file.")
    
    table = excel[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PlateLocHeight', 'PlateLocSide', 'BatterSide']] 
    pitcher_data = table[table['PitcherId'] == pitcher_id]
    
    # Create subplots for left and right handed batters
    fig, (ax_left, ax_right) = plt.subplots(1, 2, figsize=(18, 8))
    
    # Process each batter side
    for batter_side, ax in [('Left', ax_left), ('Right', ax_right)]:
        batter_data = pitcher_data[pitcher_data['BatterSide'] == batter_side]
        
        if len(batter_data) == 0:
            ax.text(0, 2.5, f'No data for {batter_side}-handed batters', 
                   ha='center', va='center', fontsize=14)
            ax.set_xlim(-3, 3)
            ax.set_ylim(0, 5)
            continue
        
        # Get unique pitch types for this batter side
        pitch_types = batter_data['TaggedPitchType'].unique()
        pitch_types = [pt for pt in pitch_types if pt != 'Undefined']
        
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
                    color=point_color,
                    alpha=0.6,
                    bw_adjust=bw_adjust,
                    ax=ax,
                    levels=2
                )
            
            # Plot individual points
            '''ax.scatter(
                pitch_data['PlateLocSide'],
                pitch_data['PlateLocHeight'],
                color=point_color,
                alpha=0.6,
                s=50,
                edgecolors='black',
                linewidth=0.5,
                label=f'{pitch_type} (n={len(pitch_data)})'
            )'''

            # Plot average pitch location for pitich type
            avg_side = pitch_data['PlateLocSide'].mean()
            avg_height = pitch_data['PlateLocHeight'].mean()
            ax.scatter(
                avg_side, 
                avg_height,
                color=point_color,
                marker='.',
                s=100,
                label=f'{pitch_type} Avg: {len(pitch_data)} pitches'
            )
        
        # Set plot properties
        ax.set_title(f'vs {batter_side}-Handed Batters (n={len(batter_data)})', fontsize=14, fontweight='bold', pad=10)
        ax.set_xlabel('Plate Location Side (ft)', fontsize=12, labelpad=8)
        ax.set_ylabel('Plate Location Height (ft)', fontsize=12, labelpad=8)
        ax.set_xlim(-3, 3)
        ax.set_ylim(0, 5)
        ax.set_aspect('equal', adjustable='box')
        
        # Add strike zone rectangle (approximate)
        from matplotlib.patches import Rectangle
        strike_zone = Rectangle((-0.83, 1.5), 1.66, 2.0, 
                               linewidth=2, edgecolor='black', 
                               facecolor='none', linestyle='--')
        ax.add_patch(strike_zone)
        
        # Add legend
        handles, labels = ax.get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        ax.legend(by_label.values(), by_label.keys(), loc='upper right', fontsize=12)
    
    # Overall title
    fig.suptitle(f'Pitch Location Heat Map for Pitcher ID: {pitcher_id}', 
                fontsize=16, fontweight='bold', y=0.99)
    
    # Adjust spacing to make room for title
    plt.subplots_adjust(left=0.06, right=0.96, top=0.88, bottom=0.1, wspace=0.2)

    # Save the figure in the output folder for report building
    plt.savefig(f'app/static/output/pitcher_{pitcher_id}_heat_map.png', pad_inches=0.3, dpi=300, bbox_inches='tight')
    plt.close()
