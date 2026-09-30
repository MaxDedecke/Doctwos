"""Hochgeladene Dokumente: Abschnittsgrenzen, Metadaten, Fehlerstatus und Chunk-Kandidaten pro Stelle."""

import os

import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEntity, DocumentChunk, KnowledgeSource
from tasks import document as document_task
from tasks.link_builder import _candidate_key, _pass_keyword

MD = (
    "# Autorisierung\n\n"
    + "Einleitung zum Autorisierungsdienst. " * 6 + "\n\n"
    "## Entscheidung\n\n"
    + "COPAUA0C prueft das verfuegbare Limit und lehnt bei Ueberschreitung ab. " * 5 + "\n\n"
    "## Antwort\n\n"
    + "Die Antwort geht ueber MQPUT1 an die Antwort-Queue. " * 5 + "\n"
)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def upload(db_session, tmp_path):
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:n, now()) RETURNING id"), {"n": f"upload-team-{tmp_path.name}"}
    ).scalar_one()
    project_id = db_session.execute(
        text("INSERT INTO projects (name, team_id, created_at) VALUES (:n, :t, now()) RETURNING id"),
        {"n": f"upload-project-{tmp_path.name}", "t": team_id},
    ).scalar_one()
    source = KnowledgeSource(name="Autorisierung.md", type="Local", project_id=project_id, team_id=team_id, embedding_model="test-embed")
    db_session.add(source)
    db_session.commit()
    path = tmp_path / "autorisierung.md"
    path.write_text(MD, encoding="utf-8")
    yield source, str(path), project_id
    db_session.rollback()
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.execute(text("DELETE FROM knowledge_sources WHERE id = :id"), {"id": source.id})
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def _patch_embedding(monkeypatch, fail=False):
    async def fake_embedding(content, model=None):
        if fail:
            raise ConnectionError("Embedding-Dienst nicht erreichbar")
        return [0.1] * 1024

    async def no_pull(model):
        return None

    monkeypatch.setattr(document_task, "get_embedding", fake_embedding)
    monkeypatch.setattr(document_task, "ensure_model_pulled", no_pull)


def _chunks(db, source_id):
    db.expire_all()
    return db.query(DocumentChunk).filter(DocumentChunk.source_id == source_id).order_by(DocumentChunk.start_line).all()


@pytest.mark.asyncio
async def test_markdown_chunks_follow_headings_and_carry_section_metadata(db_session, upload, monkeypatch):
    source, path, _project_id = upload
    _patch_embedding(monkeypatch)

    await document_task.process_local_document_async(source.id, path)

    db_session.refresh(source)
    assert source.sync_status == "completed"
    chunks = _chunks(db_session, source.id)
    assert len(chunks) >= 3
    sections = [(c.metadata_json or {}).get("section") for c in chunks]
    assert "Autorisierung > Entscheidung" in sections and "Autorisierung > Antwort" in sections
    for chunk in chunks:
        meta = chunk.metadata_json
        assert meta["title"] == "Autorisierung.md" and meta["source_type"] == "Local"
        assert chunk.start_line and chunk.end_line >= chunk.start_line
    # Kein Chunk mischt zwei Abschnitte: jede Überschrift beginnt einen neuen Chunk.
    starts = {c.start_line for c in chunks}
    assert 5 in starts or any(c.start_line <= 5 <= c.end_line for c in chunks)
    decision_lines = [c for c in chunks if (c.metadata_json or {}).get("section") == "Autorisierung > Entscheidung"]
    assert all("MQPUT1" not in c.content for c in decision_lines)


@pytest.mark.asyncio
async def test_failed_embedding_marks_source_as_error_instead_of_completed(db_session, upload, monkeypatch):
    source, path, _project_id = upload
    _patch_embedding(monkeypatch, fail=True)

    await document_task.process_local_document_async(source.id, path)

    db_session.refresh(source)
    assert source.sync_status == "error"
    assert "Embedding fehlgeschlagen" in (source.last_error or "")
    assert _chunks(db_session, source.id) == []


@pytest.mark.asyncio
async def test_failed_reindex_keeps_previous_chunks(db_session, upload, monkeypatch):
    source, path, _project_id = upload
    _patch_embedding(monkeypatch)
    await document_task.process_local_document_async(source.id, path)
    before = [(c.start_line, c.content) for c in _chunks(db_session, source.id)]
    assert before

    db_session.refresh(source)
    source.sync_status = "completed"
    db_session.commit()
    _patch_embedding(monkeypatch, fail=True)
    await document_task.process_local_document_async(source.id, path)

    db_session.refresh(source)
    assert source.sync_status == "error"
    assert [(c.start_line, c.content) for c in _chunks(db_session, source.id)] == before


@pytest.mark.asyncio
async def test_each_passage_of_an_uploaded_document_is_its_own_link_candidate(db_session, upload, monkeypatch):
    source, path, project_id = upload
    _patch_embedding(monkeypatch)
    # Zwei Abschnitte erwähnen den Namen; beide müssen einzeln Kandidat bleiben.
    extra = "\n## Betrieb\n\n" + "COPAUA0C laeuft als Online-Programm unter CICS. " * 5 + "\n"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(extra)
    await document_task.process_local_document_async(source.id, path)
    entity = CodeEntity(project_id=project_id, name="COPAUA0C", type="program", file_path="cbl/COPAUA0C.cbl", start_line=1, end_line=10)
    db_session.add(entity)
    db_session.commit()

    found = _pass_keyword(entity, project_id, db_session, embedding_model="test-embed")

    sections = {(chunk.metadata_json or {}).get("section") for chunk, _score in found.values()}
    assert {"Autorisierung > Entscheidung", "Autorisierung > Betrieb"} <= sections
    assert len(found) >= 2


def test_candidate_key_is_per_chunk_only_for_uploaded_documents():
    class Chunk:
        id = 7
        file_path = "seite"

    assert _candidate_key(Chunk(), {"title": "Handbuch", "source_type": "Local"}) == "Handbuch#7"
    assert _candidate_key(Chunk(), {"title": "Confluence-Seite", "source_type": "Confluence"}) == "Confluence-Seite"
    assert _candidate_key(Chunk(), {}) == "seite"
