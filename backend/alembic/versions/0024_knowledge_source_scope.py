"""Keep knowledge source scope metadata in sync with the ORM model."""

from alembic import op
import sqlalchemy as sa


revision = "0024_knowledge_source_scope"
down_revision = "0023_module_scoped_code_entities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_sources", sa.Column("scope_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("knowledge_sources", "scope_json")
