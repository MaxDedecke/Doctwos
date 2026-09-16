"""O-187: persist the embedding model used for sources and vectors."""

from alembic import op
import sqlalchemy as sa


revision = "0014_embedding_model_metadata"
down_revision = "0013_copybook_dependencies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("link_builder_runs", sa.Column("embedding_model", sa.String(), nullable=True))
    # Existing vectors were created with the deployment default in the former
    # schema. Keep them searchable without pretending that an arbitrary newly
    # selected model produced them.
    op.execute(
        "UPDATE document_chunks SET embedding_model = 'bge-m3' "
        "WHERE embedding IS NOT NULL AND embedding_model IS NULL"
    )
    op.execute(
        "UPDATE knowledge_sources SET embedding_model = 'bge-m3' "
        "WHERE embedding_model IS NULL"
    )


def downgrade() -> None:
    op.drop_column("document_chunks", "embedding_model")
    op.drop_column("link_builder_runs", "embedding_model")
    op.drop_column("knowledge_sources", "embedding_model")
