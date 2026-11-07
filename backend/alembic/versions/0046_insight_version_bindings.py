"""Keep historical approvals unbound until their source versions are reviewed."""

from alembic import op
import sqlalchemy as sa

revision = "0046_insight_version_bindings"
down_revision = "0045_unresolved_reference_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("insights", sa.Column("version_bindings", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("insights", "version_bindings")
