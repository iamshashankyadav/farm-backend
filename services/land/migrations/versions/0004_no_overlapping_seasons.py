"""Seasons of one plot never overlap, so the same land cannot be let twice for the same days.

The exclusion constraint needs the btree_gist extension (uuid equality inside a GiST index).
infra/postgres/init-db.sh creates it as the superuser on a new volume; on an existing database a
superuser runs `CREATE EXTENSION IF NOT EXISTS btree_gist;` once before this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_no_overlapping_seasons"
down_revision = "0003_agreements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if not bind.scalar(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")):
        try:
            with bind.begin_nested():
                op.execute("CREATE EXTENSION btree_gist")
        except sa.exc.ProgrammingError as exc:
            raise RuntimeError(
                "The btree_gist extension is missing and the land role may not create it. "
                "As the database superuser run: CREATE EXTENSION IF NOT EXISTS btree_gist;"
            ) from exc
    op.execute(
        """
        ALTER TABLE land.plot_seasons
          ADD CONSTRAINT plot_seasons_no_overlap
          EXCLUDE USING gist (plot_id WITH =, daterange(start_date, end_date, '[]') WITH &&)
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE land.plot_seasons DROP CONSTRAINT plot_seasons_no_overlap")
