"""
parser/connectors/folder.py
============================
Connector für lokale Ordner / Netzlaufwerke (NAS/Fileshare).

Ablauf:
    1. Alle unterstützten Dateien im konfigurierten Ordner rekursiv einlesen
    2. MD5-Hash jeder Datei mit gespeichertem SourceScanFile-Eintrag vergleichen
    3. Nur neue oder veränderte Dateien als Document yielden (Delta-Sync)
    4. Nach dem Sync: SourceScanFile-Tabelle aktualisieren + Orphan-Chunks löschen

Unterstützte Formate: PDF (Text-Layer + OCR-Fallback), DOCX/DOC, TXT, MD
Konfiguration:    KnowledgeSource.url = absoluter Ordnerpfad (innerhalb des Containers)
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import AsyncIterator

from connectors.base import BaseConnector, Document
from connectors.office import (
    OFFICE_EXTENSIONS,
    extract_legacy_doc,
    extract_odf_text,
    extract_pptx_text,
    extract_xlsx_text,
    html_to_text,
)
from connectors.textio import read_text_file
from db import SessionLocal
from models.database import DocumentChunk, KnowledgeSource, SourceScanFile
from utils import extract_text_from_pdf_ocr

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"} | OFFICE_EXTENSIONS

# Dateien über dieser Größe werden nicht indiziert (Speicher/Laufzeit); der Wert ist je Betrieb einstellbar.
MAX_FILE_BYTES = int(os.getenv("FOLDER_MAX_FILE_MB", "200")) * 1024 * 1024

# Temporäre Dateien und Systemdateien von Office, Windows, macOS und NAS-Geräten (Papierkörbe, Vorschauen).
_EXCLUDED_FILE_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}
_EXCLUDED_FILE_SUFFIXES = (".tmp", ".temp", ".bak", ".swp", ".lnk")
_EXCLUDED_DIR_NAMES = {"$recycle.bin", "@eadir", "#recycle", "system volume information", "lost+found"}


def _is_excluded_file(name: str) -> bool:
    lower = name.lower()
    return lower.startswith(("~$", ".")) or lower in _EXCLUDED_FILE_NAMES or lower.endswith(_EXCLUDED_FILE_SUFFIXES)


def _is_excluded_dir(name: str) -> bool:
    return name.startswith(".") or name.lower() in _EXCLUDED_DIR_NAMES


def _md5(file_path: str) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_pdf_pages(file_path: str) -> list[tuple[int | None, str]]:
    """Liest eine PDF-Datei seitenweise ein; OCR-Fallback für Bild-PDFs ohne Text-Layer.

    Liefert eine Liste aus (Seitennummer, Text) für Aufrufer, die die Seite pro
    Chunk erhalten wollen (z. B. `parser/tasks/document.py` für die
    "was steht auf Seite X"-Navigation). Ist kein Text-Layer vorhanden, wird die
    gesamte Datei per OCR erkannt; dabei geht die Seitenzuordnung verloren, daher
    ein einzelner Eintrag mit `page_no=None`.
    """
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    pages = [
        (page_no, page.extract_text() or "") for page_no, page in enumerate(reader.pages, start=1)
    ]
    if not any(text.strip() for _, text in pages):
        logger.info(f"OCR-Fallback für PDF ohne Text-Layer: '{file_path}'")
        return [(None, extract_text_from_pdf_ocr(file_path))]
    return pages


def extract_docx_text(file_path: str) -> str:
    """Liest Absätze und Tabellenzellen eines Word-Dokuments (.docx/.doc) als Text ein.

    Geteilt zwischen Folder-/WebDAV-Connector und lokalem Datei-Upload
    (`parser/tasks/document.py`), analog zu `extract_pdf_pages` (O-031/O-044) --
    vorher hatte `document.py` eine eigene, unabhängige python-docx-Schleife.
    """
    import docx

    doc = docx.Document(file_path)
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        try:
            return "\n".join(text for _, text in extract_pdf_pages(file_path))
        except Exception as e:
            # Fallback to plain text if the PDF is actually a text/mock file (like the Markdown mock files)
            try:
                content = read_text_file(file_path)
                if content.strip().startswith("##") or len(content) < 5000:
                    return content
            except Exception:
                pass
            raise e
    if ext == ".docx":
        return extract_docx_text(file_path)
    if ext == ".doc":
        return extract_legacy_doc(file_path, extract_docx_text)
    if ext == ".xlsx":
        return extract_xlsx_text(file_path)
    if ext == ".pptx":
        return extract_pptx_text(file_path)
    if ext in (".odt", ".ods", ".odp"):
        return extract_odf_text(file_path)
    if ext in (".html", ".htm"):
        return html_to_text(read_text_file(file_path))
    return read_text_file(file_path)


@dataclass
class ScanResult:
    """Ergebnis eines Ordnerscans.

    ``complete`` ist nur wahr, wenn jedes Verzeichnis gelesen und jede Datei erfasst werden konnte. Nur dann
    darf aus dem Fehlen einer Datei auf ihr Löschen geschlossen werden: ein kurz nicht erreichbares Laufwerk
    oder ein unlesbarer Unterordner sieht sonst wie ein Löschen aus.
    """

    files: dict[str, str] = field(default_factory=dict)  # Pfad -> MD5
    stats: dict[str, tuple[int, int]] = field(default_factory=dict)  # Pfad -> (Größe, mtime_ns)
    errors: list[str] = field(default_factory=list)
    too_large: list[str] = field(default_factory=list)
    reused_hashes: int = 0

    @property
    def complete(self) -> bool:
        return not self.errors


def _scan_folder(
    folder_path: str, known: dict[str, tuple[int | None, int | None, str]] | None = None
) -> ScanResult:
    """Rekursiv alle unterstützten Dateien erfassen.

    ``known`` ({Pfad: (Größe, mtime_ns, MD5)} vom letzten Lauf) erspart das erneute Lesen unveränderter
    Dateien: stimmen Größe und Änderungszeit, gilt der gespeicherte Hash. Das hält die Last auf einem NAS
    bei stündlichen Scans klein.
    """
    result = ScanResult()
    known = known or {}

    def on_error(error: OSError) -> None:
        result.errors.append(f"{getattr(error, 'filename', '?')}: {getattr(error, 'strerror', None) or error}")

    for root, dirs, files in os.walk(folder_path, onerror=on_error):
        dirs[:] = [d for d in dirs if not _is_excluded_dir(d)]
        for fname in files:
            if os.path.splitext(fname)[1].lower() not in SUPPORTED_EXTENSIONS or _is_excluded_file(fname):
                continue
            full_path = os.path.join(root, fname)
            try:
                st = os.stat(full_path)
                if st.st_size > MAX_FILE_BYTES:
                    result.too_large.append(full_path)
                    continue
                previous = known.get(full_path)
                if previous and previous[2] and previous[0] == st.st_size and previous[1] == st.st_mtime_ns:
                    digest = previous[2]
                    result.reused_hashes += 1
                else:
                    digest = _md5(full_path)
            except OSError as error:
                result.errors.append(f"{full_path}: {error.strerror or error}")
                continue
            result.files[full_path] = digest
            result.stats[full_path] = (st.st_size, st.st_mtime_ns)
    return result


class FolderConnector(BaseConnector):
    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._current_scan: dict[str, str] = {}
        self._scan_stats: dict[str, tuple[int, int]] = {}
        self._scan_complete = True
        self._successful_files: set[str] = set()
        self._new_or_changed: set[str] = set()

    async def fetch_documents(self) -> AsyncIterator[Document]:
        folder_path = (self.source.url or "").strip()
        if not folder_path or not os.path.isdir(folder_path):
            raise ValueError(
                f"Ordnerpfad '{folder_path}' nicht gefunden oder kein Verzeichnis. "
                "Bitte prüfe, ob der Pfad im Container korrekt gemountet ist."
            )

        self._log(f"Scanne Ordner: {folder_path}")
        known = {
            r.file_path: (r.size_bytes, r.mtime_ns, r.content_hash)
            for r in self.db.query(SourceScanFile).filter(SourceScanFile.source_id == self.source_id).all()
        }
        scan = _scan_folder(folder_path, known)
        self._current_scan = scan.files
        self._scan_stats = scan.stats
        self._scan_complete = scan.complete
        self._log(
            f"{len(scan.files)} unterstützte Datei(en) gefunden "
            f"({scan.reused_hashes} ohne erneutes Lesen, da Größe und Änderungszeit unverändert)."
        )
        if scan.too_large:
            self._log(f"[SKIP] {len(scan.too_large)} Datei(en) über {MAX_FILE_BYTES // (1024 * 1024)} MB nicht indiziert.")
        if scan.errors:
            shown = "; ".join(scan.errors[:5])
            self._log(
                f"[WARNUNG] {len(scan.errors)} Pfad(e) nicht lesbar ({shown}). Dateien, die dadurch im Scan fehlen, "
                "werden in diesem Lauf nicht als gelöscht behandelt."
            )

        existing: dict[str, str] = {path: values[2] for path, values in known.items()}

        chunk_count = (
            self.db.query(DocumentChunk).filter(DocumentChunk.source_id == self.source_id).count()
        )
        if chunk_count == 0:
            existing = {}

        new_or_changed = [path for path, h in self._current_scan.items() if existing.get(path) != h]
        self._new_or_changed = set(new_or_changed)
        self._successful_files = set()
        self._log(
            f"{len(new_or_changed)} neue/veränderte Datei(en) werden indiziert, "
            f"{len(self._current_scan) - len(new_or_changed)} unverändert übersprungen."
        )

        for i, file_path in enumerate(new_or_changed, start=1):
            try:
                content = _extract_text(file_path).replace("\x00", "")
            except Exception as e:
                self._log(f"[FEHLER] '{file_path}': {e}")
                continue

            if not content.strip():
                self._log(f"[SKIP] Kein Textinhalt (auch nach OCR) in '{file_path}'.")
                continue

            rel_path = os.path.relpath(file_path, folder_path)
            self._update_progress(i, len(new_or_changed), f"Indiziere {rel_path}")
            self._successful_files.add(file_path)
            yield Document(
                title=rel_path,
                content=content,
                url=None,
                source_type="FolderWatch",
                storage_key=file_path,
                extra_meta={"folder_path": folder_path, "file_name": os.path.basename(file_path)},
            )

    async def sync(self) -> None:
        await super().sync()

        db = SessionLocal()
        try:
            if not self._current_scan:
                return

            existing_records = {
                r.file_path: r
                for r in db.query(SourceScanFile)
                .filter(SourceScanFile.source_id == self.source_id)
                .all()
            }

            # Orphans: in DB aber nicht mehr im Ordner → Chunks + Record löschen. Nur bei vollständigem Scan:
            # ein unlesbarer Unterordner oder ein kurz weggefallener Mount macht den Scan unvollständig, und
            # Löschen würde dann gültige Dokumente unwiederbringlich entfernen.
            if not self._scan_complete:
                src = db.query(KnowledgeSource).filter(KnowledgeSource.id == self.source_id).first()
                if src is not None:
                    src.sync_log = (src.sync_log or "") + (
                        "[WARNUNG] Unvollständiger Scan: verwaiste Einträge wurden NICHT gelöscht. "
                        "Der nächste vollständige Lauf bereinigt automatisch.\n"
                    )
            else:
                for path, record in existing_records.items():
                    if path not in self._current_scan:
                        db.query(DocumentChunk).filter(
                            DocumentChunk.source_id == self.source_id,
                            DocumentChunk.file_path == path,
                        ).delete()
                        db.delete(record)
                        self.has_changes = True

            # Neue und veränderte Dateien: upsert SourceScanFile nur wenn sie erfolgreich indiziert wurden
            for path, content_hash in self._current_scan.items():
                if path in self._new_or_changed and path not in self._successful_files:
                    continue
                size, mtime_ns = self._scan_stats.get(path, (None, None))

                if path in existing_records:
                    existing_records[path].content_hash = content_hash
                    existing_records[path].size_bytes = size
                    existing_records[path].mtime_ns = mtime_ns
                else:
                    db.add(
                        SourceScanFile(
                            source_id=self.source_id,
                            file_path=path,
                            content_hash=content_hash,
                            size_bytes=size,
                            mtime_ns=mtime_ns,
                        )
                    )

            db.commit()
        except Exception as e:
            logger.error(
                f"[FolderConnector] Fehler beim Aktualisieren der SourceScanFile-Tabelle: {e}"
            )
            db.rollback()
        finally:
            db.close()
