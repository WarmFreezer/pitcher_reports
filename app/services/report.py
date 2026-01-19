import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import matplotlib.patches as patches
import seaborn as sns
import os

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

def build_report(path):
    excel = pd.read_excel(path)
    table = excel[['Pitcher', 'PitcherId', 'TaggedPitchType', 'RelSpeed', 'InducedVertBreak', 'HorzBreak', 'SpinRate', 'VertApprAngle', 'HorzApprAngle', 'RelHeight', 'RelSide', 'Extension', 'SpinAxis', 'ZoneTime', 'PlateLocHeight', 'PlateLocSide', 'PitchCall']] 

    for pitcherid in table['PitcherId'].unique():
        pitcher_data = table[table['PitcherId'] == pitcherid]
        pitcher = pitcher_data['Pitcher'].iloc[0]

        #Dictionary to hold data for each pitch type per game
        game_report = {'PitchType': [],
                    'Count': [],
                    'PitchPercent': [],
                    'Avg_Velocity': [],
                    'Avg_Ivb': [],
                    'Avg_Hb': [],
                    'Avg_SpinRate': [],
                    'Avg_Vaa': [],
                    'Avg_Haa': [],
                    'Avg_RelHeight': [],
                    'Avg_RelSide': [],
                    'Extension': [],
                    'Axis': [],
                    'Zone_Percent': [],
                    'Chase_Percent': [],
                    'Whiff_Percent': []}
                        
        #Parse through each pitch type for the pitcher
        for pitch_type in pitcher_data['TaggedPitchType'].unique():
            pitch_type_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
            #If type is defined
            if (pitch_type != 'Undefined'):
                #Add the stats of the pitch type to the report 
                game_report['PitchType'].append(pitch_type)
                game_report['Count'].append(len(pitch_type_data))
                game_report['PitchPercent'].append(len(pitch_type_data) / len(pitcher_data) * 100)
                game_report['Avg_Velocity'].append(pitch_type_data['RelSpeed'].mean())
                game_report['Avg_Ivb'].append(pitch_type_data['InducedVertBreak'].mean())
                game_report['Avg_Hb'].append(pitch_type_data['HorzBreak'].mean())
                game_report['Avg_SpinRate'].append(pitch_type_data['SpinRate'].mean())
                game_report['Avg_Vaa'].append(pitch_type_data['VertApprAngle'].mean())
                game_report['Avg_Haa'].append(pitch_type_data['HorzApprAngle'].mean())
                game_report['Avg_RelHeight'].append(pitch_type_data['RelHeight'].mean())
                game_report['Avg_RelSide'].append(pitch_type_data['RelSide'].mean())
                game_report['Extension'].append(pitch_type_data['Extension'].mean())
                game_report['Axis'].append(pitch_type_data['SpinAxis'].mean()) 
                game_report['Zone_Percent'].append(pitch_type_data['ZoneTime'].mean() * 100)

                chase_count = 0
                for _, row in pitch_type_data.iterrows():
                    outside = (row['PlateLocHeight'] < 1.5) or (row['PlateLocHeight'] > 3.5)
                    outside_height = abs(row['PlateLocSide']) > 0.83
                    batter_swung = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay', 'HitByPitch']
                    
                    if (outside or outside_height) and batter_swung:
                        chase_count += 1
                        
                game_report['Chase_Percent'].append(chase_count / len(pitch_type_data) * 100.00)
                
                whiff_count = 0
                for _, row in pitch_type_data.iterrows():
                    swing_and_miss = row['PitchCall'] in ['StrikeSwinging', 'FoulBallNotFieldable']
                    
                    if swing_and_miss:
                        whiff_count += 1
                
                game_report['Whiff_Percent'].append(whiff_count / len(pitch_type_data) * 100.00)
        
        #Build and print report dataframe
        report_df = pd.DataFrame(game_report)
        report_df.sort_values(by='Count', ascending=False, inplace=True)
        print(pitcher)
        print(report_df)
        print()

