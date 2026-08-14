from datetime import date, datetime
from typing import TYPE_CHECKING

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

# db.Model is built dynamically inside SQLAlchemy.__init__ (it mixes Base with
# Flask-SQLAlchemy's own Model/BindMixin/NameMixin, which is what gives us the
# legacy `.query` attribute used throughout this codebase), so mypy has no
# static type for it. Models below inherit from db.Model at runtime; for
# type-checking, stand in a Base+Model combination so Mapped[] columns and
# `.query` both resolve.
if TYPE_CHECKING:
    from flask_sqlalchemy.model import Model as _FSAModel

    class BaseModel(Base, _FSAModel):
        pass
else:
    BaseModel = db.Model


class School(BaseModel):
    """A subscribing school/program — the top-level tenant every other table is scoped to."""
    __tablename__ = 'schools'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(100))
    slug: Mapped[str] = mapped_column(db.String(50))
    created_at: Mapped[datetime | None] = mapped_column(default=datetime.now)
    admin_email: Mapped[str] = mapped_column(db.String(100), unique=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(db.String(100), unique=True)
    stripe_subscription_status: Mapped[str | None] = mapped_column(db.String(20), default='inactive')
    trackman_id: Mapped[str | None] = mapped_column(db.String(20), unique=True)

    users = db.relationship('User', backref='school', lazy=True)

    players = db.relationship('Pitcher', backref='school', lazy=True)

    @property
    def branding_path(self) -> str:
        """Repo-relative path to this school's branding.json."""
        return f'storage/schools/{self.id}/assets/branding.json'

    @property
    def is_active(self) -> bool:
        """Whether the school's Stripe subscription currently grants access."""
        return self.stripe_subscription_status in ('active', 'trialing')


class User(UserMixin, BaseModel):
    """A login for a school — students/coaches viewing reports, or the school admin."""
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(db.String(120), unique=True)
    password_hash: Mapped[str] = mapped_column(db.String(128))
    first_name: Mapped[str] = mapped_column(db.String(50))
    last_name: Mapped[str] = mapped_column(db.String(50))
    school_id: Mapped[int] = mapped_column(db.ForeignKey('schools.id'))
    role: Mapped[str] = mapped_column(db.String(20), default='student')
    is_active: Mapped[bool | None] = mapped_column(default=True)
    created_at: Mapped[datetime | None] = mapped_column(default=db.func.current_timestamp())


class Pitcher(BaseModel):
    """A pitcher on a school's roster, identified by TrackMan's own id."""
    __tablename__ = 'pitchers'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    school_id: Mapped[int] = mapped_column(db.ForeignKey('schools.id'))
    name: Mapped[str] = mapped_column(db.String(100))
    trackman_id: Mapped[str | None] = mapped_column(db.String(20), unique=True)
    birthdate: Mapped[date | None] = mapped_column(db.Date)
    height: Mapped[str | None] = mapped_column(db.String(10))
    weight: Mapped[str | None] = mapped_column(db.String(10))
    created_at: Mapped[datetime | None] = mapped_column(default=db.func.current_timestamp())


class Outing(BaseModel):
    """A single game appearance for a pitcher, plus situational stats computed at save time."""
    __tablename__ = 'outings'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    content_hash: Mapped[str | None] = mapped_column(db.String(200))
    pitcher_id: Mapped[int] = mapped_column(db.ForeignKey('pitchers.id'))
    date: Mapped[str] = mapped_column(db.String(20))
    opponent: Mapped[str | None] = mapped_column(db.String(100))
    is_home: Mapped[bool | None] = mapped_column(default=True)
    notes: Mapped[str | None] = mapped_column(db.Text)
    created_at: Mapped[datetime | None] = mapped_column(default=db.func.current_timestamp())

    pitch_count: Mapped[int | None] = mapped_column(db.Integer)

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
    lo_inning_count: Mapped[float | None] = mapped_column(db.Float)
    lo_reach: Mapped[float | None] = mapped_column(db.Float)
    lo_obp: Mapped[float | None] = mapped_column(db.Float)
    lo_bb_count: Mapped[float | None] = mapped_column(db.Float)
    lo_bb_percentage: Mapped[float | None] = mapped_column(db.Float)
    two_out_ab_count: Mapped[float | None] = mapped_column(db.Float)
    two_out_reach: Mapped[float | None] = mapped_column(db.Float)
    two_out_eff_percentage: Mapped[float | None] = mapped_column(db.Float)
    two_out_bb_count: Mapped[float | None] = mapped_column(db.Float)
    two_out_bb_percentage: Mapped[float | None] = mapped_column(db.Float)


class Pitch_Types(BaseModel):
    """Lookup table mapping a TrackMan pitch type name to its report abbreviation."""
    __tablename__ = 'pitch_types'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True)
    abbreviation: Mapped[str] = mapped_column(db.String(10), unique=True)


class Outing_Pitch_Stat(BaseModel):
    """Per-pitch-type aggregated stats for one outing, persisted for season totals."""
    __tablename__ = 'outing_pitch_stats'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pitcher_id: Mapped[int] = mapped_column(db.ForeignKey('pitchers.id'))
    outing_id: Mapped[int] = mapped_column(db.ForeignKey('outings.id'))
    pitch_type_id: Mapped[int] = mapped_column(db.ForeignKey('pitch_types.id'))

    count: Mapped[float | None] = mapped_column(db.Float)
    percentage: Mapped[float | None] = mapped_column(db.Float)
    strike_count: Mapped[float | None] = mapped_column(db.Float)
    strike_percentage: Mapped[float | None] = mapped_column(db.Float)
    sw_percentage: Mapped[float | None] = mapped_column(db.Float)
    sw_miss_count: Mapped[float | None] = mapped_column(db.Float)
    sw_miss_percentage: Mapped[float | None] = mapped_column(db.Float)

    low_quartile_speed: Mapped[float | None] = mapped_column(db.Float)
    median_speed: Mapped[float | None] = mapped_column(db.Float)
    high_quartile_speed: Mapped[float | None] = mapped_column(db.Float)

    # Hits and Babip may be batting stats
