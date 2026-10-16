"""add user newsletter opt-in

Revision ID: f6c2d4b01e35
Revises: e5b1c3a98d24
Create Date: 2026-10-15 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6c2d4b01e35'
down_revision = 'e5b1c3a98d24'
branch_labels = None
depends_on = None


def upgrade():
    # Everyone starts opted out; server_default is dropped so the model default governs new rows.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('newsletter_opt_in', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('newsletter_last_sent', sa.String(length=50), nullable=True))

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.alter_column('newsletter_opt_in', server_default=None)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('newsletter_last_sent')
        batch_op.drop_column('newsletter_opt_in')
