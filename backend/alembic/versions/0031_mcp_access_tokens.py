"""Add revocable, user-bound MCP access tokens."""

from alembic import op
import sqlalchemy as sa


revision = "0031_mcp_access_tokens"
down_revision = "0030_insight_outdated_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_access_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_mcp_access_tokens_user_id", "mcp_access_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_mcp_access_tokens_user_id", table_name="mcp_access_tokens")
    op.drop_table("mcp_access_tokens")
