"""Angeheftete Chat-Sitzungen und verschlüsselte Anhänge an Nutzerfragen."""

from alembic import op
import sqlalchemy as sa

revision = "0051_chat_pins_attachments"
down_revision = "0050_chat_compaction_caps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("chat_messages", sa.Column("attachments", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("chat_messages", "attachments")
    op.drop_column("chat_sessions", "is_pinned")
