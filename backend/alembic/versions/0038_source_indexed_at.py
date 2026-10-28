"""Record when a knowledge source was last indexed completely and consistently."""

from alembic import op
import sqlalchemy as sa

revision = "0038_source_indexed_at"
down_revision = "0037_link_manager_projects"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "knowledge_sources", sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True)
    )
    # Bisher galt ein Lauf nur über den Status als vollständig; last_synced_at
    # wird auch nach Fehlern gesetzt und taugt nur bei "completed" als Stand.
    op.execute(
        "UPDATE knowledge_sources SET indexed_at = last_synced_at "
        "WHERE sync_status = 'completed' AND last_synced_at IS NOT NULL"
    )


def downgrade():
    op.drop_column("knowledge_sources", "indexed_at")
