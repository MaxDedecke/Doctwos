"""Index code entities by project: without it a small project scans every large project's rows."""

from alembic import op

revision = "0041_code_entities_project_index"
down_revision = "0040_code_file_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_code_entities_project_id", "code_entities", ["project_id"])


def downgrade():
    op.drop_index("ix_code_entities_project_id", table_name="code_entities")
