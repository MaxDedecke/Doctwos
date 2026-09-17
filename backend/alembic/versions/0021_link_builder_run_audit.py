"""Record the initiating user for privileged link-builder runs (O-178)."""

from alembic import op
import sqlalchemy as sa


revision = "0021_link_builder_run_audit"
down_revision = "0020_link_builder_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "link_builder_runs",
        sa.Column("triggered_by_user_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_link_builder_runs_triggered_by_user_id",
        "link_builder_runs",
        ["triggered_by_user_id"],
    )
    op.create_foreign_key(
        "fk_link_builder_runs_triggered_by_user_id_users",
        "link_builder_runs",
        "users",
        ["triggered_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_link_builder_runs_triggered_by_user_id_users",
        "link_builder_runs",
        type_="foreignkey",
    )
    op.drop_index("ix_link_builder_runs_triggered_by_user_id", table_name="link_builder_runs")
    op.drop_column("link_builder_runs", "triggered_by_user_id")
