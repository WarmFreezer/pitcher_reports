"""add user ink_mode preference

Revision ID: ad49bae9d0c2
Revises: 7868a8c01cfe
Create Date: 2026-09-09 21:43:58.069860

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ad49bae9d0c2'
down_revision = '7868a8c01cfe'
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills existing rows (Postgres rejects a NOT NULL add
    # without one); dropped after so the Python-side model default is what
    # governs new rows going forward, matching chart_style's own migration.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ink_mode', sa.String(length=20), nullable=False, server_default='full_color'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('ink_mode', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('ink_mode')
