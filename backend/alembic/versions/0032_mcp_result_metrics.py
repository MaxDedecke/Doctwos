"""Record bounded MCP result metrics without storing tool content."""

from alembic import op
import sqlalchemy as sa


revision = "0032_mcp_result_metrics"
down_revision = "0031_mcp_access_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "mcp_tool_audit_logs",
        sa.Column("result_payload_bytes", sa.Integer(), nullable=True),
    )
    op.add_column(
        "mcp_tool_audit_logs",
        sa.Column("result_truncated", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "mcp_tool_audit_logs",
        sa.Column("index_revision", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mcp_tool_audit_logs", "index_revision")
    op.drop_column("mcp_tool_audit_logs", "result_truncated")
    op.drop_column("mcp_tool_audit_logs", "result_payload_bytes")
