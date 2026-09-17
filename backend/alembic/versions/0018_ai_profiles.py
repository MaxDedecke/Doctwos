"""Add server-side AI profiles and migrate the legacy deployment setting."""

from alembic import op
import sqlalchemy as sa


revision = "0018_ai_profiles"
down_revision = "0017_incremental_link_builder"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("protocol", sa.String(length=32), nullable=False),
        sa.Column("llm_model", sa.String(), nullable=False),
        sa.Column("llm_base_url", sa.String(), nullable=True),
        sa.Column("llm_path", sa.String(), nullable=True),
        sa.Column("llm_api_key", sa.Text(), nullable=True),
        sa.Column("embedding_provider", sa.String(length=32), nullable=False),
        sa.Column("embedding_model", sa.String(), nullable=False),
        sa.Column("embedding_base_url", sa.String(), nullable=True),
        sa.Column("embedding_path", sa.String(), nullable=True),
        sa.Column("embedding_api_key", sa.Text(), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False, server_default="1024"),
        sa.Column("embedding_context_length", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("llm_context_length", sa.Integer(), nullable=False, server_default="8192"),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.add_column("ai_settings", sa.Column("active_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_ai_settings_active_profile",
        "ai_settings",
        "ai_profiles",
        ["active_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # The local profile is a stable escape hatch. Its URL is intentionally not
    # copied from ai_settings, because that row may already point at a remote host.
    op.execute(
        """
        INSERT INTO ai_profiles
          (name, kind, provider, protocol, llm_model, llm_base_url, llm_path,
           embedding_provider, embedding_model, embedding_base_url, embedding_path,
           embedding_dimension, embedding_context_length, llm_context_length, is_system)
        SELECT 'Lokales Ollama', 'local', 'ollama', 'ollama',
               COALESCE(NULLIF(llm_model, ''), 'disabled'), 'http://ollama:11434', '/api/chat',
               'ollama', COALESCE(NULLIF(embedding_model, ''), 'bge-m3'),
               'http://ollama:11434', '/api/embed', embedding_dimension,
               embedding_context_length, llm_context_length, true
        FROM ai_settings ORDER BY id LIMIT 1
        """
    )
    op.execute(
        """
        INSERT INTO ai_profiles
          (name, kind, provider, protocol, llm_model, llm_base_url, llm_path, llm_api_key,
           embedding_provider, embedding_model, embedding_base_url, embedding_path,
           embedding_api_key, embedding_dimension, embedding_context_length,
           llm_context_length, is_system)
        SELECT 'Remote (migriert)', 'remote', llm_provider,
               CASE WHEN llm_provider = 'ollama' THEN 'ollama' ELSE 'openai_chat' END,
               llm_model, llm_base_url,
               CASE WHEN llm_provider = 'ollama' THEN '/api/chat' ELSE '/chat/completions' END,
               llm_api_key, embedding_provider, embedding_model, embedding_base_url,
               CASE WHEN embedding_provider = 'ollama' THEN '/api/embed' ELSE '/embeddings' END,
               embedding_api_key, embedding_dimension, embedding_context_length,
               llm_context_length, false
        FROM ai_settings
        WHERE COALESCE(llm_base_url, '') NOT IN ('', 'http://ollama:11434')
        ORDER BY id LIMIT 1
        """
    )
    op.execute(
        """
        UPDATE ai_settings s SET active_profile_id = COALESCE(
          (SELECT id FROM ai_profiles WHERE kind = 'remote' ORDER BY id LIMIT 1),
          (SELECT id FROM ai_profiles WHERE kind = 'local' ORDER BY id LIMIT 1)
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_ai_settings_active_profile", "ai_settings", type_="foreignkey")
    op.drop_column("ai_settings", "active_profile_id")
    op.drop_table("ai_profiles")
