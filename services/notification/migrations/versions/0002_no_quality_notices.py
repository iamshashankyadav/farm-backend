"""drop inspection notices: the quality gate and its ORDER_QC_PASSED type were removed

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM notification.notifications WHERE type = 'ORDER_QC_PASSED'")


def downgrade() -> None:
    pass
