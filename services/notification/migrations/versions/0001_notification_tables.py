"""notification service tables: device_tokens, notifications, outbox, processed_events

Revision ID: 0001
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "notification"


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.String(256), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "token", name="uq_device_tokens_user_token"),
        schema=SCHEMA,
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"], schema=SCHEMA)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.String(1000), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], schema=SCHEMA)
    op.create_index(
        "ix_notifications_user_created",
        "notifications",
        ["user_id", "created_at"],
        schema=SCHEMA,
    )
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "read_at"],
        schema=SCHEMA,
    )

    op.create_table(
        "processed_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        schema=SCHEMA,
    )

    op.create_table(
        "outbox",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_notification_outbox_unpublished", "outbox", ["published_at"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("outbox", schema=SCHEMA)
    op.drop_table("processed_events", schema=SCHEMA)
    op.drop_table("notifications", schema=SCHEMA)
    op.drop_table("device_tokens", schema=SCHEMA)
