"""Allow one chunk table to contain isolated embedding dimensions."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0015_multi_dimension_embeddings"
down_revision = "0014_embedding_model_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("idx_document_chunks_embedding_hnsw", table_name="document_chunks")
    op.alter_column("document_chunks", "embedding", type_=Vector(), postgresql_using="embedding::vector")
    op.add_column("document_chunks", sa.Column("embedding_dimension", sa.Integer(), nullable=True))
    op.execute("UPDATE document_chunks SET embedding_dimension = vector_dims(embedding) WHERE embedding IS NOT NULL")
    op.create_index("ix_document_chunks_embedding_dimension", "document_chunks", ["embedding_dimension"])
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding_1024_hnsw ON document_chunks "
        "USING hnsw ((embedding::vector(1024)) vector_cosine_ops) "
        "WHERE embedding_dimension = 1024"
    )
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding_2560_hnsw ON document_chunks "
        "USING hnsw ((embedding::halfvec(2560)) halfvec_cosine_ops) "
        "WHERE embedding_dimension = 2560"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_1024_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_document_chunks_embedding_2560_hnsw")
    op.drop_index("ix_document_chunks_embedding_dimension", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding_dimension")
    op.alter_column("document_chunks", "embedding", type_=Vector(1024), postgresql_using="embedding::vector(1024)")
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )
