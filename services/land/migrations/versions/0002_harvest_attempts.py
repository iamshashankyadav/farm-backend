"""Add a monotonically increasing attempt counter to land reservations."""
from alembic import op
import sqlalchemy as sa

revision = "0002_harvest_attempts"
down_revision = "0001_land_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reservations",
        sa.Column("harvest_attempt", sa.Integer(), nullable=False, server_default="0"),
        schema="land",
    )


def downgrade() -> None:
    op.drop_column("reservations", "harvest_attempt", schema="land")
