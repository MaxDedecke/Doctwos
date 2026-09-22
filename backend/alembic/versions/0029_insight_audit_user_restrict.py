"""Keep verified-insight audit identities intact when users are removed."""

from alembic import op


revision = "0029_insight_audit_user_restrict"
down_revision = "0028_insights_four_eyes_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("insights_created_by_id_fkey", "insights", type_="foreignkey")
    op.drop_constraint("insights_verified_by_id_fkey", "insights", type_="foreignkey")
    op.create_foreign_key("insights_created_by_id_fkey", "insights", "users", ["created_by_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("insights_verified_by_id_fkey", "insights", "users", ["verified_by_id"], ["id"], ondelete="RESTRICT")
    op.alter_column("insights", "created_by_id", existing_type=None, nullable=False)


def downgrade() -> None:
    op.alter_column("insights", "created_by_id", existing_type=None, nullable=True)
    op.drop_constraint("insights_created_by_id_fkey", "insights", type_="foreignkey")
    op.drop_constraint("insights_verified_by_id_fkey", "insights", type_="foreignkey")
    op.create_foreign_key("insights_created_by_id_fkey", "insights", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("insights_verified_by_id_fkey", "insights", "users", ["verified_by_id"], ["id"], ondelete="SET NULL")
