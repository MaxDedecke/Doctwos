"""Make insight maintenance searchable, assigned and bounded."""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0048_insight_team_workflow"
down_revision = "0047_ci_build_reports"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("owner_id", "reviewer_id"):
        op.add_column("insights", sa.Column(name, sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_insights_" + name, "insights", "users", [name], ["id"], ondelete="SET NULL"
        )
    op.add_column(
        "insights", sa.Column("priority", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "insights", sa.Column("work_revision", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "insights", sa.Column("workflow_history", sa.JSON(), nullable=False, server_default="[]")
    )
    op.add_column("insights", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "insights",
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_check_constraint("ck_insights_priority", "insights", "priority BETWEEN 0 AND 3")
    op.create_index(
        "ix_insights_worklist", "insights", ["project_id", "status", "priority", "due_at", "id"]
    )
    op.create_index("ix_insights_owner", "insights", ["project_id", "owner_id", "id"])
    op.execute(
        "CREATE INDEX ix_insights_search ON insights USING gin "
        "(to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(content, '')))"
    )
    op.execute(
        "CREATE INDEX ix_insights_evidence_gin ON insights USING gin ((evidence_json::jsonb))"
    )
    op.execute(
        "CREATE INDEX ix_insights_bindings_gin ON insights USING gin ((version_bindings::jsonb))"
    )
    op.create_table(
        "insight_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "insight_id",
            sa.Integer(),
            sa.ForeignKey("insights.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("cycle_key", sa.String(80), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "insight_id", "user_id", "kind", "cycle_key", name="uq_insight_notification_cycle"
        ),
    )
    op.create_index(
        "ix_insight_notifications_inbox",
        "insight_notifications",
        ["project_id", "user_id", "read_at", "id"],
    )
    op.create_table(
        "insight_embeddings",
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "insight_id",
            sa.Integer(),
            sa.ForeignKey("insights.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("profile_key", sa.String(64), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_insight_embeddings_profile", "insight_embeddings", ["profile_key"])
    op.create_index(
        "ix_insight_embeddings_scope", "insight_embeddings", ["project_id", "profile_key"]
    )
    op.create_index(
        "ix_insight_embeddings_hnsw",
        "insight_embeddings",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade():
    op.drop_table("insight_embeddings")
    op.drop_table("insight_notifications")
    op.drop_index("ix_insights_search", table_name="insights")
    op.drop_index("ix_insights_evidence_gin", table_name="insights")
    op.drop_index("ix_insights_bindings_gin", table_name="insights")
    op.drop_index("ix_insights_owner", table_name="insights")
    op.drop_index("ix_insights_worklist", table_name="insights")
    op.drop_constraint("ck_insights_priority", "insights", type_="check")
    for name in ("owner_id", "reviewer_id"):
        op.drop_constraint("fk_insights_" + name, "insights", type_="foreignkey")
    for name in (
        "owner_id",
        "reviewer_id",
        "priority",
        "due_at",
        "updated_at",
        "work_revision",
        "workflow_history",
    ):
        op.drop_column("insights", name)
