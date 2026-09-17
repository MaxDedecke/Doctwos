"""Separate embedding endpoints from LLM profiles."""

from alembic import op
import sqlalchemy as sa


revision = "0019_separate_embedding_profiles"
down_revision = "0018_ai_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="ollama"),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False, server_default="/api/embed"),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("context_length", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("ai_settings", sa.Column("active_embedding_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ai_settings_active_embedding_profile",
        "ai_settings", "embedding_profiles", ["active_embedding_profile_id"], ["id"], ondelete="SET NULL",
    )
    # Copy the effective embedding configuration out of the legacy combined
    # profile. Existing installations keep their current import/retrieval setup.
    op.execute(
        """
        INSERT INTO embedding_profiles
          (name, provider, model, base_url, path, api_key, dimension, context_length, is_system)
        SELECT 'Standard-Embedding', COALESCE(p.embedding_provider, s.embedding_provider),
               COALESCE(NULLIF(p.embedding_model, ''), s.embedding_model),
               COALESCE(NULLIF(p.embedding_base_url, ''), s.embedding_base_url, 'http://ollama:11434'),
               COALESCE(NULLIF(p.embedding_path, ''),
                 CASE WHEN COALESCE(p.embedding_provider, s.embedding_provider) = 'openai'
                      THEN '/embeddings' ELSE '/api/embed' END),
               COALESCE(p.embedding_api_key, s.embedding_api_key),
               COALESCE(p.embedding_dimension, s.embedding_dimension, 1024),
               COALESCE(p.embedding_context_length, s.embedding_context_length, 8192), true
        FROM ai_settings s
        LEFT JOIN ai_profiles p ON p.id = s.active_profile_id
        ORDER BY s.id LIMIT 1
        """
    )
    op.execute(
        """
        UPDATE ai_settings SET active_embedding_profile_id =
          (SELECT id FROM embedding_profiles ORDER BY id LIMIT 1)
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_settings_active_embedding_profile", "ai_settings", type_="foreignkey")
    op.drop_column("ai_settings", "active_embedding_profile_id")
    op.drop_table("embedding_profiles")
