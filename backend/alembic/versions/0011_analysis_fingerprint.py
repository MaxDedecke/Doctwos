"""O-122: pro Quelldatei die Eingaben der Strukturanalyse persistieren.

Bestehende Zeilen bleiben absichtlich NULL. Beim nächsten Sync stimmt ihr
fehlender Fingerprint mit keinem berechneten Wert überein und sie werden genau
einmal mit dem vollständigen Analysevertrag neu verarbeitet; eine erfundene
Rückbefüllung könnte alte Profile oder Bibliotheken fälschlich als aktuell
ausgeben.
"""

from alembic import op
import sqlalchemy as sa


revision = "0011_analysis_fingerprint"
down_revision = "0010_analysis_status_vocabulary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_scan_files",
        sa.Column("analysis_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_scan_files", "analysis_fingerprint")
