"""drop schools.slug unique constraint

Revision ID: 7fa9fe631f29
Revises: 95218ed0478e
Create Date: 2026-08-14 00:30:22.178456

`schools.slug` was never captured by an earlier Alembic revision — the
`schools` table has only ever been created via `db.create_all()`. This
revision drops its unique constraint now that internal code (storage paths,
Stripe webhook lookups, CLI school resolution) has been migrated to key off
`school.id` instead of `slug`. See docs/test-plan-slug-migration.md.
"""
from alembic import op
import sqlalchemy as sa


revision = '7fa9fe631f29'
down_revision = '95218ed0478e'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    slug_constraints = [
        c for c in inspector.get_unique_constraints('schools')
        if c.get('column_names') == ['slug']
    ]
    if not slug_constraints:
        return

    if bind.dialect.name == 'sqlite':
        # SQLite never assigns a name to an inline UNIQUE(column) constraint
        # (reflection reports name=None), so batch mode's table-recreate
        # strategy has nothing to target by name unless we give it one via
        # naming_convention.
        naming_convention = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}
        with op.batch_alter_table('schools', naming_convention=naming_convention) as batch_op:
            batch_op.drop_constraint('uq_schools_slug', type_='unique')
    else:
        # Postgres (and other dialects that name constraints on creation)
        # report a real name via reflection — drop it directly.
        with op.batch_alter_table('schools') as batch_op:
            for c in slug_constraints:
                if c.get('name'):
                    batch_op.drop_constraint(c['name'], type_='unique')


def downgrade():
    with op.batch_alter_table('schools') as batch_op:
        batch_op.create_unique_constraint('uq_schools_slug', ['slug'])
