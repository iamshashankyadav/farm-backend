"""no quality gate: packed orders are ready for dispatch, harvests are not graded

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23 12:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Produce orders that were waiting for an inspection move on, as packing now does.
    op.execute(
        """
        INSERT INTO "order".order_events (order_id, status, note, occurred_at)
        SELECT id, 'READY_FOR_DISPATCH', 'Ready for pickup (quality check removed)', now()
          FROM "order".orders
         WHERE order_type = 'PRODUCE' AND status IN ('PACKED', 'QC_PASSED')
        """
    )
    op.execute(
        """
        UPDATE "order".orders SET status = 'READY_FOR_DISPATCH', updated_at = now()
         WHERE order_type = 'PRODUCE' AND status IN ('PACKED', 'QC_PASSED')
        """
    )
    op.drop_column("harvest_reservations", "quality_result", schema="order")
    op.drop_column("harvest_reservations", "quality_grade", schema="order")


def downgrade() -> None:
    op.add_column(
        "harvest_reservations",
        sa.Column("quality_grade", sa.String(length=2), nullable=True),
        schema="order",
    )
    op.add_column(
        "harvest_reservations",
        sa.Column("quality_result", sa.String(length=10), nullable=True),
        schema="order",
    )
