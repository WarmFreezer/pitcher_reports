"""initial schema

Revision ID: c1f77aa52f5c
Revises:
Create Date: 2026-05-28 23:29:04.959762

"""
from alembic import op
import sqlalchemy as sa


revision = 'c1f77aa52f5c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('pitchers',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('school_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('trackman_id', sa.String(length=20), nullable=True),
    sa.Column('birthdate', sa.Date(), nullable=True),
    sa.Column('height', sa.String(length=10), nullable=True),
    sa.Column('weight', sa.String(length=10), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['school_id'], ['schools.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('trackman_id')
    )

    op.create_table('pitch_types',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=50), nullable=False),
    sa.Column('abbreviation', sa.String(length=10), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name'),
    sa.UniqueConstraint('abbreviation')
    )

    op.create_table('outings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('content_hash', sa.String(length=200), nullable=True),
    sa.Column('pitcher_id', sa.Integer(), nullable=False),
    sa.Column('date', sa.String(length=20), nullable=False),
    sa.Column('opponent', sa.String(length=100), nullable=True),
    sa.Column('is_home', sa.Boolean(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('pitch_count', sa.Integer(), nullable=True),
    sa.Column('lo_inning_count', sa.Float(), nullable=True),
    sa.Column('lo_reach', sa.Float(), nullable=True),
    sa.Column('lo_obp', sa.Float(), nullable=True),
    sa.Column('lo_bb_count', sa.Float(), nullable=True),
    sa.Column('lo_bb_percentage', sa.Float(), nullable=True),
    sa.Column('two_out_ab_count', sa.Float(), nullable=True),
    sa.Column('two_out_reach', sa.Float(), nullable=True),
    sa.Column('two_out_eff_percentage', sa.Float(), nullable=True),
    sa.Column('two_out_bb_count', sa.Float(), nullable=True),
    sa.Column('two_out_bb_percentage', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('content_hash', name='uq_outings_content_hash')
    )

    op.create_table('outing_pitch_stats',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('pitcher_id', sa.Integer(), nullable=False),
    sa.Column('outing_content_hash', sa.String(length=200), nullable=False),
    sa.Column('pitch_type_id', sa.Integer(), nullable=False),
    sa.Column('count', sa.Float(), nullable=True),
    sa.Column('percentage', sa.Float(), nullable=True),
    sa.Column('strike_count', sa.Float(), nullable=True),
    sa.Column('strike_percentage', sa.Float(), nullable=True),
    sa.Column('sw_percentage', sa.Float(), nullable=True),
    sa.Column('sw_miss_count', sa.Float(), nullable=True),
    sa.Column('sw_miss_percentage', sa.Float(), nullable=True),
    sa.Column('ip_count', sa.Float(), nullable=True),
    sa.Column('low_quartile_speed', sa.Float(), nullable=True),
    sa.Column('median_speed', sa.Float(), nullable=True),
    sa.Column('high_quartile_speed', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['outing_content_hash'], ['outings.content_hash'], ),
    sa.ForeignKeyConstraint(['pitch_type_id'], ['pitch_types.id'], ),
    sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('outing_pitch_stats')
    op.drop_table('outings')
    op.drop_table('pitch_types')
    op.drop_table('pitchers')