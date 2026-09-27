"""add user show break arrows preference

Revision ID: 2a682c0df1e8
Revises: c7e19a4f6b2d
Create Date: 2026-09-26 19:02:55.476627

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '2a682c0df1e8'
down_revision = 'c7e19a4f6b2d'
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills existing rows (Postgres rejects a NOT NULL add
    # without one); dropped after so the Python-side model default is what
    # governs new rows going forward, matching chart_style/ink_mode's own migrations.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('show_break_arrows', sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('show_break_arrows', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('show_break_arrows')
