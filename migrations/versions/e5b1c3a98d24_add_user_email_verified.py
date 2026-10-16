"""add user email_verified

Revision ID: e5b1c3a98d24
Revises: d4a8e2f61b07
Create Date: 2026-10-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5b1c3a98d24'
down_revision = 'd4a8e2f61b07'
branch_labels = None
depends_on = None


def upgrade():
    # Existing accounts are grandfathered as verified so no current admin is locked out;
    # the server_default is dropped after so new rows take the model default (False).
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('email_verified', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('email_verified')
