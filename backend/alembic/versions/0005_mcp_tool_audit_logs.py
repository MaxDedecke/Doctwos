"""Persist data-minimal MCP tool-call audit entries."""

from alembic import op
import sqlalchemy as sa


revision = "0005_mcp_tool_audit_logs"
down_revision = "0004_job_center_dismissals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_tool_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chat_session_id", sa.Integer(), sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("chat_message_id", sa.Integer(), sa.ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("knowledge_source_id", sa.Integer(), sa.ForeignKey("knowledge_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("server_name", sa.String(length=120), nullable=False),
        sa.Column("tool_name", sa.String(length=200), nullable=False),
        sa.Column("arguments_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trace_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    for column in ("user_id", "chat_session_id", "chat_message_id", "project_id", "knowledge_source_id", "created_at"):
        op.create_index(f"ix_mcp_tool_audit_logs_{column}", "mcp_tool_audit_logs", [column])


def downgrade() -> None:
    for column in ("created_at", "knowledge_source_id", "project_id", "chat_message_id", "chat_session_id", "user_id"):
        op.drop_index(f"ix_mcp_tool_audit_logs_{column}", table_name="mcp_tool_audit_logs")
    op.drop_table("mcp_tool_audit_logs")
