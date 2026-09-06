"""Add auditable chat downvote signals for cited links (O-087)."""

from alembic import op
import sqlalchemy as sa


revision = "0008_chat_link_feedback_signals"
down_revision = "0007_user_oidc_subject"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_link_feedback_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chat_message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chat_session_id",
            sa.Integer(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("link_type", sa.String(length=30), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "chat_message_id", "link_type", "link_id", name="uq_chat_link_feedback_signal"
        ),
    )
    op.create_index("ix_chat_link_feedback_signals_id", "chat_link_feedback_signals", ["id"])
    op.create_index(
        "ix_chat_link_feedback_signals_message",
        "chat_link_feedback_signals",
        ["chat_message_id"],
    )
    op.create_index(
        "ix_chat_link_feedback_signals_session",
        "chat_link_feedback_signals",
        ["chat_session_id"],
    )
    op.create_index(
        "ix_chat_link_feedback_signals_user", "chat_link_feedback_signals", ["user_id"]
    )
    op.create_index(
        "ix_chat_link_feedback_active",
        "chat_link_feedback_signals",
        ["link_type", "link_id", "revoked_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_link_feedback_active", table_name="chat_link_feedback_signals")
    op.drop_index("ix_chat_link_feedback_signals_user", table_name="chat_link_feedback_signals")
    op.drop_index("ix_chat_link_feedback_signals_session", table_name="chat_link_feedback_signals")
    op.drop_index("ix_chat_link_feedback_signals_message", table_name="chat_link_feedback_signals")
    op.drop_index("ix_chat_link_feedback_signals_id", table_name="chat_link_feedback_signals")
    op.drop_table("chat_link_feedback_signals")
