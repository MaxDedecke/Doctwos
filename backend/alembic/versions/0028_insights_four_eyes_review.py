"""Add evidence-backed project insights with four-eyes verification (O-271/O-301)."""

from alembic import op
import sqlalchemy as sa


revision = "0028_insights_four_eyes_review"
down_revision = "0027_knowledge_link_dir_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("origin_kind", sa.String(length=20), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("verified_by_id", sa.Integer(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["verified_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("origin_kind IN ('chat', 'code', 'process')", name="ck_insights_origin_kind"),
        sa.CheckConstraint("status IN ('draft', 'verified')", name="ck_insights_status"),
        sa.CheckConstraint(
            "(status = 'draft' AND verified_by_id IS NULL AND verified_at IS NULL) OR "
            "(status = 'verified' AND verified_by_id IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_insights_verification_state",
        ),
    )
    op.create_index("ix_insights_project_id", "insights", ["project_id"])
    op.create_index("ix_insights_status", "insights", ["status"])


def downgrade() -> None:
    op.drop_index("ix_insights_status", table_name="insights")
    op.drop_index("ix_insights_project_id", table_name="insights")
    op.drop_table("insights")
