"""Index unresolved impact candidates without blocking source imports."""

from alembic import op
import sqlalchemy as sa

revision = "0045_unresolved_reference_index"
down_revision = "0044_insight_revisions"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_code_edges_unresolved_project_name"


def upgrade():
    # Concurrent builds can leave an invalid index when interrupted. Recover
    # that state before retrying, while accepting an already completed build.
    with op.get_context().autocommit_block():
        valid = (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT i.indisvalid FROM pg_index i "
                    "JOIN pg_class c ON c.oid=i.indexrelid "
                    "JOIN pg_namespace n ON n.oid=c.relnamespace "
                    "WHERE c.relname=:name AND n.nspname=current_schema()"
                ),
                {"name": INDEX_NAME},
            )
            .scalar()
        )
        if valid is False:
            op.drop_index(INDEX_NAME, table_name="code_edges", postgresql_concurrently=True)
        op.create_index(
            INDEX_NAME,
            "code_edges",
            ["project_id", sa.text("lower(dst_name)"), "id"],
            postgresql_where=sa.text(
                "dst_entity_id IS NULL AND resolution IN ('unresolved', 'dynamic')"
            ),
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index(INDEX_NAME, table_name="code_edges", postgresql_concurrently=True)
