"""
Regression coverage for tasks/link_builder.py::_pass_keyword after docs/GAPS.md #4:
DocumentChunk.content is now Fernet-encrypted at rest (EncryptedString), so the keyword pass can
no longer filter with SQL ILIKE and instead scans the project's chunks in Python after
decryption. This is a real integration test against the shared Postgres DB (same one the backend
uses) since _pass_keyword's whole job is a DB query + decrypt + score.
"""

import pytest
from sqlalchemy import text

from db import SessionLocal
from models.database import CodeEdge, CodeEntity, DocumentChunk
from tasks.link_builder import (
    MIN_SCORE_KEYWORD,
    _build_entity_context,
    _build_relationship_index,
    _entity_breadcrumb,
    _pass_keyword,
)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_project(db_session):
    # Raw SQL, not the ORM, for teams/projects/knowledge_sources: parser/models/database.py has no
    # Team class (only backend does), so SQLAlchemy can't resolve Project.team_id's FK to a `teams`
    # table it doesn't know about and flushing a Project/KnowledgeSource ORM object here would raise
    # NoReferencedTableError -- pre-existing gap in the parser's model file, unrelated to this test.
    team_id = db_session.execute(
        text("INSERT INTO teams (name, created_at) VALUES (:name, now()) RETURNING id"),
        {"name": "link-builder-test-team"},
    ).scalar_one()
    project_id = db_session.execute(
        text(
            "INSERT INTO projects (name, team_id, created_at) VALUES (:name, :team_id, now()) RETURNING id"
        ),
        {"name": "link-builder-test-project", "team_id": team_id},
    ).scalar_one()
    source_id = db_session.execute(
        text(
            "INSERT INTO knowledge_sources (name, type, team_id, project_id, created_at) "
            "VALUES (:name, :type, :team_id, :project_id, now()) RETURNING id"
        ),
        {
            "name": "link-builder-test-source",
            "type": "Local",
            "team_id": team_id,
            "project_id": project_id,
        },
    ).scalar_one()
    db_session.commit()

    yield project_id, source_id

    db_session.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.execute(text("DELETE FROM knowledge_sources WHERE id = :id"), {"id": source_id})
    db_session.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db_session.execute(text("DELETE FROM teams WHERE id = :id"), {"id": team_id})
    db_session.commit()


def test_pass_keyword_matches_decrypted_content(db_session, test_project):
    project_id, source_id = test_project

    entity = CodeEntity(
        project_id=project_id,
        file_path="src/payroll_calculator.py",
        name="calculate_payroll",
        type="function",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    matching = DocumentChunk(
        project_id=project_id,
        source_id=source_id,
        file_path="docs/payroll.pdf",
        content="This document describes the payroll calculator module in detail.",
    )
    decoy = DocumentChunk(
        project_id=project_id,
        source_id=source_id,
        file_path="docs/unrelated.pdf",
        content="Completely unrelated text about landscaping and gardens.",
    )
    db_session.add_all([matching, decoy])
    db_session.commit()

    result = _pass_keyword(entity, project_id, db_session)

    assert "docs/payroll.pdf" in result
    assert "docs/unrelated.pdf" not in result
    _, score = result["docs/payroll.pdf"]
    assert score >= MIN_SCORE_KEYWORD


def test_entity_context_uses_bounded_repository_excerpt_and_direct_edges(
    db_session, test_project
):
    project_id, source_id = test_project
    service = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentService.java",
        name="PaymentService",
        type="class",
        qualified_name="com.acme.PaymentService",
        start_line=1,
        end_line=6,
        meta_json={"language": "java"},
    )
    method = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentService.java",
        name="save",
        type="method",
        parent=service,
        qualified_name="com.acme.PaymentService#save(Payment)",
        start_line=2,
        end_line=4,
        meta_json={"language": "java", "signature": "save(Payment)"},
    )
    repository = CodeEntity(
        project_id=project_id,
        source_id=source_id,
        file_path="src/PaymentRepository.java",
        name="PaymentRepository",
        type="class",
        qualified_name="com.acme.PaymentRepository",
    )
    db_session.add_all([service, method, repository])
    db_session.flush()
    db_session.add(
        CodeEdge(
            project_id=project_id,
            source_id=source_id,
            src_entity_id=method.id,
            dst_entity_id=repository.id,
            dst_name=repository.qualified_name,
            type="CALL",
            resolution="resolved",
        )
    )
    db_session.add(
        DocumentChunk(
            project_id=project_id,
            source_id=source_id,
            file_path="src/PaymentService.java",
            start_line=1,
            end_line=6,
            content=(
                "class PaymentService {\n"
                "  public Payment save(Payment payment) {\n"
                "    return repository.persist(payment);\n"
                "  }\n"
                "  public void unrelated() {}\n"
                "}\n"
            ),
        )
    )
    db_session.commit()

    entities_by_id = {service.id: service, method.id: method, repository.id: repository}
    relationships = _build_relationship_index(
        project_id, db_session, entities_by_id, {method.id}
    )
    context = _build_entity_context(
        method,
        project_id,
        db_session,
        _entity_breadcrumb(method, entities_by_id),
        relationships,
        {},
    )

    assert "Qualified name: com.acme.PaymentService#save(Payment)" in context
    assert "Breadcrumb: PaymentService › save" in context
    assert "signature: save(Payment)" in context
    assert "to CALL (resolved) com.acme.PaymentRepository" in context
    assert "return repository.persist(payment);" in context
    assert "unrelated" not in context


