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

from app.db.models import db
from app.db import models

STRIKES  =  ['StrikeCalled', 'StrikeSwinging', 'FoulBallNotFieldable']
SWINGS  =  ['StrikeSwinging', 'FoulBallNotFieldable', 'InPlay']

def _native(val):
    return val.item() if hasattr(val, 'item') else val

def hash_file(file) -> str:
    file.seek(0)  # Ensure we're at the start of the file
    h = hashlib.md5(file.read()).hexdigest()[:128]
    file.seek(0)  # Reset file pointer after reading
    return h

def add_pitcher(school_id, trackman_id, name):
    trackman_id = str(trackman_id)
    pitcher = models.Pitcher.query.filter_by(trackman_id=trackman_id, school_id=school_id).first()
    if not pitcher:
        pitcher = models.Pitcher(school_id=school_id, trackman_id=trackman_id, name=name)
        db.session.add(pitcher)
        db.session.flush()
    return pitcher.id

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
    return new_outing.id

def update_outing(outing_id, **kwargs):
    outing = models.Outing.query.get(outing_id)
    if outing:
        for key, value in kwargs.items():
            if hasattr(outing, key):
                setattr(outing, key, value)
        db.session.commit()

def add_outing_pitch_stats(pitcher_id, outing_id, source):
    pitch_type_map = {pt.name: pt.id for pt in models.Pitch_Types.query.all()}
    undefined_id = pitch_type_map.get('Undefined', None)

    for pitch_type in source['TaggedPitchType'].unique():
        pitch_data  =  source[source['TaggedPitchType'] == pitch_type]

        count =  pitch_data.shape[0]

        low_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.25)
        median_speed  =  pitch_data['RelSpeed'].quantile(0.5)
        high_quartile_speed  =  pitch_data['RelSpeed'].quantile(0.75)

        pitch_type_id = pitch_type_map.get(pitch_type, undefined_id)
        if pitch_type_id is None:
            print(f"Skipping unknown pitch type: {pitch_type}")
            continue

        new_stat  =  models.Outing_Pitch_Stat(
            pitcher_id = pitcher_id,
            outing_id = outing_id,
            pitch_type_id = pitch_type_id,
            count = _native(count),
            percentage = _native(count/source.shape[0]*100),
            strike_count = _native(pitch_data['PitchCall'].isin(STRIKES).sum()),
            strike_percentage = _native(pitch_data['PitchCall'].isin(STRIKES).sum()/count*100),
            sw_percentage = _native(pitch_data['PitchCall'].isin(SWINGS).sum()/count*100),
            sw_miss_count = _native((pitch_data['PitchCall'] == 'StrikeSwinging').sum()),
            sw_miss_percentage = _native((pitch_data['PitchCall'] == 'StrikeSwinging').sum()/count*100),
            ip_count = 0,
            low_quartile_speed = _native(low_quartile_speed),
            median_speed = _native(median_speed),
            high_quartile_speed = _native(high_quartile_speed)
        )
        db.session.add(new_stat)
    db.session.flush()

def update_outing_pitch_stats(pitcher_id, outing_id, source):
    models.Outing_Pitch_Stat.query.filter_by(outing_id=outing_id).delete()
    db.session.flush()
    add_outing_pitch_stats(pitcher_id, outing_id, source)
    db.session.commit()

def add_report(school_id, trackman_id, file):
    content_hash = hash_file(file)
    filepath = file.name
    if filepath.endswith(('.xlsx', '.xls')):
        source = pd.read_excel(filepath)
    else:
        source = pd.read_csv(filepath)

    if not models.Outing.query.filter_by(content_hash = content_hash).first():
        team_data = source[source['PitcherTeam'] == trackman_id]
        for trackman_pitcher_id in team_data['PitcherId'].unique():
            pitcher_data = team_data[team_data['PitcherId'] == trackman_pitcher_id]

            db_pitcher_id = add_pitcher(school_id, trackman_pitcher_id, pitcher_data['Pitcher'].iloc[0])
            outing_id = add_outing(
                db_pitcher_id,
                pd.to_datetime(pitcher_data['Date'].mode().iloc[0]).date(),
                content_hash,
                (trackman_id == pitcher_data['HomeTeam'].iloc[0]),
                pitcher_data.shape[0],
                pitcher_data)
            add_outing_pitch_stats(
                db_pitcher_id,
                outing_id,
                pitcher_data)

            db.session.commit()
    else: 
        print("Report with this content hash already exists. No new data added.")

def remove_report(content_hash):
    outings = models.Outing.query.filter_by(content_hash=content_hash).all()
    for outing in outings:
        models.Outing_Pitch_Stat.query.filter_by(outing_id=outing.id).delete()
        db.session.delete(outing)
    if outings:
        db.session.commit()

