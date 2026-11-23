"""catalog: listings have no grade any more (the quality gate was removed, November 2026)

Revision ID: 0003_drop_listing_grade
Revises: 0002_farm_ratings
Create Date: 2026-11-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_drop_listing_grade"
down_revision: str | None = "0002_farm_ratings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "catalog"


def upgrade() -> None:
    op.drop_column("produce_listings", "grade", schema=SCHEMA)


def downgrade() -> None:
    op.add_column(
        "produce_listings", sa.Column("grade", sa.String(length=1), nullable=True), schema=SCHEMA
    )