def test_chunks_of_the_entitys_own_source_file_are_not_documentation_candidates():
    """Live-Fall CBPAUP0C: der Vorschlag „Entity ↔ Zeilen der eigenen CBPAUP0C.cbl“ ist kein Dokubezug."""
    from types import SimpleNamespace as NS

    from tasks.link_builder import _exclude_own_source

    entity = NS(source_id=7, file_path="app/cbl/CBPAUP0C.cbl")
    own = NS(source_id=7, file_path="app/cbl/CBPAUP0C.cbl")
    readme = NS(source_id=7, file_path="README.md")
    other_source_same_path = NS(source_id=8, file_path="app/cbl/CBPAUP0C.cbl")

    kept = _exclude_own_source(entity, [(own, 1.0, "keyword"), (readme, 0.98, "keyword"), (other_source_same_path, 0.9, "semantic")])

    assert [page[0] for page in kept] == [readme, other_source_same_path]


def _review_with(monkeypatch, response):
    import asyncio
    from types import SimpleNamespace

    import tasks.link_builder as link_builder

    async def fake_chat_json(prompt, model, **kwargs):
        return response

    monkeypatch.setattr(link_builder, "get_chat_json", fake_chat_json)
    entity = SimpleNamespace(type="program", name="CBPAUP0C", qualified_name="CBPAUP0C", file_path="CBPAUP0C.cbl")
    chunk = SimpleNamespace(content="Text", metadata_json={}, file_path="README.md", start_line=0, end_line=0)
    return asyncio.run(link_builder._llm_review(entity, [(chunk, 0.8, "semantic")], min_confidence=50))


_REASON = "Die README nennt das Programm ausdrücklich und beschreibt dessen Zweck; die genaue Rolle des Feldes bleibt unklar."


def test_llm_review_accepts_bare_object_for_single_candidate(monkeypatch):
    reviewed = _review_with(monkeypatch, {"index": 0, "confidence": 85, "reason": _REASON})
    assert [(item[1], item[3]) for item in reviewed] == [(0.85, _REASON)]


def test_llm_review_accepts_wrapped_array(monkeypatch):
    reviewed = _review_with(monkeypatch, {"results": [{"index": 0, "confidence": 70, "reason": _REASON}]})
    assert len(reviewed) == 1


def test_llm_review_still_rejects_answer_without_candidates(monkeypatch):
    with pytest.raises(RuntimeError, match="keine Kandidatenbewertung"):
        _review_with(monkeypatch, {"hinweis": "nichts gefunden"})


def _field(name="WS-AUTH-DATE", qualified="CBPAUP0C.WS-AUTH-DATE"):
    from types import SimpleNamespace

    return SimpleNamespace(
        type="data_item", name=name, qualified_name=qualified, file_path="cbl/CBPAUP0C.cbl", start_line=45, end_line=45
    )