def pitch_heat_map(path, pitcher_id, threshold=0.1):
    excel = pd.read_excel(path)
    table = excel[['Pitcher', 'PitcherId', 'TaggedPitchType', 'PlateLocHeight', 'PlateLocSide']] 
    pitcher_data = table[table['PitcherId'] == pitcher_id]
    
    # Get unique pitch types
    pitch_types = pitcher_data['TaggedPitchType'].unique()
    pitch_types = [pt for pt in pitch_types if pt != 'Undefined']
    
    plt.figure(figsize=(10, 8))
    
    # Plot each pitch type on the same plot
    for pitch_type in pitch_types:
        pitch_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
        cmap = pitch_colors.get(pitch_type, 'viridis')
        
        # Check if pitches are clustered closely enough
        # Calculate the standard deviation of horizontal and vertical spread
        side_std = pitch_data['PlateLocSide'].std()
        height_std = pitch_data['PlateLocHeight'].std()
        clustering_metric = (side_std + height_std) / 2
        
        # Adjust bandwidth for better smoothing with sparse data
        bw_adjust = 1.5 if len(pitch_data) < 20 else 1.0
        
        # Create heatmap with threshold and pitch-type-specific color
        if (len(pitch_data) >= 5):
            sns.kdeplot(
                x=pitch_data['PlateLocSide'],
                y=pitch_data['PlateLocHeight'],
                fill=True,
                thresh=threshold,
                levels=[threshold, 1],
                cmap=cmap,
                alpha=0.6,
                bw_adjust=bw_adjust
            )
        
        # Plot individual points
        point_color = pitch_point_colors.get(pitch_type, '#000000')
        '''plt.scatter(
            pitch_data['PlateLocSide'],
            pitch_data['PlateLocHeight'],
            color=point_color,
            alpha=0.5,
            s=30,
            edgecolors='black',
            linewidth=0.5,
            label=f'{pitch_type} (n={len(pitch_data)})'
        )'''

        # Plot average pitch location for pitich type
        avg_side = pitch_data['PlateLocSide'].mean()
        avg_height = pitch_data['PlateLocHeight'].mean()
        plt.scatter(
            avg_side, 
            avg_height,
            color=point_color,
            marker='.',
            s=100,
            label=f'{pitch_type} Avg: {len(pitch_data)} pitches'
        )
    
    # Draw strike zone
    rect = patches.Rectangle(
        (-0.83, 1.5), 
        1.66, 2.0, 
        linewidth=1, 
        edgecolor='black', 
        facecolor='none'
    )
    plt.gca().add_patch(rect)

    plt.title(f'Pitch Location Heat Map for Pitcher ID: {pitcher_id}')
    plt.xlabel('Plate Location Side (ft)')
    plt.ylabel('Plate Location Height (ft)')
    plt.xlim(-6, 6)
    plt.ylim(-5, 10)
    plt.gca().set_aspect('equal', adjustable='box')
    
    # Add legend for scatter points without duplicates
    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    plt.legend(by_label.values(), by_label.keys(), loc='upper right')

    plt.show()
    
def pitch_heat_map_by_batter_side(path, pitcher_id, threshold=0.1):
    excel = pd.read_excel(path)
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
                
                sns.kdeplot(
                    x=pitch_data['PlateLocSide'],
                    y=pitch_data['PlateLocHeight'],
                    fill=True,
                    thresh=threshold,
                    levels=[threshold, 1],
                    cmap=cmap,
                    alpha=0.6,
                    bw_adjust=bw_adjust,
                    ax=ax
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
        ax.set_title(f'vs {batter_side}-Handed Batters (n={len(batter_data)})', fontsize=14, fontweight='bold')
        ax.set_xlabel('Plate Location Side (ft)', fontsize=12)
        ax.set_ylabel('Plate Location Height (ft)', fontsize=12)
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
        ax.legend(by_label.values(), by_label.keys(), loc='upper right')
    
    # Overall title
    fig.suptitle(f'Pitch Location Heat Map for Pitcher ID: {pitcher_id}', 
                fontsize=16, fontweight='bold', y=0.98)
    
    plt.tight_layout()
    plt.show()

build_report("app/input/MSU CSV 1.xlsx")
# Parse through each pitcher in the input file and generate heat maps
excel = pd.read_excel('app/input/MSU CSV 1.xlsx')
table = excel[['PitcherId']]
for pitcherid in table['PitcherId'].unique():
    pitcher_data = table[table['PitcherId'] == pitcherid]
    #pitch_heat_map("app/input/MSU CSV 1.xlsx", pitcherid, threshold=0.75)
    pitch_heat_map_by_batter_side("app/input/MSU CSV 1.xlsx", pitcherid, threshold=0.75)