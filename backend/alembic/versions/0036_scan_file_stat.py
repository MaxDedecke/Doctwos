"""Dateigröße und Änderungszeit im Datei-Journal: Folder/WebDAV-Scan liest unveränderte Dateien nicht erneut."""

from alembic import op
import sqlalchemy as sa


revision = "0036_scan_file_stat"
down_revision = "0035_profile_deployments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_scan_files", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.add_column("source_scan_files", sa.Column("mtime_ns", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("source_scan_files", "mtime_ns")
    op.drop_column("source_scan_files", "size_bytes")
