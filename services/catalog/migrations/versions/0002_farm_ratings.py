"""catalog: running rating total per farm, fed by order.rated events

Revision ID: 0002_farm_ratings
Revises: 0001_initial
Create Date: 2026-11-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_farm_ratings"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "catalog"


def upgrade() -> None:
    for column in ("rating_count", "rating_sum"):
        op.add_column(
            "farms",
            sa.Column(column, sa.Integer(), nullable=False, server_default="0"),
            schema=SCHEMA,
        )


def downgrade() -> None:
    for column in ("rating_sum", "rating_count"):
        op.drop_column("farms", column, schema=SCHEMA)
