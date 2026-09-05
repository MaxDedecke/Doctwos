"""
Regressionstests für O-044: Word-Extraktion (.docx/.doc) ist jetzt zwischen
Folder-/WebDAV-Connector und lokalem Datei-Upload geteilt
(`connectors/folder.py::extract_docx_text`), analog zu `extract_pdf_pages`
(O-031). Vorher hatte `tasks/document.py::process_local_document_async` eine
eigene, unabhängige python-docx-Schleife, und der Direkt-Upload-Endpunkt
lehnte .docx/.doc serverseitig komplett ab, obwohl der Folder-/WebDAV-Connector
dieselben Formate schon immer einlesen konnte.
"""

from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from connectors.folder import _extract_text, extract_docx_text
from db import SessionLocal
from models.database import DocumentChunk, KnowledgeSource

from conftest import requires_ollama


def _fake_docx_document(paragraph_texts: list[str], table_rows: list[list[str]] | None = None) -> MagicMock:
    doc = MagicMock()
    doc.paragraphs = [MagicMock(text=text) for text in paragraph_texts]
    doc.tables = []
    if table_rows:
        table = MagicMock()
        table.rows = []
        for row_cells in table_rows:
            row = MagicMock()
            row.cells = [MagicMock(text=cell) for cell in row_cells]
            table.rows.append(row)
        doc.tables.append(table)
    return doc


def test_extract_docx_text_joins_paragraphs():
    with patch("docx.Document", return_value=_fake_docx_document(["Erster Absatz", "Zweiter Absatz"])):
        content = extract_docx_text("/tmp/handbuch.docx")

    assert content == "Erster Absatz\nZweiter Absatz"


def test_extract_docx_text_includes_table_cells():
    with patch("docx.Document", return_value=_fake_docx_document(
        ["Einleitung"], table_rows=[["Spalte A", "Spalte B"]],
    )):
        content = extract_docx_text("/tmp/handbuch.docx")

    assert content == "Einleitung\nSpalte A | Spalte B"


def test_folder_extract_text_uses_extract_docx_text_for_doc_and_docx():
    with patch("connectors.folder.extract_docx_text", return_value="geteilter Word-Text") as mock_extract:
        content = _extract_text("/tmp/vertrag.doc")

    mock_extract.assert_called_once_with("/tmp/vertrag.doc")
    assert content == "geteilter Word-Text"


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def local_docx_source(db_session):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "docx-upload-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"),
        {"name": "docx-upload-test-project", "team_id": team_id},
    ).scalar_one()

    source = KnowledgeSource(
        name="Handbuch.docx",
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
async def test_process_local_document_uses_shared_extract_docx_text(db_session, local_docx_source):
    from tasks.document import process_local_document_async

    with patch("tasks.document.extract_docx_text", return_value="Aus geteilter Funktion extrahierter Text") as mock_extract:
        await process_local_document_async(local_docx_source.id, "/tmp/Handbuch.docx")

    mock_extract.assert_called_once_with("/tmp/Handbuch.docx")

    db_session.expire_all()
    db_session.refresh(local_docx_source)
    assert local_docx_source.sync_status == "completed"

    chunks = db_session.query(DocumentChunk).filter(
        DocumentChunk.source_id == local_docx_source.id
    ).all()
    assert len(chunks) == 1
    assert "Aus geteilter Funktion extrahierter Text" in chunks[0].content
