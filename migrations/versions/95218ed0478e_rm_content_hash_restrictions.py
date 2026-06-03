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
    import sqlalchemy as sa_inspect
    bind = op.get_bind()
    inspector = sa_inspect.inspect(bind)

    # Drop unique constraint on outings.content_hash (skip if not present — SQLite may not store it by name)
    outings_constraints = {c['name'] for c in inspector.get_unique_constraints('outings')}
    if 'uq_outings_content_hash' in outings_constraints:
        with op.batch_alter_table('outings') as batch_op:
            batch_op.drop_constraint('uq_outings_content_hash', type_='unique')

    # Clear existing pitch stats — outing_id cannot be backfilled
    op.execute('DELETE FROM outing_pitch_stats')

    # Swap outing_content_hash for outing_id FK
    pitch_stat_cols = {c['name'] for c in inspector.get_columns('outing_pitch_stats')}
    with op.batch_alter_table('outing_pitch_stats') as batch_op:
        if 'outing_content_hash' in pitch_stat_cols:
            batch_op.drop_column('outing_content_hash')
        if 'outing_id' not in pitch_stat_cols:
            batch_op.add_column(sa.Column('outing_id', sa.Integer(), nullable=False))
            batch_op.create_foreign_key('outing_pitch_stats_outing_id_fkey', 'outings', ['outing_id'], ['id'])


def downgrade():
    with op.batch_alter_table('outing_pitch_stats') as batch_op:
        batch_op.drop_column('outing_id')
        batch_op.add_column(sa.Column('outing_content_hash', sa.String(length=200), nullable=False))

    with op.batch_alter_table('outings') as batch_op:
        batch_op.create_unique_constraint('uq_outings_content_hash', ['content_hash'])
