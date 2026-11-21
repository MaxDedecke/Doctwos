"""Verdichteter Gesprächsverlauf je Chat-Sitzung und geprüfte Modellfähigkeiten je KI-Profil."""

from alembic import op
import sqlalchemy as sa

revision = "0050_chat_compaction_caps"
down_revision = "0049_source_health_embed_switch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_sessions", sa.Column("context_summary", sa.String(), nullable=True))
    op.add_column(
        "chat_sessions", sa.Column("context_summary_upto_id", sa.Integer(), nullable=True)
    )
    op.add_column("ai_profiles", sa.Column("capabilities_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_profiles", "capabilities_json")
    op.drop_column("chat_sessions", "context_summary_upto_id")
    op.drop_column("chat_sessions", "context_summary")
