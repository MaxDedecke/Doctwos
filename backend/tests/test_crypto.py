from sqlalchemy import text

from models.database import ChatMessage, ChatSession, DocumentChunk, KnowledgeSource


def test_token_round_trips_through_the_orm(db_session, test_project, test_team):
    source = KnowledgeSource(name="crypto-roundtrip", type="Git", url="https://example.com/x.git", token="my-plaintext-token", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    db_session.expire(source)
    assert source.token == "my-plaintext-token"

    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def test_token_is_not_stored_as_plaintext_at_the_raw_sql_level(db_session, test_project, test_team):
    plaintext = "another-plaintext-token"
    source = KnowledgeSource(name="crypto-raw-check", type="Git", url="https://example.com/x.git", token=plaintext, project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    raw_value = db_session.execute(
        text("SELECT token FROM knowledge_sources WHERE id = :id"), {"id": source.id}
    ).scalar_one()
    assert raw_value != plaintext
    assert raw_value.startswith("gAAAAA")  # Fernet token prefix

    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


# ── docs/GAPS.md #4: content-at-rest now covers document/chat/compliance content too ──

def test_document_chunk_content_round_trips_and_is_not_plaintext_at_rest(db_session, test_project):
    plaintext = "Section 4.2.1: Fire-rated wall T90 required per DIN 4102."
    chunk = DocumentChunk(project_id=test_project, file_path="docs/spec.pdf", content=plaintext, start_line=1, end_line=1)
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    db_session.expire(chunk)
    assert chunk.content == plaintext

    raw_value = db_session.execute(
        text("SELECT content FROM document_chunks WHERE id = :id"), {"id": chunk.id}
    ).scalar_one()
    assert raw_value != plaintext
    assert raw_value.startswith("gAAAAA")

    db_session.query(DocumentChunk).filter(DocumentChunk.id == chunk.id).delete()
    db_session.commit()


def test_chat_message_content_round_trips_and_is_not_plaintext_at_rest(db_session, test_project):
    session = ChatSession(project_id=test_project, title="crypto-test-session")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    plaintext = "Was verlangt die Baubeschreibung fuer die Brandschutzklasse im Erdgeschoss?"
    msg = ChatMessage(session_id=session.id, role="user", content=plaintext)
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    db_session.expire(msg)
    assert msg.content == plaintext

    raw_value = db_session.execute(
        text("SELECT content FROM chat_messages WHERE id = :id"), {"id": msg.id}
    ).scalar_one()
    assert raw_value != plaintext
    assert raw_value.startswith("gAAAAA")

    db_session.query(ChatMessage).filter(ChatMessage.id == msg.id).delete()
    db_session.query(ChatSession).filter(ChatSession.id == session.id).delete()
    db_session.commit()


