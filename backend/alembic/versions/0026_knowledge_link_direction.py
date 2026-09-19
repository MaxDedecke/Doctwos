"""Add direction column to knowledge_links table.

O-264: Model edge directionality for knowledge links.
Allowed values: 'undirected' (default), 'directed' (source_a -> source_b), 'bidirectional'.
"""

from alembic import op
import sqlalchemy as sa


revision = "0026_knowledge_link_direction"
down_revision = "0025_o251_qwen_embedding_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_links",
        sa.Column(
            "direction",
            sa.String(length=20),
            nullable=False,
            server_default="undirected",
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_links", "direction")
