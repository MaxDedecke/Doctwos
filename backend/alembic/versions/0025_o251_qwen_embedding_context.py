"""Align the system Qwen embedding profile with the prescribed 8100-token limit."""

from alembic import op


revision = "0025_o251_qwen_embedding_context"
down_revision = "0024_knowledge_source_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Only migrate the shipped system profile.  Customer-created profiles are
    # deliberate configuration and must not be overwritten by O-251.
    op.execute(
        """
        UPDATE embedding_profiles
           SET context_length = 8100,
               updated_at = CURRENT_TIMESTAMP
         WHERE is_system = TRUE
           AND model = 'qwen3-embedding:4b'
           AND context_length = 8192
        """
    )
    op.execute(
        """
        UPDATE ai_settings AS settings
           SET embedding_context_length = 8100,
               updated_at = CURRENT_TIMESTAMP
          FROM embedding_profiles AS profile
         WHERE profile.id = settings.active_embedding_profile_id
           AND profile.is_system = TRUE
           AND profile.model = 'qwen3-embedding:4b'
           AND settings.embedding_context_length = 8192
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE embedding_profiles
           SET context_length = 8192,
               updated_at = CURRENT_TIMESTAMP
         WHERE is_system = TRUE
           AND model = 'qwen3-embedding:4b'
           AND context_length = 8100
        """
    )
    op.execute(
        """
        UPDATE ai_settings AS settings
           SET embedding_context_length = 8192,
               updated_at = CURRENT_TIMESTAMP
          FROM embedding_profiles AS profile
         WHERE profile.id = settings.active_embedding_profile_id
           AND profile.is_system = TRUE
           AND profile.model = 'qwen3-embedding:4b'
           AND settings.embedding_context_length = 8100
        """
    )
