"""Text einer Quelldatei für die Anzeige, mit derselben Kodierung wie beim Import.

Der Parser speichert je Datei den Codec, mit dem er sie gelesen hat (cp1252-Rückfall, EBCDIC). Liest die Ansicht
dieselben Bytes anders, fehlen Umlaute oder es erscheint Zeichensalat; bei EBCDIC-Sätzen ohne Zeilenende stimmen
dann auch die Zeilen nicht mehr mit den Entitäten und Kanten überein.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from doctus_models.database import KnowledgeSource, SourceScanFile
from doctus_models.source_text import decode_text


def read_source_text(db: Session, source: KnowledgeSource, path: str | None, file_path: str) -> str:
    with open(file_path, "rb") as f:
        raw = f.read()
    encoding = None
    if path and (source.type or "").lower() == "git":
        encoding = (
            db.query(SourceScanFile.encoding)
            .filter(SourceScanFile.source_id == source.id, SourceScanFile.file_path == path)
            .scalar()
        )
    try:
        text = decode_text(raw, encoding or "utf-8", errors="ignore")
    except LookupError:
        text = raw.decode("utf-8", errors="ignore")
    return text.replace("\r\n", "\n").replace("\r", "\n")
