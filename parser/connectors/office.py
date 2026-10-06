"""
parser/connectors/office.py
===========================
Textextraktion für Office- und Webdokumente, die Ordner-, WebDAV- und Upload-Pfad gemeinsam nutzen:
Excel (.xlsx), PowerPoint (.pptx), OpenDocument (.odt/.ods/.odp) und HTML.

Alles wird zu Klartext mit schlichten Überschriften (``## Blatt: …``, ``## Folie 3``), damit das generische
Chunking daran sinnvoll schneiden kann. Binäre Alt-Formate (.doc) werden nicht geraten: Ein echtes
Word-97-Dokument lässt sich ohne externe Konverter nicht lesen, das sagt die Fehlermeldung ausdrücklich.
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
                cells = [str(value).strip() for value in row if value is not None and str(value).strip()]
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
    _BLOCK = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article", "pre"}

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


def extract_legacy_doc(file_path: str, extract_docx) -> str:
    """``.doc`` kann vieles sein: umbenanntes .docx (ZIP), umbenanntes RTF oder echtes Word 97–2003 (OLE)."""
    if zipfile.is_zipfile(file_path):
        return extract_docx(file_path)
    with open(file_path, "rb") as handle:
        head = handle.read(8)
    if head.lstrip().startswith(b"{\\rtf"):
        from connectors.rtf import extract_rtf_text

        return extract_rtf_text(file_path)
    from connectors.msdoc import extract_doc_text

    return extract_doc_text(file_path)
