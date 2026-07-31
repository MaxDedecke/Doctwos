"""
parser/connectors/extract.py
============================
Gemeinsame Datei-zu-Document Extraktion für Connectoren, die Dateien erst in eine
Temp-Datei herunterladen und danach lokal parsen müssen (aktuell: WebDAV).

Alle Endungen laufen durch ``connectors.folder._extract_text`` (PDF/DOCX/TXT/MD,
inkl. OCR-Fallback für Bild-PDFs).
"""

from connectors.base import Document
from connectors.folder import _extract_text


def extract_cloud_file(
    tmp_path: str,
    ext: str,
    *,
    file_key: str,
    title: str,
    source_type: str,
    url: str | None,
    extra_meta_base: dict,
) -> tuple[list[Document], list[dict]]:
    """Extrahiert eine heruntergeladene Datei und liefert (documents, entities).

    Args:
        tmp_path:        Pfad zur lokalen Temp-Datei (wird nur gelesen, nicht gelöscht).
        ext:             Dateiendung inkl. Punkt (z. B. ".pdf").
        file_key:        Stabiler Schlüssel der Datei (WebDAV-URL) — wird als
                         Document.storage_key genutzt. NIEMALS tmp_path, sonst brechen
                         Delta-Sync/Orphan-Logik.
        title:           Anzeige-Titel (Dateiname bzw. relativer Pfad).
        source_type:     Quell-Label des Connectors.
        url:             Original-Link.
        extra_meta_base: Basis-Metadaten für metadata_json.

    Returns:
        (documents, entities). ``entities`` ist derzeit immer leer — der zweite
        Rückgabewert bleibt erhalten, weil der COBOL-Pfad (AP-4) hier Entities
        anhängen wird.
    """
    content = _extract_text(tmp_path).replace("\x00", "")

    doc = Document(
        title=title,
        content=content,
        url=url,
        source_type=source_type,
        storage_key=file_key,
        extra_meta=extra_meta_base,
    )
    return [doc], []
