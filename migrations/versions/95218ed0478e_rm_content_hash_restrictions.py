"""rm content_hash restrictions

Revision ID: 95218ed0478e
Revises: c1f77aa52f5c
Create Date: 2026-05-29 00:04:31.061638

"""
from alembic import op
import sqlalchemy as sa


revision = '95218ed0478e'
down_revision = 'c1f77aa52f5c'
branch_labels = None
depends_on = None


def upgrade():
    # Clear existing pitch stats — outing_id cannot be backfilled
    op.execute('DELETE FROM outing_pitch_stats')

    # Drop FK from outing_pitch_stats.outing_content_hash -> outings.content_hash
    op.drop_constraint('outing_pitch_stats_outing_content_hash_fkey', 'outing_pitch_stats', type_='foreignkey')

    # Drop unique constraint on outings.content_hash (multiple pitchers share a game file)
    op.drop_constraint('uq_outings_content_hash', 'outings', type_='unique')

    # Replace outing_content_hash with outing_id FK to outings.id
    op.drop_column('outing_pitch_stats', 'outing_content_hash')
    op.add_column('outing_pitch_stats', sa.Column('outing_id', sa.Integer(), nullable=False))
    op.create_foreign_key('outing_pitch_stats_outing_id_fkey', 'outing_pitch_stats', 'outings', ['outing_id'], ['id'])


def downgrade():
    op.drop_constraint('outing_pitch_stats_outing_id_fkey', 'outing_pitch_stats', type_='foreignkey')
    op.drop_column('outing_pitch_stats', 'outing_id')
    op.add_column('outing_pitch_stats', sa.Column('outing_content_hash', sa.String(length=200), nullable=False))
    op.create_foreign_key('outing_pitch_stats_outing_content_hash_fkey', 'outing_pitch_stats', 'outings', ['outing_content_hash'], ['content_hash'])
    op.create_unique_constraint('uq_outings_content_hash', 'outings', ['content_hash'])
