"""O-120: SourceScanFile.parse_status auf die neue Vollständigkeits-Wortliste
(core.model.AnalysisStatus) migrieren, statt eine gemischte Alt-/Neu-Wortliste
im selben Feld stehen zu lassen.

Reine Datenmigration, kein Schemawechsel (parse_status blieb schon immer eine
ungeprüfte String-Spalte). Zuordnung für Bestandszeilen:
  - 'ok'            -> 'complete'      (kein struktureller Makel gemeldet)
  - 'fallback_text'  -> 'partial'       (Näherung: die alte Wortliste hatte
    KEIN eigenes Textfallback-Signal -- 'fallback_text' deckte gleichermaßen
    "Struktur mit Fehlern" (jetzt 'partial') und "gar keine Struktur, reiner
    Volltext" (jetzt 'text_fallback', F-029) ab. Ohne den seit O-119 in
    ParseResult.diagnostics/den Fallback-Chunk-Marker mitgeschriebenen Beleg
    lässt sich das für Altzeilen nicht mehr rekonstruieren -- 'partial' ist
    die vorsichtigere Näherung (impliziert nicht "keine Struktur vorhanden"),
    ein erneuter Sync ersetzt den Wert ohnehin durch die präzise Klassifikation.
  - 'error'          bleibt 'error'     (DB-seitiger Persistenzfehler, eine
    von core.model.AnalysisStatus unabhängige Dimension, siehe Spaltenkommentar).
  - NULL             bleibt NULL        (kein Strukturparser beteiligt, z.B.
    nicht-COBOL-Dateien -- weiterhin "nicht zutreffend", kein Status).
'skipped' entsteht erst durch künftige Syncs (Binärformat/Größenlimit/kein
UTF-8, siehe GitConnector._record_skip) -- für Bestandszeilen gibt es dafür
keine rekonstruierbare Evidenz, deshalb keine rückwirkende Zuordnung.
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_analysis_status_vocabulary"
down_revision = "0009_chat_feedback_diagnostics"
branch_labels = None
depends_on = None

_scan_files = sa.table(
    "source_scan_files",
    sa.column("parse_status", sa.String),
)


def upgrade() -> None:
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "ok")
        .values(parse_status="complete")
    )
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "fallback_text")
        .values(parse_status="partial")
    )


def downgrade() -> None:
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "complete")
        .values(parse_status="ok")
    )
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "partial")
        .values(parse_status="fallback_text")
    )
    # 'text_fallback'/'skipped' existierten vor O-120 nicht -- die nächstbeste
    # Downgrade-Näherung ist wieder 'fallback_text' (deckte beide vormals ab).
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "text_fallback")
        .values(parse_status="fallback_text")
    )
    op.execute(
        _scan_files.update()
        .where(_scan_files.c.parse_status == "skipped")
        .values(parse_status=None)
    )
