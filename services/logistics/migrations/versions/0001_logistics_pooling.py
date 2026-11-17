"""logistics pooling tables

Revision ID: 0001_logistics_pooling
Revises:
Create Date: 2026-11-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "logistics"


def upgrade() -> None:
    op.create_table(
        "delivery_partners",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("vehicle_type", sa.String(30), nullable=True),
        sa.Column("capacity_kg", sa.Float(), nullable=False, server_default="50"),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("dp_online_ix", "delivery_partners", ["is_online"], schema=SCHEMA)

    op.create_table(
        "delivery_pools",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pool_date", sa.Date(), nullable=False),
        sa.Column("partner_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column(
            "geom",
            Geometry("LINESTRING", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("total_km", sa.Float(), nullable=True),
        sa.Column("km_saved", sa.Float(), nullable=True),
        sa.Column("osrm_meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("pool_date_ix", "delivery_pools", ["pool_date"], schema=SCHEMA)
    op.create_index(
        "pool_partner_date_ix", "delivery_pools", ["partner_id", "pool_date"], schema=SCHEMA
    )
    op.execute(f"CREATE INDEX pool_geom_gix ON {SCHEMA}.delivery_pools USING gist (geom)")

    op.create_table(
        "pool_stops",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("pool_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("stop_type", sa.String(8), nullable=False),
        sa.Column("seq", sa.SmallInteger(), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column(
            "geom",
            Geometry("POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("eta", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("photo_media_id", sa.Uuid(), nullable=True),
        sa.Column("otp", sa.String(6), nullable=True),
        sa.Column("otp_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("customer_name", sa.String(120), nullable=True),
        sa.Column("customer_phone", sa.String(20), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("stop_pool_seq_ix", "pool_stops", ["pool_id", "seq"], schema=SCHEMA)
    op.create_index("stop_order_ix", "pool_stops", ["order_id"], schema=SCHEMA)
    op.execute(f"CREATE INDEX stop_geom_gix ON {SCHEMA}.pool_stops USING gist (geom)")

    op.create_table(
        "location_pings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("partner_id", sa.Uuid(), nullable=False),
        sa.Column("pool_id", sa.Uuid(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_ms", sa.Float(), nullable=True),
        sa.Column("heading", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index(
        "ping_partner_recorded_ix",
        "location_pings",
        ["partner_id", "recorded_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ping_pool_recorded_ix",
        "location_pings",
        ["pool_id", "recorded_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.String(100), nullable=False, index=True),
        sa.Column("producer", sa.String(50), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True, index=True),
        schema=SCHEMA,
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    for table in (
        "processed_events",
        "outbox",
        "location_pings",
        "pool_stops",
        "delivery_pools",
        "delivery_partners",
    ):
        op.drop_table(table, schema=SCHEMA)
