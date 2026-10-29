"""Store group nodes of the graph overview: files grouped by coupling, topics first."""

from alembic import op
import sqlalchemy as sa

revision = "0040_code_file_groups"
down_revision = "0039_code_file_edges"
branch_labels = None
depends_on = None


def _project():
    return sa.Column(
        "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )


def upgrade():
    op.create_table(
        "code_file_groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        _project(),
        sa.Column("group_key", sa.String(), nullable=False),
        sa.Column("parent_key", sa.String(), nullable=True),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column(
            "topic_id", sa.Integer(), sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("label", sa.String(), nullable=False),
        sa.Column("path_prefix", sa.String(), nullable=False),
        sa.Column("central_file", sa.String(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_code_file_groups_project", "code_file_groups", ["project_id"])
    op.create_table(
        "code_file_group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        _project(),
        sa.Column("group_key", sa.String(), nullable=False),
        sa.Column("file_project_id", sa.Integer(), nullable=True),
        sa.Column(
            "file_source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("file_path", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_code_file_group_members_project_group",
        "code_file_group_members",
        ["project_id", "group_key"],
    )
    op.create_index(
        "ix_code_file_group_members_file",
        "code_file_group_members",
        ["file_source_id", "file_path"],
    )
    op.create_table(
        "code_group_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        _project(),
        sa.Column("src_group_key", sa.String(), nullable=False),
        sa.Column("dst_group_key", sa.String(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("file_edge_count", sa.Integer(), nullable=False),
        sa.Column("edge_types", sa.JSON(), nullable=False),
    )
    op.create_index("ix_code_group_edges_project", "code_group_edges", ["project_id"])


def downgrade():
    op.drop_table("code_group_edges")
    op.drop_table("code_file_group_members")
    op.drop_table("code_file_groups")
