"""Persist the explicit project/source scope of link-builder runs (O-177)."""

from alembic import op
import sqlalchemy as sa


revision = "0020_link_builder_scope"
down_revision = "0019_separate_embedding_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("link_builder_runs", sa.Column("scope_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("link_builder_runs", "scope_json")
