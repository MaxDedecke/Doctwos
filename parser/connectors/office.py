"""
parser/connectors/office.py
===========================
Textextraktion für Office- und Webdokumente, die Ordner-, WebDAV- und Upload-Pfad gemeinsam nutzen:
Excel (.xlsx), PowerPoint (.pptx), OpenDocument (.odt/.ods/.odp) und HTML.

Alles wird zu Klartext mit schlichten Überschriften (``## Blatt: …``, ``## Folie 3``), damit das generische
Chunking daran sinnvoll schneiden kann. Binäres Word (.doc, Word 6 bis 2003) liest ``connectors/msdoc.py``.
"""

import zipfile
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

# Obergrenze gelesener Zellen je Arbeitsmappe: sehr große Exporte würden sonst Speicher und Embedding-Zeit sprengen.
XLSX_MAX_CELLS = 500_000

OFFICE_EXTENSIONS = {".xlsx", ".pptx", ".odt", ".ods", ".odp", ".html", ".htm", ".csv", ".rtf"}


class UnsupportedFormat(ValueError):
    """Dateiformat, das ohne zusätzliche Software nicht lesbar ist (mit Hinweis für den Nutzer)."""


def extract_xlsx_text(file_path: str) -> str:
    import openpyxl

    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    lines: list[str] = []
    cells_read = 0
    try:
        for sheet in workbook.worksheets:
            lines.append(f"## Blatt: {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                cells = [
                    str(value).strip() for value in row if value is not None and str(value).strip()
                ]
                cells_read += len(row)
                if cells:
                    lines.append(" | ".join(cells))
                if cells_read >= XLSX_MAX_CELLS:
                    lines.append(f"[Abgeschnitten: mehr als {XLSX_MAX_CELLS} Zellen]")
                    return "\n".join(lines)
    finally:
        workbook.close()
    return "\n".join(lines)


def extract_pptx_text(file_path: str) -> str:
    from pptx import Presentation

    presentation = Presentation(file_path)
    lines: list[str] = []
    for number, slide in enumerate(presentation.slides, start=1):
        lines.append(f"## Folie {number}")
        for shape in slide.shapes:
            if shape.has_text_frame:
                lines.extend(p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        lines.append(" | ".join(cells))
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                lines.append(f"Notizen: {notes}")
    return "\n".join(lines)


class _HtmlText(HTMLParser):
    _SKIP = {"script", "style", "head", "noscript"}
    _BLOCK = {
        "p",
        "div",
        "li",
        "tr",
        "br",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "table",
        "section",
        "article",
        "pre",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in ("td", "th"):
            self._parts.append(" | ")
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._parts).split("\n"))
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    parser = _HtmlText()
    parser.feed(html)
    return parser.text()


def extract_odf_text(file_path: str) -> str:
    """Text aus OpenDocument-Dateien (.odt/.ods/.odp): ``content.xml`` im ZIP, Absätze und Überschriften."""
    with zipfile.ZipFile(file_path) as archive:
        root = ET.fromstring(archive.read("content.xml"))
    lines: list[str] = []
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in ("p", "h"):
            text = "".join(element.itertext()).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def extract_legacy_doc(file_path: str, extract_docx) -> str:
    """``.doc`` kann vieles sein: echtes Word 6–2003 (OLE), umbenanntes .docx (ZIP), RTF oder HTML/MHTML.

    Erkannt wird am Dateikopf, nicht mit ``zipfile.is_zipfile``: Ab Word 2007 als .doc gespeicherte Dateien tragen
    ein gezipptes Design (themeData) in sich, das ``is_zipfile`` für ein ZIP-Archiv hält; diese Dateien landeten
    sonst im .docx-Leser und scheiterten.
    """
    with open(file_path, "rb") as handle:
        head = handle.read(1024)
    if head.startswith(b"PK\x03\x04"):
        return extract_docx(file_path)
    if not head.startswith(_OLE_MAGIC):
        start = head.lstrip(b"\xef\xbb\xbf \t\r\n")
        if start.startswith(b"{\\rtf"):
            from connectors.rtf import extract_rtf_text

            return extract_rtf_text(file_path)
        if _looks_like_html(start):
            return _html_export_text(file_path)
    from connectors.msdoc import extract_doc_text

    return extract_doc_text(file_path)


def _looks_like_html(start: bytes) -> bool:
    """Word-„Webseite“, Confluence- und Jira-„Export nach Word“: HTML oder MHTML mit Endung .doc."""
    lower = start[:1024].lower()
    return lower.startswith((b"<", b"mime-version:")) or b"<html" in lower


def _html_export_text(file_path: str) -> str:
    import email
    from email import policy

    from connectors.textio import decode_text

    with open(file_path, "rb") as handle:
        data = handle.read()
    if not data.lstrip()[:1].startswith(b"<"):
        message = email.message_from_bytes(data, policy=policy.default)
        part = next((p for p in message.walk() if p.get_content_type() == "text/html"), None)
        if part is not None:
            payload = part.get_payload(decode=True) or b""
            charset = part.get_content_charset()
            try:
                return html_to_text(payload.decode(charset) if charset else decode_text(payload))
            except (LookupError, UnicodeDecodeError):
                return html_to_text(decode_text(payload))
    return html_to_text(decode_text(data))
