import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import os

#venv/Scripts/activate

path = os.path.abspath(os.path.dirname(__file__))

for filename in os.listdir(path + '/app/input'):
    excel = pd.read_excel(path + '/app/input/' + filename)
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
                    outside_height = abs(row['PlateLocSide']) > 0.708
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