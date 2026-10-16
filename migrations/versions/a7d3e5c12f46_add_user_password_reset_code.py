"""add user password reset code

Revision ID: a7d3e5c12f46
Revises: f6c2d4b01e35
Create Date: 2026-10-16 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7d3e5c12f46'
down_revision = 'f6c2d4b01e35'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reset_code_hash', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('reset_code_expires', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reset_attempts', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('reset_attempts', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('reset_attempts')
        batch_op.drop_column('reset_code_expires')
        batch_op.drop_column('reset_code_hash')
