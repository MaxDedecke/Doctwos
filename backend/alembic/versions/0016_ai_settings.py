"""Persist the deployment-wide AI profile for UI configuration."""

from alembic import op
import sqlalchemy as sa


revision = "0016_ai_settings"
down_revision = "0015_multi_dimension_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("llm_provider", sa.String(length=32), nullable=False, server_default="ollama"),
        sa.Column("llm_model", sa.String(), nullable=False, server_default="disabled"),
        sa.Column("llm_base_url", sa.String(), nullable=True),
        sa.Column("llm_api_key", sa.String(), nullable=True),
        sa.Column("embedding_provider", sa.String(length=32), nullable=False, server_default="ollama"),
        sa.Column("embedding_model", sa.String(), nullable=False, server_default="bge-m3"),
        sa.Column("embedding_base_url", sa.String(), nullable=True),
        sa.Column("embedding_api_key", sa.String(), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("embedding_context_length", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("llm_context_length", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ai_settings")
