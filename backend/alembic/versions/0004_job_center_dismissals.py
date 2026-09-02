"""persist admin removal of completed Job Center entries"""

from alembic import op
import sqlalchemy as sa


revision = "0004_job_center_dismissals"
down_revision = "0003_expose_analysis_global"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_center_dismissals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("dismissed_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("dismissed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kind", "job_id", name="uq_job_center_dismissals_kind_job"),
    )
    op.create_index("ix_job_center_dismissals_id", "job_center_dismissals", ["id"])


def downgrade() -> None:
    op.drop_index("ix_job_center_dismissals_id", table_name="job_center_dismissals")
    op.drop_table("job_center_dismissals")
