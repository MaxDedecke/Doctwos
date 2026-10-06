"""Link profiles to deployer-managed local LLM containers."""

from alembic import op
import sqlalchemy as sa


revision = "0035_profile_deployments"
down_revision = "0034_entity_doc_link_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_profiles", sa.Column("deployment_name", sa.String(64), nullable=True))
    op.add_column("embedding_profiles", sa.Column("deployment_name", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("embedding_profiles", "deployment_name")
    op.drop_column("ai_profiles", "deployment_name")
