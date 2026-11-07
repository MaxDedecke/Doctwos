"""Persist source-scoped CI credentials and commit-specific build reports."""

from alembic import op
import sqlalchemy as sa

revision = "0047_ci_build_reports"
down_revision = "0046_insight_version_bindings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ci_build_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("repository", sa.String(64), nullable=False),
        sa.Column("branch", sa.String(256), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ci_build_tokens_project_id", "ci_build_tokens", ["project_id"])
    op.create_index("ix_ci_build_tokens_source_id", "ci_build_tokens", ["source_id"])
    op.create_table(
        "ci_build_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "token_id",
            sa.Integer(),
            sa.ForeignKey("ci_build_tokens.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("repository", sa.String(64), nullable=False),
        sa.Column("branch", sa.String(256), nullable=False),
        sa.Column("commit", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("run_id", sa.String(200), nullable=False),
        sa.Column("attempt", sa.BigInteger(), nullable=False),
        sa.Column("job_name", sa.String(200), nullable=False),
        sa.Column("variant", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("pipeline_url", sa.String(2000), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("identity_hash", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.UniqueConstraint("source_id", "identity_hash", name="uq_ci_build_run_identity"),
    )
    op.create_index(
        "ix_ci_build_runs_source_commit",
        "ci_build_runs",
        ["project_id", "source_id", "commit", "finished_at"],
    )


def downgrade():
    op.drop_table("ci_build_runs")
    op.drop_table("ci_build_tokens")
