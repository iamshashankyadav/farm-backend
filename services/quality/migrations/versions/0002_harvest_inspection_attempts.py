"""Allow one quality inspection for each order or harvest attempt."""

import sqlalchemy as sa
from alembic import op

revision = "0002_harvest_inspection_attempts"
down_revision = "0001_quality_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspections",
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        schema="quality",
    )
    op.drop_constraint("inspection_subject_unique", "inspections", schema="quality", type_="unique")
    op.create_unique_constraint(
        "inspection_subject_attempt_unique",
        "inspections",
        ["subject_type", "subject_id", "attempt"],
        schema="quality",
    )


def downgrade() -> None:
    op.drop_constraint(
        "inspection_subject_attempt_unique", "inspections", schema="quality", type_="unique"
    )
    op.create_unique_constraint(
        "inspection_subject_unique",
        "inspections",
        ["subject_type", "subject_id"],
        schema="quality",
    )
    op.drop_column("inspections", "attempt", schema="quality")
