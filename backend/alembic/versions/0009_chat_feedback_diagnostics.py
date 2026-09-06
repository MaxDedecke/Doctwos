"""Add opt-in local chat-feedback diagnostic capture (O-088)."""

from alembic import op
import sqlalchemy as sa


revision = "0009_chat_feedback_diagnostics"
down_revision = "0008_chat_link_feedback_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_feedback_diagnostic_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("collection_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("support_export_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "chat_feedback_diagnostic_cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL")),
        sa.Column("question", sa.String(), nullable=True),
        sa.Column("answer", sa.String(), nullable=False),
        sa.Column("sources_json", sa.JSON(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("provider", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_feedback_diagnostic_cases_id", "chat_feedback_diagnostic_cases", ["id"])
    op.create_index("ix_chat_feedback_diagnostic_cases_created", "chat_feedback_diagnostic_cases", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_chat_feedback_diagnostic_cases_created", table_name="chat_feedback_diagnostic_cases")
    op.drop_index("ix_chat_feedback_diagnostic_cases_id", table_name="chat_feedback_diagnostic_cases")
    op.drop_table("chat_feedback_diagnostic_cases")
    op.drop_table("chat_feedback_diagnostic_settings")
