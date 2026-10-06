"""add user chart_color_mode preference

Revision ID: d4a8e2f61b07
Revises: 2a682c0df1e8
Create Date: 2026-10-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a8e2f61b07'
down_revision = '2a682c0df1e8'
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills existing rows (Postgres rejects a NOT NULL add
    # without one); dropped after so the Python-side model default is what
    # governs new rows going forward, matching chart_style/ink_mode's own migrations.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('chart_color_mode', sa.String(length=20), nullable=False, server_default='pitch_type'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('chart_color_mode', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('chart_color_mode')
