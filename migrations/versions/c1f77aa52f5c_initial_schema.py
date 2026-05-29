"""initial schema

Revision ID: c1f77aa52f5c
Revises:
Create Date: 2026-05-28 23:29:04.959762

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1f77aa52f5c'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # outings.content_hash must be unique for outing_pitch_stats FK to work on PostgreSQL
    op.create_unique_constraint('uq_outings_content_hash', 'outings', ['content_hash'])

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
    op.drop_constraint('uq_outings_content_hash', 'outings', type_='unique')
