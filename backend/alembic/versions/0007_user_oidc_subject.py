"""Add OIDC subject column to users, make password_hash nullable for SSO accounts (E-12)."""

from alembic import op
import sqlalchemy as sa


revision = "0007_user_oidc_subject"
down_revision = "0006_job_center_cancellation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.String(), nullable=True)
    op.add_column("users", sa.Column("oidc_subject", sa.String(), nullable=True))
    op.create_index("ix_users_oidc_subject", "users", ["oidc_subject"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_users_oidc_subject", table_name="users")
    op.drop_column("users", "oidc_subject")
    op.alter_column("users", "password_hash", existing_type=sa.String(), nullable=False)