def test_field_needs_its_own_name_or_a_name_from_its_code():
    from tasks.link_builder import _document_names_field

    program_only = "| CBPAUP0J | CBPAUP0C | Purge Expired Authorizations |"
    assert not _document_names_field(_field(), program_only, "Indexed code excerpt:\n 05 WS-AUTH-DATE PIC 9(05).")
    assert _document_names_field(_field(), "WS-AUTH-DATE hält das Datum.", None)
    copybook_doc = "| CIPAUSMY | Pending Authorization Summary IMS Segment |"
    summary = _field("PENDING-AUTH-SUMMARY", "CBPAUP0C.PENDING-AUTH-SUMMARY")
    assert _document_names_field(summary, copybook_doc, "Indexed code excerpt:\n 01 PENDING-AUTH-SUMMARY.\n COPY CIPAUSMY.")
    assert not _document_names_field(summary, copybook_doc, "Indexed code excerpt:\n 01 PENDING-AUTH-SUMMARY.")


def test_llm_review_skips_model_for_field_without_document_evidence(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import tasks.link_builder as link_builder

    async def must_not_be_called(prompt, model, **kwargs):
        raise AssertionError("LLM darf ohne Beleg nicht gefragt werden")

    monkeypatch.setattr(link_builder, "get_chat_json", must_not_be_called)
    chunk = SimpleNamespace(content="| CBPAUP0J | CBPAUP0C |", metadata_json={}, file_path="README.md", start_line=0, end_line=0)
    assert asyncio.run(link_builder._llm_review(_field(), [(chunk, 0.8, "semantic")], entity_context="Indexed code excerpt:\n x")) == []


def test_llm_review_prompt_has_no_example_confidence(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import tasks.link_builder as link_builder

    seen = {}

    async def capture(prompt, model, **kwargs):
        seen["prompt"] = prompt
        return {"index": 0, "confidence": 60, "reason": "Die README beschreibt dieses Programm und nennt dessen Zweck ausdrücklich im Detail."}

    monkeypatch.setattr(link_builder, "get_chat_json", capture)
    entity = SimpleNamespace(type="program", name="CBPAUP0C", qualified_name="CBPAUP0C", file_path="CBPAUP0C.cbl")
    chunk = SimpleNamespace(content="CBPAUP0C", metadata_json={}, file_path="README.md", start_line=0, end_line=0)
    asyncio.run(link_builder._llm_review(entity, [(chunk, 0.8, "semantic")], min_confidence=50))
    assert '"confidence": 85' not in seen["prompt"] and "nicht für alle Kandidaten denselben Wert" in seen["prompt"]


def test_keyword_corpus_gives_the_same_candidates_as_the_per_entity_scan(db_session, test_project, monkeypatch):
    """O-181: Der einmal je Lauf gebaute Korpus ändert die Treffer nicht; auch die Obergrenze schneidet gleich ab."""
    import tasks.link_builder as link_builder

    project_id, source_id = test_project
    entity = CodeEntity(project_id=project_id, file_path="src/payroll_calculator.py", name="calculate_payroll", type="function")
    db_session.add(entity)
    db_session.add_all(
        DocumentChunk(
            project_id=project_id, source_id=source_id, file_path=f"docs/payroll_{index}.pdf",
            content="Calculate payroll runs monthly." if index % 3 else "Unrelated gardening notes.",
        )
        for index in range(12)
    )
    db_session.commit()
    db_session.refresh(entity)
    monkeypatch.setattr(link_builder, "TOP_CHUNKS_KEYWORD", 5)

    scanned = link_builder._pass_keyword(entity, project_id, db_session)
    cached = link_builder._pass_keyword(
        entity, project_id, db_session, corpus=link_builder.KeywordCorpus(db_session, project_id)
    )

    assert scanned and {key: (value[0].id, value[1]) for key, value in scanned.items()} == {
        key: (value[0].id, value[1]) for key, value in cached.items()
    }
    delta = {chunk.id for chunk in db_session.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).limit(4)}
    assert set(link_builder._pass_keyword(entity, project_id, db_session, candidate_chunk_ids=delta)) == set(
        link_builder._pass_keyword(
            entity, project_id, db_session, candidate_chunk_ids=delta,
            corpus=link_builder.KeywordCorpus(db_session, project_id),
        )
    )


def test_keyword_corpus_over_the_memory_cap_falls_back_to_the_scan(db_session, test_project, monkeypatch):
    import tasks.link_builder as link_builder

    project_id, source_id = test_project
    db_session.add(DocumentChunk(project_id=project_id, source_id=source_id, file_path="docs/a.pdf", content="payroll text"))
    db_session.commit()
    monkeypatch.setattr(link_builder, "KEYWORD_CORPUS_MAX_CHARS", 3)
    assert link_builder.KeywordCorpus(db_session, project_id).items is None


def test_embed_context_window_batches_and_degrades_to_single_calls(monkeypatch):
    import asyncio

    import tasks.link_builder as link_builder

    calls = []

    async def batch(texts, model=None, **kwargs):
        calls.append(list(texts))
        return [[float(len(text))] for text in texts]

    monkeypatch.setattr(link_builder, "get_embeddings_batch", batch)
    vectors = asyncio.run(link_builder._embed_context_window({1: "aa", 2: "bbbb", 3: "c"}, "bge-m3"))
    assert calls == [["aa", "bbbb", "c"]] and vectors == {1: [2.0], 2: [4.0], 3: [1.0]}
    # Ein einzelner Kontext braucht kein Bündel.
    assert asyncio.run(link_builder._embed_context_window({1: "aa"}, "bge-m3")) == {}

    async def broken(texts, model=None, **kwargs):
        raise RuntimeError("Embedding-Server nicht erreichbar")

    monkeypatch.setattr(link_builder, "get_embeddings_batch", broken)
    assert asyncio.run(link_builder._embed_context_window({1: "a", 2: "b"}, "bge-m3")) == {}

    async def short(texts, model=None, **kwargs):
        return [[1.0]]

    monkeypatch.setattr(link_builder, "get_embeddings_batch", short)
    assert asyncio.run(link_builder._embed_context_window({1: "a", 2: "b"}, "bge-m3")) == {}


def test_pass_semantic_uses_a_precomputed_embedding(db_session, test_project, monkeypatch):
    import asyncio

    import tasks.link_builder as link_builder

    project_id, _source_id = test_project
    entity = CodeEntity(project_id=project_id, file_path="src/a.py", name="calc", type="function")
    db_session.add(entity)
    db_session.commit()

    async def must_not_be_called(*args, **kwargs):
        raise AssertionError("das Embedding ist schon berechnet")

    monkeypatch.setattr(link_builder, "get_embedding", must_not_be_called)
    assert asyncio.run(link_builder._pass_semantic(entity, project_id, db_session, embedding=[0.0] * 1024)) == {}


def test_link_run_params_default_to_the_constants_and_clamp_to_their_limits():
    from tasks.link_builder import (
        LLM_MIN_CONFIDENCE, MERGE_SCORE_THRESHOLD, TOP_CHUNKS_KEYWORD, TOP_CHUNKS_SEMANTIC, LinkRunParams,
    )

    defaults = LinkRunParams.from_scope(None)
    assert (defaults.top_k_semantic, defaults.top_k_keyword, defaults.merge_threshold, defaults.min_confidence) == (
        TOP_CHUNKS_SEMANTIC, TOP_CHUNKS_KEYWORD, MERGE_SCORE_THRESHOLD, LLM_MIN_CONFIDENCE
    )
    assert defaults.review_concurrency == 1 and defaults.review_batch_size == 0 and not defaults.dedupe_by_chunk

    chosen = LinkRunParams.from_scope(
        {"params": {"top_k_semantic": 5, "review_concurrency": 99, "merge_threshold": -1, "dedupe_by_chunk": True,
                    "review_batch_size": "3", "top_k_keyword": "kaputt"}},
        min_confidence=60,
    )
    assert chosen.top_k_semantic == 5 and chosen.review_concurrency == 8 and chosen.merge_threshold == 0.0
    assert chosen.dedupe_by_chunk is True and chosen.review_batch_size == 3
    assert chosen.top_k_keyword == TOP_CHUNKS_KEYWORD  # unlesbarer Wert: Standard
    assert chosen.min_confidence == 60
    assert LinkRunParams.from_scope({"params": chosen.as_dict()}) == LinkRunParams.from_scope(
        {"params": chosen.as_dict()}
    )


def test_llm_review_splits_candidates_into_batches(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import tasks.link_builder as link_builder

    sizes = []

    async def fake_once(entity, pages, min_confidence, entity_context):
        sizes.append(len(pages))
        return [(page[0], 0.7, page[2], "Begründung " * 5) for page in pages]

    monkeypatch.setattr(link_builder, "_llm_review_once", fake_once)
    entity = SimpleNamespace(type="program", name="P", qualified_name="P", file_path="p.cbl")
    pages = [(SimpleNamespace(id=index, content="x"), 0.9, "semantic") for index in range(5)]

    assert len(asyncio.run(link_builder._llm_review(entity, pages, batch_size=2))) == 5
    assert sizes == [2, 2, 1]
    sizes.clear()
    asyncio.run(link_builder._llm_review(entity, pages))
    assert sizes == [5]


def test_candidate_key_can_dedupe_per_chunk():
    from types import SimpleNamespace

    from tasks.link_builder import _candidate_key

    chunk = SimpleNamespace(id=7, file_path="README.md")
    assert _candidate_key(chunk, {"title": "README"}) == "README"
    assert _candidate_key(chunk, {"title": "README"}, per_chunk=True) == "README#7"
    assert _candidate_key(chunk, {"title": "README", "source_type": "Local"}) == "README#7"


def test_store_reviewed_links_updates_pending_and_keeps_decisions(db_session, test_project):
    from tasks.link_builder import _store_reviewed_links, _undecided_pages
    from models.database import EntityDocLink

    project_id, source_id = test_project
    entity = CodeEntity(project_id=project_id, file_path="src/a.py", name="calc", type="function")
    chunks = [
        DocumentChunk(project_id=project_id, source_id=source_id, file_path=f"docs/{index}.md", content="calc")
        for index in range(3)
    ]
    db_session.add_all([entity, *chunks])
    db_session.commit()
    db_session.add_all([
        EntityDocLink(project_id=project_id, entity_id=entity.id, chunk_id=chunks[0].id, status="approved", created_by="user"),
        EntityDocLink(project_id=project_id, entity_id=entity.id, chunk_id=chunks[1].id, status="pending", created_by="auto", score=0.1),
    ])
    db_session.commit()

    pages = [(chunk, 0.9, "semantic") for chunk in chunks]
    assert [page[0].id for page in _undecided_pages(db_session, entity, pages)] == [chunks[1].id, chunks[2].id]

    reason = "Der Abschnitt beschreibt diese Funktion mit ihrem Zweck ausdrücklich im Detail."
    _store_reviewed_links(db_session, project_id, entity, [(chunk, 0.8, "semantic", reason) for chunk in chunks], "bge-m3")
    db_session.commit()

    rows = {link.chunk_id: link for link in db_session.query(EntityDocLink).filter(EntityDocLink.entity_id == entity.id)}
    assert len(rows) == 3
    assert rows[chunks[0].id].status == "approved" and rows[chunks[0].id].score is None  # Entscheidung bleibt
    assert rows[chunks[1].id].score == 0.8 and rows[chunks[1].id].context == reason
    assert rows[chunks[2].id].status == "pending" and rows[chunks[2].id].created_by == "auto"


def test_llm_review_retries_once_after_a_timeout_and_names_the_error_type(monkeypatch):
    import asyncio
    from types import SimpleNamespace

    import httpx

    import tasks.link_builder as link_builder

    entity = SimpleNamespace(type="program", name="CBPAUP0C", qualified_name="CBPAUP0C", file_path="CBPAUP0C.cbl")
    chunk = SimpleNamespace(content="CBPAUP0C", metadata_json={}, file_path="README.md", start_line=0, end_line=0)
    reason = "Die README beschreibt dieses Programm und nennt dessen Zweck ausdrücklich im Detail."
    attempts = []

    async def slow_once(prompt, model, timeout=60.0, **kwargs):
        attempts.append(timeout)
        if len(attempts) == 1:
            raise httpx.ReadTimeout("")
        return {"index": 0, "confidence": 70, "reason": reason}

    monkeypatch.setattr(link_builder, "get_chat_json", slow_once)
    assert len(asyncio.run(link_builder._llm_review(entity, [(chunk, 0.8, "semantic")], min_confidence=50))) == 1
    assert attempts == [link_builder.LLM_REVIEW_TIMEOUT] * 2

    async def always_slow(prompt, model, timeout=60.0, **kwargs):
        raise httpx.ReadTimeout("")

    monkeypatch.setattr(link_builder, "get_chat_json", always_slow)
    try:
        asyncio.run(link_builder._llm_review(entity, [(chunk, 0.8, "semantic")], min_confidence=50))
        raise AssertionError("erwartet: RuntimeError")
    except RuntimeError as error:
        assert "ReadTimeout" in str(error)  # vorher eine leere Meldung
