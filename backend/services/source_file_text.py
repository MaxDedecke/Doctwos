"""Text einer Quelldatei für die Anzeige, mit derselben Kodierung wie beim Import.

Der Parser speichert je Datei den Codec, mit dem er sie gelesen hat (cp1252-Rückfall, EBCDIC). Liest die Ansicht
dieselben Bytes anders, fehlen Umlaute oder es erscheint Zeichensalat; bei EBCDIC-Sätzen ohne Zeilenende stimmen
dann auch die Zeilen nicht mehr mit den Entitäten und Kanten überein.
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy.orm import Session

from codena_models.database import DocumentChunk, KnowledgeSource, SourceScanFile
from codena_models.source_text import decode_text


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


def indexed_text(db: Session, source: KnowledgeSource, keys: Iterable[str]) -> str | None:
    """Beim Import extrahierter Text einer Datei, aus ihren DocumentChunks; ``None``, wenn nichts indexiert ist.

    Für Formate, die das Backend nicht selbst darstellt (Word 97, RTF, Office/OpenDocument): Der Parser hat sie gelesen,
    das Backend soll seine Leser nicht doppeln.
    """
    rows = (
        db.query(
            DocumentChunk.content,
            DocumentChunk.start_line,
            DocumentChunk.end_line,
            DocumentChunk.metadata_json,
        )
        .filter(DocumentChunk.source_id == source.id, DocumentChunk.file_path.in_(list(keys)))
        .order_by(DocumentChunk.start_line, DocumentChunk.id)
        .all()
    )
    if not rows:
        return None
    pages: dict[object, list[tuple[str, int | None, int | None]]] = {}
    for content, start, end, meta in rows:
        page = (meta or {}).get("page") if isinstance(meta, dict) else None
        pages.setdefault(page, []).append((content or "", start, end))
    order = sorted(pages, key=lambda page: (page is not None, page if isinstance(page, int) else 0))
    return "\n\n".join(assemble_chunks(pages[page]) for page in order)


def assemble_chunks(chunks: Iterable[tuple[str, int | None, int | None]]) -> str:
    """Setzt Chunks wieder zum Text zusammen, Zeile für Zeile an ihrer ursprünglichen Nummer.

    Die Chunks überlappen (``chunk_file`` wiederholt die letzten Zeilen des Vorgängers), und Belege verweisen auf
    ``start_line``/``end_line``. Ein bloßes Aneinanderhängen doppelte Text und verschöbe die zitierten Zeilen.
    Sonderfälle von ``chunk_file``: eine überlange Zeile wird in mehrere Chunks derselben Zeile zerlegt, und kleine
    Chunks werden samt ihrer Überlappung zu einem zusammengelegt.
    """
    lines: dict[int, str] = {}
    for content, start, end in sorted(chunks, key=lambda c: c[1] or 0):
        parts = content.split("\n")
        start = start or (max(lines) + 1 if lines else 1)
        end = end if end and end >= start else start + len(parts) - 1
        if start == end and len(parts) > 1:
            parts = [" ".join(parts)]
        elif len(parts) != end - start + 1:
            parts = _without_inner_overlap(parts, len(parts) - (end - start + 1))
        for offset, line in enumerate(parts):
            number = start + offset
            known = lines.get(number)
            if known is None:
                lines[number] = line
            elif line and line != known and not known.endswith(line):
                # Teilstück einer überlangen Zeile; Überlappungen tragen denselben Text.
                lines[number] = f"{known} {line}"
    if not lines:
        return ""
    return "\n".join(lines.get(number, "") for number in range(1, max(lines) + 1))


def _without_inner_overlap(parts: list[str], extra: int) -> list[str]:
    """Entfernt aus zusammengelegten Chunks die Zeilen, die jeweils den Schluss des Vorgängers wiederholen."""
    kept: list[str] = []
    index = 0
    while index < len(parts):
        if extra > 0:
            repeat = next(
                (
                    size
                    for size in range(min(extra, len(kept)), 0, -1)
                    if parts[index : index + size] == kept[-size:]
                ),
                0,
            )
            if repeat:
                index += repeat
                extra -= repeat
                continue
        kept.append(parts[index])
        index += 1
    return kept
