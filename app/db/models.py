from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class School(db.Model):
    __tablename__ = 'schools'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    admin_email = db.Column(db.String(100), unique=True, nullable=False)
    stripe_customer_id = db.Column(db.String(100), unique=True, nullable=True)
    stripe_subscription_id = db.Column(db.String(100), unique=True, nullable=True)
    stripe_subscription_status = db.Column(db.String(20), default='inactive')
    trackman_id = db.Column(db.String(20), unique=True, nullable=True)

    users = db.relationship('User', backref='school', lazy=True)

    players = db.relationship('Pitcher', backref='school', lazy=True)

    @property
    def branding_path(self):
        return f'storage/schools/{self.slug}/assets/branding.json'

    @property
    def is_active(self):
        return self.stripe_subscription_status in ('active', 'trialing')
    
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(120), unique=True, nullable=False) 
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    
class Pitcher(db.Model):
    __tablename__ = 'pitchers'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    trackman_id = db.Column(db.String(20), unique=True, nullable=True)
    birthdate = db.Column(db.Date, nullable=True)
    height = db.Column(db.String(10), nullable=True)
    weight = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class Outing(db.Model):
    __tablename__ = 'outings'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    content_hash = db.Column(db.String(200), nullable=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    opponent = db.Column(db.String(100), nullable=True)
    is_home = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    pitch_count = db.Column(db.Integer, nullable=True)

    '''
    ip = db.Column(db.Float, nullable=True)
    tbf = db.Column(db.Float, nullable=True)
    ab = db.Column(db.Float, nullable=True)
    h = db.Column(db.Float, nullable=True)
    bb = db.Column(db.Float, nullable=True)
    hbp = db.Column(db.Float, nullable=True)
    k = db.Column(db.Float, nullable=True)
    hr = db.Column(db.Float, nullable=True)
    sf = db.Column(db.Float, nullable=True)
    runs = db.Column(db.Float, nullable=True)
    earned_runs = db.Column(db.Float, nullable=True)
    fip = db.Column(db.Float, nullable=True)
    babip = db.Column(db.Float, nullable=True)
    two_of_three_strikes_percentage = db.Column(db.Float, nullable=True)
    total_pitches = db.Column(db.Float, nullable=True)
    total_strikes = db.Column(db.Float, nullable=True)
    k_percentage = db.Column(db.Float, nullable=True)
    p_over_ab = db.Column(db.Float, nullable=True)
    fst_pitch_strike_count = db.Column(db.Float, nullable=True)
    fst_pitch_strike_percentage = db.Column(db.Float, nullable=True)
    '''
    lo_inning_count = db.Column(db.Float, nullable=True)
    lo_reach = db.Column(db.Float, nullable=True)
    lo_obp = db.Column(db.Float, nullable=True)
    lo_bb_count = db.Column(db.Float, nullable=True)
    lo_bb_percentage = db.Column(db.Float, nullable=True)
    two_out_ab_count = db.Column(db.Float, nullable=True)
    two_out_reach = db.Column(db.Float, nullable=True)
    two_out_eff_percentage = db.Column(db.Float, nullable=True)
    two_out_bb_count = db.Column(db.Float, nullable=True)
    two_out_bb_percentage = db.Column(db.Float, nullable=True)
    

class Pitch_Types(db.Model):
    __tablename__ = 'pitch_types'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    abbreviation = db.Column(db.String(10), unique=True, nullable=False)

class Outing_Pitch_Stat(db.Model):
    __tablename__ = 'outing_pitch_stats'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    outing_id = db.Column(db.Integer, db.ForeignKey('outings.id'), nullable=False)
    pitch_type_id = db.Column(db.Integer, db.ForeignKey('pitch_types.id'), nullable=False)

    count = db.Column(db.Float, nullable=True)
    percentage = db.Column(db.Float, nullable=True)
    strike_count = db.Column(db.Float, nullable=True)
    strike_percentage = db.Column(db.Float, nullable=True)
    sw_percentage = db.Column(db.Float, nullable=True)
    sw_miss_count = db.Column(db.Float, nullable=True)
    sw_miss_percentage = db.Column(db.Float, nullable=True)
    
    low_quartile_speed = db.Column(db.Float, nullable=True)
    median_speed = db.Column(db.Float, nullable=True)
    high_quartile_speed = db.Column(db.Float, nullable=True)

    # Hits and Babip may be batting stats
