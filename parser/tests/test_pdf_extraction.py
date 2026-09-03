"""
Regressionstests für O-031: PDF-Extraktion mit OCR-Fallback ist jetzt zwischen
Folder-/WebDAV-Connector und lokalem Datei-Upload geteilt
(`connectors/folder.py::extract_pdf_pages`).

Vor dem Fix hatte `tasks/document.py::process_local_document_async` eine eigene
`pypdf`-Schleife ohne OCR-Fallback -- ein Bild-PDF ohne Text-Layer lieferte dort
keinen Inhalt, obwohl derselbe Upload über den Folder-Connector per OCR erkannt
worden wäre.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from connectors.folder import _extract_text, extract_pdf_pages
from db import SessionLocal
from models.database import DocumentChunk, KnowledgeSource

from conftest import requires_ollama


def _fake_reader(page_texts: list[str | None]) -> MagicMock:
    reader = MagicMock()
    pages = []
    for page_text in page_texts:
        page = MagicMock()
        page.extract_text.return_value = page_text
        pages.append(page)
    reader.pages = pages
    return reader


def test_extract_pdf_pages_returns_per_page_text_when_text_layer_present():
    with patch("pypdf.PdfReader", return_value=_fake_reader(["Seite eins", "Seite zwei"])):
        pages = extract_pdf_pages("/tmp/irrelevant.pdf")

    assert pages == [(1, "Seite eins"), (2, "Seite zwei")]


def test_extract_pdf_pages_falls_back_to_ocr_when_text_layer_empty():
    with patch("pypdf.PdfReader", return_value=_fake_reader(["", None])), \
         patch("connectors.folder.extract_text_from_pdf_ocr", return_value="OCR-erkannter Text") as mock_ocr:
        pages = extract_pdf_pages("/tmp/scan.pdf")

    mock_ocr.assert_called_once_with("/tmp/scan.pdf")
    # Die OCR-Erkennung läuft über die gesamte Datei -- die Seitenzuordnung geht
    # dabei verloren, daher ein einzelner Eintrag mit page_no=None statt einem
    # Eintrag pro PDF-Seite.
    assert pages == [(None, "OCR-erkannter Text")]


def test_folder_extract_text_uses_ocr_fallback_via_extract_pdf_pages():
    with patch("pypdf.PdfReader", return_value=_fake_reader([""])), \
         patch("connectors.folder.extract_text_from_pdf_ocr", return_value="OCR-erkannter Text"):
        content = _extract_text("/tmp/scan.pdf")

    assert content == "OCR-erkannter Text"


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def local_document_source(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "pdf-ocr-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "pdf-ocr-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Gescanntes-Dokument.pdf",
        type="local_document",
        project_id=project_id,
        team_id=team_id,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    yield source

    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.delete(source)
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


@pytest.mark.anyio
@requires_ollama
async def test_process_local_document_applies_ocr_fallback_for_image_only_pdf(db_session, local_document_source):
    from tasks.document import process_local_document_async

    with patch("tasks.document.extract_pdf_pages", return_value=[(None, "OCR-erkannter Rechnungstext")]):
        await process_local_document_async(local_document_source.id, "/tmp/scan.pdf")

    db_session.expire_all()
    db_session.refresh(local_document_source)
    assert local_document_source.sync_status == "completed"

    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == local_document_source.id
    ).all()
    assert len(chunks) == 1
    assert "OCR-erkannter Rechnungstext" in chunks[0].content
    # Die OCR-Erkennung kennt keine Seitenzahl -- muss als None statt als
    # fehlendes/falsches Feld ankommen.
    assert chunks[0].metadata_json["page"] is None
