"""Store O-242 language and encoding metadata for source scan files."""

from alembic import op
import sqlalchemy as sa


revision = "0022_scan_coverage_metadata"
down_revision = "0021_link_builder_run_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_scan_files", sa.Column("language", sa.String(length=50), nullable=True))
    op.add_column("source_scan_files", sa.Column("encoding", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("source_scan_files", "encoding")
    op.drop_column("source_scan_files", "language")
