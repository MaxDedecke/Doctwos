"""O-137: praezise Copybook-Abhaengigkeiten je Datei statt konservativer
Gesamtbestands-Invalidierung.

`copybook_dependencies` haelt die zuletzt beim erfolgreichen Parsen entdeckte,
eindeutig aufgeloeste Menge an Copybooks fest ({pfad: content_hash}), auf die
diese Datei (transitiv) angewiesen ist. connectors/git.py nutzt das, um beim
naechsten Sync nur diese Teilmenge statt des gesamten Copybook-Bestands in den
Analyse-Fingerprint einzubeziehen - eine Aenderung an einem NICHT verwendeten
Copybook loest dann keinen unnoetigen Reparse mehr aus. NULL (kein bisheriger
Eintrag oder eine Datei ohne COBOL/Copybook-Sprache) bedeutet weiterhin
konservatives Verhalten (voller Bestand im Fingerprint).
"""

from alembic import op
import sqlalchemy as sa


revision = "0013_copybook_dependencies"
down_revision = "0012_evidence_variants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_scan_files",
        sa.Column("copybook_dependencies", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_scan_files", "copybook_dependencies")
