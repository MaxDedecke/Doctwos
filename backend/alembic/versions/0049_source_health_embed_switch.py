"""Quellenzustand (Fehlerart, Fehler in Folge, letzter Versuch) und Modellwechsel der Embeddings je Projekt."""

import os

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0049_source_health_embed_switch"
down_revision = "0048_insight_team_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("error_kind", sa.String(32), nullable=True))
    op.add_column(
        "knowledge_sources",
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "knowledge_sources",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("document_chunks", sa.Column("embedding_next", Vector(), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_next_model", sa.String(), nullable=True))
    op.create_table(
        "embedding_migrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("embedding_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_model", sa.String(), nullable=False),
        sa.Column("target_dimension", sa.Integer(), nullable=True),
        sa.Column("previous_model", sa.String(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="embedding"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("switched_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Altbestände ohne Modelleintrag galten als „jeweiliges Standardmodell“; ändert sich der Standard, würden sie
    # falsch zugeordnet. Sie erhalten das Modell ihrer Quelle, sonst den heute konfigurierten Standard.
    op.execute(
        "UPDATE document_chunks c SET embedding_model = s.embedding_model FROM knowledge_sources s "
        "WHERE c.embedding_model IS NULL AND c.embedding IS NOT NULL AND c.source_id = s.id "
        "AND s.embedding_model IS NOT NULL"
    )
    default_model = (
        os.getenv("OLLAMA_EMBED_MODEL") or os.getenv("EMBED_MODEL") or "bge-m3"
    ).strip()
    op.execute(
        sa.text(
            "UPDATE document_chunks SET embedding_model = :model "
            "WHERE embedding_model IS NULL AND embedding IS NOT NULL"
        ).bindparams(model=default_model)
    )


def downgrade() -> None:
    op.drop_table("embedding_migrations")
    op.drop_column("document_chunks", "embedding_next_model")
    op.drop_column("document_chunks", "embedding_next")
    op.drop_column("knowledge_sources", "last_attempt_at")
    op.drop_column("knowledge_sources", "failure_count")
    op.drop_column("knowledge_sources", "error_kind")
