"""Store repository statistics on the source, computed at the end of a sync."""

from alembic import op
import sqlalchemy as sa

revision = "0043_source_repo_stats"
down_revision = "0042_search_trigram_indexes"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("knowledge_sources", sa.Column("repo_stats", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("knowledge_sources", "repo_stats")
