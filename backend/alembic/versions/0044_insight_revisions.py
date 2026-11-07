"""Version insight review decisions."""

from alembic import op
import sqlalchemy as sa

revision = "0044_insight_revisions"
down_revision = "0043_source_repo_stats"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "insights", sa.Column("revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "insights", sa.Column("review_history", sa.JSON(), nullable=False, server_default="[]")
    )
    op.drop_constraint("ck_insights_status", "insights", type_="check")
    op.drop_constraint("ck_insights_verification_state", "insights", type_="check")
    op.create_check_constraint(
        "ck_insights_status", "insights", "status IN ('draft', 'verified', 'outdated', 'rejected')"
    )
    op.create_check_constraint(
        "ck_insights_verification_state",
        "insights",
        "(status IN ('draft','rejected') AND verified_by_id IS NULL AND verified_at IS NULL) OR (status IN ('verified','outdated') AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
    )


def downgrade():
    op.execute("UPDATE insights SET status='draft' WHERE status='rejected'")
    op.drop_constraint("ck_insights_status", "insights", type_="check")
    op.drop_constraint("ck_insights_verification_state", "insights", type_="check")
    op.create_check_constraint(
        "ck_insights_status", "insights", "status IN ('draft','verified','outdated')"
    )
    op.create_check_constraint(
        "ck_insights_verification_state",
        "insights",
        "(status='draft' AND verified_by_id IS NULL AND verified_at IS NULL) OR (status IN ('verified','outdated') AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
    )
    op.drop_column("insights", "review_history")
    op.drop_column("insights", "revision")
