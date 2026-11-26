"""Kundenbranding (Logos, Name, Akzentfarbe, Login-Hinweis und -Links) als eine Zeile."""

from alembic import op
import sqlalchemy as sa

revision = "0052_corporate_branding"
down_revision = "0051_chat_pins_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "corporate_branding",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_name", sa.String(60), nullable=True),
        sa.Column("accent_color", sa.String(7), nullable=True),
        sa.Column("login_notice", sa.String(280), nullable=True),
        sa.Column("imprint_url", sa.String(500), nullable=True),
        sa.Column("privacy_url", sa.String(500), nullable=True),
        sa.Column("support_url", sa.String(500), nullable=True),
        sa.Column("logo_light", sa.LargeBinary(), nullable=True),
        sa.Column("logo_dark", sa.LargeBinary(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("corporate_branding")
