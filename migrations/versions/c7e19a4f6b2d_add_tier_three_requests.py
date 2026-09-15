"""add tier_three_requests table

Revision ID: c7e19a4f6b2d
Revises: b3f2a91c7d4e
Create Date: 2026-09-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7e19a4f6b2d'
down_revision = 'b3f2a91c7d4e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('tier_three_requests',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('org_name', sa.String(length=100), nullable=False),
    sa.Column('contact_email', sa.String(length=120), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('tier_three_requests')
