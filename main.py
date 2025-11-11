import numpy as np
import pandas as pd
from matplotlib import pyplot as plt
import seaborn as sns
import os

#venv/Scripts/activate

path = os.path.abspath(os.path.dirname(__file__))

for filename in os.listdir(path + '/app/input'):
    excel = pd.read_excel(path + '/app/input/' + filename)
    table = excel[['Pitcher', 'PitcherId', 'TaggedPitchType', 'EffectiveVelo', 'InducedVertBreak', 'HorzBreak', 'SpinRate', 'VertApprAngle', 'HorzApprAngle', 'RelHeight', 'RelSide']] 

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
                       'Avg_RelSide': []}
                        #Ext.,
                        #Axis

        #Parse through each pitch type for the pitcher
        for pitch_type in pitcher_data['TaggedPitchType'].unique():
            pitch_type_data = pitcher_data[pitcher_data['TaggedPitchType'] == pitch_type]
            #If type is defined
            if (pitch_type != 'Undefined'):
                #Add the stats of the pitch type to the report 
                game_report['PitchType'].append(pitch_type)
                game_report['Count'].append(len(pitch_type_data))
                game_report['PitchPercent'].append(len(pitch_type_data) / len(pitcher_data) * 100)
                game_report['Avg_Velocity'].append(pitch_type_data['EffectiveVelo'].mean())
                game_report['Avg_Ivb'].append(pitch_type_data['InducedVertBreak'].mean())
                game_report['Avg_Hb'].append(pitch_type_data['HorzBreak'].mean())
                game_report['Avg_SpinRate'].append(pitch_type_data['SpinRate'].mean())
                game_report['Avg_Vaa'].append(pitch_type_data['VertApprAngle'].mean())
                game_report['Avg_Haa'].append(pitch_type_data['HorzApprAngle'].mean())
                game_report['Avg_RelHeight'].append(pitch_type_data['RelHeight'].mean())
                game_report['Avg_RelSide'].append(pitch_type_data['RelSide'].mean())
        
        #Build and print report dataframe
        report_df = pd.DataFrame(game_report)
        report_df.sort_values(by='Count', ascending=False, inplace=True)
        print(pitcher)
        print(report_df)
        print()