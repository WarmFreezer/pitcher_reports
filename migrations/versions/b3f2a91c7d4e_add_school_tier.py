"""add school tier

Revision ID: b3f2a91c7d4e
Revises: ad49bae9d0c2
Create Date: 2026-09-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3f2a91c7d4e'
down_revision = 'ad49bae9d0c2'
branch_labels = None
depends_on = None


def upgrade():
    # server_default backfills every existing school to Tier 2 so nobody already
    # subscribed silently loses chart access; dropped after so the Python-side
    # model default is what governs new rows, matching ink_mode's own migration.
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tier', sa.Integer(), nullable=False, server_default='2'))

    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.alter_column('tier', server_default=None)


def downgrade():
    with op.batch_alter_table('schools', schema=None) as batch_op:
        batch_op.drop_column('tier')
