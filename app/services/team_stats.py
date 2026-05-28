'''
BY: Thomas Eubank 

This module contains functions for processing and analyzing team statistics, 
including adding and updating pitcher and outing information, as well as generating 
reports based on the collected data. It interacts with the database models to store 
and retrieve relevant information about pitchers, outings, and pitch statistics.

Notes: "source" refers to the dataframe filtered by pitcher and team, "file" is the 
raw Trackman report file.

Last Updated: 2024-05-26 (Thomas Eubank)

'''

import numpy as np
import pandas as pd
import hashlib

from app.db import db, models

STRIKES  =  ['StrikeCalled', 'StrikeSwinging', 'FoulBallNotFieldable']
SWINGS  =  ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay']

def hash_file(file) -> str:
    file.seek(0)  # Ensure we're at the start of the file
    h = hashlib.md5(file.read()).hexdigest()[:128]
    file.seek(0)  # Reset file pointer after reading
    return h

def add_pitcher(school_id, trackman_id, name):
    new_pitcher  =  models.Pitcher(school_id = school_id, trackman_id = trackman_id, name = name)
    db.session.add(new_pitcher)
    db.session.flush()

def update_pitcher(pitcher_id, **kwargs):
    pitcher = models.Pitcher.query.get(pitcher_id)
    if pitcher:
        for key, value in kwargs.items():
            if hasattr(pitcher, key):
                setattr(pitcher, key, value)
        db.session.commit()

def add_outing(pitcher_id, date, content_hash, is_home, pitch_count, source):
    new_outing  =  models.Outing(
        pitcher_id = pitcher_id, 
        date = date, 
        content_hash = content_hash, 
        is_home = is_home, 
        pitch_count = pitch_count, 
        opponent = source['BatterTeam'].mode().iloc[0],
        
        lo_inning_count = 0,
        lo_reach = 0,
        lo_obp = 0,
        lo_bb_count = 0,
        lo_bb_percentage = 0,
        
        two_out_ab_count = 0,
        two_out_reach = 0,
        two_out_eff_percentage = 0,
        two_out_bb_count = 0,
        two_out_bb_percentage = 0)
    db.session.add(new_outing)
    db.session.flush()

    #TODO: add stats to outing table

def update_outing(outing_id, **kwargs):
    outing = models.Outing.query.get(outing_id)
    if outing:
        for key, value in kwargs.items():
            if hasattr(outing, key):
                setattr(outing, key, value)
        db.session.commit()

def add_outing_pitch_stats(pitcher_id, outing_id, source):
    source  =  source[source['PitcherId'] == pitcher_id]
    pitch_type_map = {pt.name: pt.id for pt in models.Pitch_Types.query.all()}
    undefined_id = pitch_type_map.get('Undefined', None)

    for pitch_type in source['TaggedPitchType'].unique():
        pitch_data  =  source[source['TaggedPitchType'] == pitch_type]

        count =  pitch_data.shape[0]

        low_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.25)
        median_speed  =  pitch_data['RelSpeed'].quantile(0.5)
        high_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.75)

        pitch_type_id = pitch_type_map.get(pitch_type, undefined_id)

        new_stat  =  models.Outing_Pitch_Stat(
            pitcher_id = pitcher_id, 
            outing_id = outing_id, 
            pitch_type_id = pitch_type_id,
            count = count,
            percentage = count/source.shape[0]*100,
            strike_count = pitch_data['PitchCall'].isin(STRIKES).sum(),
            strike_percentage = pitch_data['PitchCall'].isin(STRIKES).sum()/count*100,
            sw_percentage = pitch_data['PitchCall'].isin(SWINGS).sum()/count*100,
            sw_miss_count = (pitch_data['PitchCall'] == 'StrikeSwinging').sum(),
            sw_miss_percentage = (pitch_data['PitchCall'] == 'StrikeSwinging').sum()/count*100,
            ip_count = 0, #TODO
            low_quartile_speed = low_quartile_speed,
            median_speed = median_speed,
            high_quartile_speed = high_quartile_speed
        )
        db.session.add(new_stat)
    db.session.flush()

def update_outing_pitch_stats(pitcher_id, outing_id, source):
    source  =  source[source['PitcherId'] == pitcher_id]
    pitch_type_map = {pt.name: pt.id for pt in models.Pitch_Types.query.all()}
    undefined_id = pitch_type_map.get('Undefined', None)

    for pitch_type in source['TaggedPitchType'].unique():
        pitch_data  =  source[source['TaggedPitchType'] == pitch_type]

        count =  pitch_data.shape[0]

        low_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.25)
        median_speed  =  pitch_data['RelSpeed'].quantile(0.5)
        high_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.75)

        pitch_type_id = pitch_type_map.get(pitch_type, undefined_id)

        stat = models.Outing_Pitch_Stat.query.filter_by(
            pitcher_id = pitcher_id, 
            outing_id = outing_id, 
            pitch_type_id = pitch_type_id
        ).first()

        if stat:
            stat.count = count
            stat.percentage = count/source.shape[0]*100
            stat.strike_count = pitch_data['PitchCall'].isin(STRIKES).sum()
            stat.strike_percentage = pitch_data['PitchCall'].isin(STRIKES).sum()/count*100
            stat.sw_percentage = pitch_data['PitchCall'].isin(SWINGS).sum()/count*100
            stat.sw_miss_count = (pitch_data['PitchCall'] == 'StrikeSwinging').sum()
            stat.sw_miss_percentage = (pitch_data['PitchCall'] == 'StrikeSwinging').sum()/count*100
            stat.ip_count = 0 #TODO
            stat.low_quartile_speed = low_quartile_speed
            stat.median_speed = median_speed
            stat.high_quartile_speed = high_quartile_speed
    db.session.commit()

def add_report(school_id, trackman_id, file):
    content_hash = hash_file(file)
    source = pd.read_csv(file)
    if not models.Outing.query.filter_by(content_hash = content_hash).first():
        team_data = source[source['PitcherTeam'] == trackman_id]
        for pitcher_id in team_data['PitcherId'].unique():
            pitcher_data = team_data[team_data['PitcherId'] == pitcher_id]
            
            add_pitcher(school_id, pitcher_id, pitcher_data['Pitcher'].iloc[0])
            add_outing(
                pitcher_id, 
                pitcher_data['Date'].mode().iloc[0], 
                content_hash, 
                (trackman_id == pitcher_data['HomeTeam'].iloc[0]), 
                pitcher_data.shape[0],
                pitcher_data)
            outing_id = models.Outing.query.filter_by(pitcher_id = pitcher_id, date = pitcher_data['Date'].mode().iloc[0]).first().id
            add_outing_pitch_stats(
                pitcher_id, 
                outing_id, 
                pitcher_data)

            db.session.commit()
    else: 
        print("Report with this content hash already exists. No new data added.")
