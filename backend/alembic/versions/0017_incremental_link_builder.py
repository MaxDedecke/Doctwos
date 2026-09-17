"""Persist incremental link-builder state and dirty work items (O-180)."""

from alembic import op
import sqlalchemy as sa


revision = "0017_incremental_link_builder"
down_revision = "0016_ai_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "document_chunks",
        sa.Column("link_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])

    op.add_column(
        "code_entities",
        sa.Column("link_revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("code_entities", sa.Column("embedding_model", sa.String(), nullable=True))

    op.add_column("entity_doc_links", sa.Column("entity_content_hash", sa.String(length=64), nullable=True))
    op.add_column("entity_doc_links", sa.Column("chunk_content_hash", sa.String(length=64), nullable=True))
    op.add_column("entity_doc_links", sa.Column("embedding_model", sa.String(), nullable=True))
    op.add_column("entity_doc_links", sa.Column("entity_link_revision", sa.Integer(), nullable=True))
    op.add_column("entity_doc_links", sa.Column("chunk_link_revision", sa.Integer(), nullable=True))

    op.create_table(
        "link_builder_dirty_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            sa.Integer(),
            sa.ForeignKey("code_entities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "chunk_id",
            sa.Integer(),
            sa.ForeignKey("document_chunks.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(length=40), nullable=False, server_default="content_changed"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_link_builder_dirty_items_id", "link_builder_dirty_items", ["id"])
    op.create_index(
        "ix_link_builder_dirty_pending_scope",
        "link_builder_dirty_items",
        ["project_id", "status", "entity_id", "chunk_id"],
    )
    op.create_index("ix_link_builder_dirty_items_project_id", "link_builder_dirty_items", ["project_id"])
    op.create_index("ix_link_builder_dirty_items_entity_id", "link_builder_dirty_items", ["entity_id"])
    op.create_index("ix_link_builder_dirty_items_chunk_id", "link_builder_dirty_items", ["chunk_id"])
    op.create_index("ix_link_builder_dirty_items_status", "link_builder_dirty_items", ["status"])


def downgrade() -> None:
    op.drop_table("link_builder_dirty_items")
    for column in (
        "chunk_link_revision",
        "entity_link_revision",
        "embedding_model",
        "chunk_content_hash",
        "entity_content_hash",
    ):
        op.drop_column("entity_doc_links", column)
    op.drop_column("code_entities", "embedding_model")
    op.drop_column("code_entities", "link_revision")
    op.drop_index("ix_document_chunks_content_hash", table_name="document_chunks")
    op.drop_column("document_chunks", "link_revision")
    op.drop_column("document_chunks", "content_hash")
