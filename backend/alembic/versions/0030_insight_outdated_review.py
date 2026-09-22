"""Mark verified insights as outdated after an evidence source changes."""

from alembic import op
import sqlalchemy as sa


revision = "0030_insight_outdated_review"
down_revision = "0029_insight_audit_user_restrict"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_insights_status", "insights", type_="check")
    op.drop_constraint("ck_insights_verification_state", "insights", type_="check")
    op.add_column("insights", sa.Column("outdated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("insights", sa.Column("outdated_source_ids", sa.JSON(), nullable=True))
    op.create_check_constraint("ck_insights_status", "insights", "status IN ('draft', 'verified', 'outdated')")
    op.create_check_constraint("ck_insights_verification_state", "insights", "(status = 'draft' AND verified_by_id IS NULL AND verified_at IS NULL) OR (status IN ('verified', 'outdated') AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)")


def downgrade() -> None:
    op.drop_constraint("ck_insights_verification_state", "insights", type_="check")
    op.drop_constraint("ck_insights_status", "insights", type_="check")
    op.drop_column("insights", "outdated_source_ids")
    op.drop_column("insights", "outdated_at")
    op.create_check_constraint("ck_insights_status", "insights", "status IN ('draft', 'verified')")
    op.create_check_constraint("ck_insights_verification_state", "insights", "(status = 'draft' AND verified_by_id IS NULL AND verified_at IS NULL) OR (status = 'verified' AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)")
