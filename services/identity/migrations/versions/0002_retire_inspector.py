"""retire the inspector role: the quality gate was removed (November 2026)

Revision ID: 0002_retire_inspector
Revises: 0001_initial
Create Date: 2026-11-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_retire_inspector"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Someone who was only an inspector keeps an account as a customer.
    op.execute(
        """
        INSERT INTO identity.user_roles (user_id, role)
        SELECT r.user_id, 'customer' FROM identity.user_roles r
         WHERE r.role = 'inspector'
           AND NOT EXISTS (SELECT 1 FROM identity.user_roles o
                            WHERE o.user_id = r.user_id AND o.role <> 'inspector')
        """
    )
    op.execute("DELETE FROM identity.user_roles WHERE role = 'inspector'")


def downgrade() -> None:
    pass  # the role is gone; nobody is made an inspector again
