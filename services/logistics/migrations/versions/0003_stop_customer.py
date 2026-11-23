"""pool stops know whose order they carry (tracking and the delivery code are theirs only)

Revision ID: 0003
Revises: 0002
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

SCHEMA = "logistics"


def upgrade() -> None:
    op.add_column("pool_stops", sa.Column("customer_id", sa.Uuid(), nullable=True), schema=SCHEMA)
    op.create_index(
        "ix_logistics_pool_stops_customer_id", "pool_stops", ["customer_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_logistics_pool_stops_customer_id", "pool_stops", schema=SCHEMA)
    op.drop_column("pool_stops", "customer_id", schema=SCHEMA)
