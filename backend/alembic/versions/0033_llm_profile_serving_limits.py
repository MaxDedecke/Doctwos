"""Per-profile concurrency limit and sampling temperature for self-hosted LLMs."""

from alembic import op
import sqlalchemy as sa


revision = "0033_llm_profile_serving_limits"
down_revision = "0032_mcp_result_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_profiles", sa.Column("llm_max_concurrency", sa.Integer(), nullable=True))
    op.add_column("ai_profiles", sa.Column("llm_temperature", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_profiles", "llm_temperature")
    op.drop_column("ai_profiles", "llm_max_concurrency")
