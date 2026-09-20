"""Restrict knowledge link directions to the supported values."""

from alembic import op


revision = "0027_knowledge_link_dir_check"
down_revision = "0026_knowledge_link_direction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_knowledge_links_direction",
        "knowledge_links",
        "direction IN ('directed', 'undirected', 'bidirectional')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_knowledge_links_direction",
        "knowledge_links",
        type_="check",
    )
