"""drop schools trackman_id unique constraint

Revision ID: 323b51a699aa
Revises: 7fa9fe631f29
Create Date: 2026-09-02 18:40:08.591804

`schools.trackman_id` was never captured by an earlier Alembic revision -- the
`schools` table has only ever been created via `db.create_all()`. This
revision drops its unique constraint; nothing in the codebase relies on
trackman_id being globally unique across schools.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '323b51a699aa'
down_revision = '7fa9fe631f29'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    trackman_id_constraints = [
        c for c in inspector.get_unique_constraints('schools')
        if c.get('column_names') == ['trackman_id']
    ]
    if not trackman_id_constraints:
        return

    if bind.dialect.name == 'sqlite':
        # SQLite never assigns a name to an inline UNIQUE(column) constraint
        # (reflection reports name=None), so batch mode's table-recreate
        # strategy has nothing to target by name unless we give it one via
        # naming_convention.
        naming_convention = {'uq': 'uq_%(table_name)s_%(column_0_name)s'}
        with op.batch_alter_table('schools', naming_convention=naming_convention) as batch_op:
            batch_op.drop_constraint('uq_schools_trackman_id', type_='unique')
    else:
        # Postgres (and other dialects that name constraints on creation)
        # report a real name via reflection — drop it directly.
        with op.batch_alter_table('schools') as batch_op:
            for c in trackman_id_constraints:
                if c.get('name'):
                    batch_op.drop_constraint(c['name'], type_='unique')


def downgrade():
    with op.batch_alter_table('schools') as batch_op:
        batch_op.create_unique_constraint('uq_schools_trackman_id', ['trackman_id'])
