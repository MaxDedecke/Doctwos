"""Persist Celery task identifiers for job cancellation."""

from alembic import op
import sqlalchemy as sa


revision = "0006_job_center_cancellation"
down_revision = "0005_mcp_tool_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("celery_task_id", sa.String(length=255), nullable=True))
    op.add_column("link_builder_runs", sa.Column("celery_task_id", sa.String(length=255), nullable=True))
    op.add_column("diagnostics_runs", sa.Column("celery_task_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("diagnostics_runs", "celery_task_id")
    op.drop_column("link_builder_runs", "celery_task_id")
    op.drop_column("knowledge_sources", "celery_task_id")
