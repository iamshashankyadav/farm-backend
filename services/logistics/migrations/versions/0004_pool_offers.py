"""pool offers: a new pool is offered to nearby partners, the first to accept gets it

Revision ID: 0004
Revises: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

SCHEMA = "logistics"


def upgrade() -> None:
    op.create_table(
        "pool_offers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="OFFERED"),
        sa.Column("distance_km", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("pool_id", "partner_id", name="pool_offer_once"),
        schema=SCHEMA,
    )
    op.create_index("ix_logistics_pool_offers_pool_id", "pool_offers", ["pool_id"], schema=SCHEMA)
    op.create_index(
        "ix_logistics_pool_offers_partner_id", "pool_offers", ["partner_id"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_logistics_pool_offers_partner_id", "pool_offers", schema=SCHEMA)
    op.drop_index("ix_logistics_pool_offers_pool_id", "pool_offers", schema=SCHEMA)
    op.drop_table("pool_offers", schema=SCHEMA)
