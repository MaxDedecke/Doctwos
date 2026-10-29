"""Store the graph overview backbone of code relationships aggregated to file edges."""

from alembic import op
import sqlalchemy as sa

revision = "0039_code_file_edges"
down_revision = "0038_source_indexed_at"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "code_file_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("src_project_id", sa.Integer(), nullable=True),
        sa.Column(
            "src_source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("src_file_path", sa.String(), nullable=False),
        sa.Column("dst_project_id", sa.Integer(), nullable=True),
        sa.Column(
            "dst_source_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("dst_file_path", sa.String(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("edge_types", sa.JSON(), nullable=False),
        sa.Column("sample_edge_ids", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("src_degree", sa.Integer(), nullable=False),
        sa.Column("dst_degree", sa.Integer(), nullable=False),
        sa.Column("total_pairs", sa.Integer(), nullable=False),
    )
    op.create_index("ix_code_file_edges_project", "code_file_edges", ["project_id"])


def downgrade():
    op.drop_index("ix_code_file_edges_project", table_name="code_file_edges")
    op.drop_table("code_file_edges")
