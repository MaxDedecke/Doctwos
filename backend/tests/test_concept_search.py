"""Auffinden nach Beschreibung: Produktivcode vor Tests vor Tickets und Dokumentation, eine Fundstelle je Datei,
Rückfall auf Bezeichner ohne Einbettung. Derselbe Baustein für COBOL und Java (Rollen aus dem LanguageProfile)."""

import json

import pytest

from doctus_models.database import CodeEntity, DocumentChunk, User
from services import answer_context, concept_search
from tests import test_mcp_server as mcp_tests
from tests.test_mcp_server import mcp_project_context  # noqa: F401  (Fixture, wird per Name eingesetzt)
from tests.conftest import TEST_USERNAME

mcp_server = mcp_tests.mcp_server


def _chunk(project_id, path, start, end, text="x"):
    return DocumentChunk(
        project_id=project_id, file_path=path, start_line=start, end_line=end, content=text
    )


@pytest.fixture
def user(db_session, test_project):
    # test_project legt den Testbenutzer an
    return db_session.query(User).filter(User.username == TEST_USERNAME).one()


@pytest.fixture
def project(db_session, test_project):
    yield test_project
    for model in (CodeEntity, DocumentChunk):
        db_session.query(model).filter(model.project_id == test_project).delete()
    db_session.commit()


def _serve(monkeypatch, chunks):
    monkeypatch.setattr(concept_search, "_embed_query", lambda *_a, **_k: [0.1])
    monkeypatch.setattr(concept_search, "nearest_project_chunks", lambda *_a, **_k: chunks)


def _java(db, project):
    db.add_all(
        [
            CodeEntity(
                project_id=project,
                name="UserLogic",
                type="class",
                qualified_name="app.UserLogic",
                file_path="core/logic/UserLogic.java",
                start_line=10,
                end_line=200,
            ),
            CodeEntity(
                project_id=project,
                name="delete",
                type="method",
                qualified_name="app.UserLogic#delete(String)",
                file_path="core/logic/UserLogic.java",
                start_line=120,
                end_line=130,
            ),
            CodeEntity(
                project_id=project,
                name="DeleteTest",
                type="class",
                qualified_name="app.DeleteTest",
                file_path="core/src/test/java/DeleteTest.java",
                start_line=5,
                end_line=80,
            ),
            # Dokumentation und Konfiguration haben im Index ebenfalls Einheiten, aber keine Routine oder Container
            CodeEntity(
                project_id=project,
                name="Deleting users",
                type="doc_section",
                file_path="docs/users.adoc",
                start_line=1,
                end_line=30,
            ),
        ]
    )
    db.commit()


def test_code_comes_before_tests_before_tickets_and_documentation(
    db_session, user, project, monkeypatch
):
    _java(db_session, project)
    chunks = [
        _chunk(project, "docs/users.adoc", 1, 30),
        _chunk(project, "SYNCOPE-1", 1, 5),
        _chunk(project, "core/src/test/java/DeleteTest.java", 6, 40),
        _chunk(project, "core/logic/UserLogic.java", 121, 129),
        _chunk(project, "core/logic/UserLogic.java", 150, 160),  # zweiter Abschnitt derselben Datei
    ]
    db_session.add_all(chunks)
    db_session.commit()
    _serve(monkeypatch, chunks)

    result = concept_search.concept_hits(
        db_session, user, project, "Wie wird ein Benutzer gelöscht?"
    )

    files = [hit["file"] for hit in result["hits"]]
    assert files == [
        "core/logic/UserLogic.java",
        "core/src/test/java/DeleteTest.java",
        "docs/users.adoc",
        "SYNCOPE-1",
    ]
    first = result["hits"][0]
    assert first["cite"] == "core/logic/UserLogic.java:121"
    assert (first["unit"], first["unit_type"]) == ("app.UserLogic#delete(String)", "method")


def test_documentation_and_tests_are_capped_so_code_is_not_crowded_out(
    db_session, user, project, monkeypatch
):
    _java(db_session, project)
    docs = [_chunk(project, f"docs/page{i}.adoc", 1, 9) for i in range(6)]
    code = [_chunk(project, "core/logic/UserLogic.java", 121, 129)]
    db_session.add_all(docs + code)
    db_session.commit()
    _serve(monkeypatch, docs + code)

    result = concept_search.concept_hits(
        db_session, user, project, "Löschen eines Benutzers", limit=8
    )

    files = [hit["file"] for hit in result["hits"]]
    assert files[0] == "core/logic/UserLogic.java"
    assert len(files) == 3  # Code plus höchstens zwei sonstige Dateien


def test_cobol_units_are_found_by_the_same_block(db_session, user, project, monkeypatch):
    db_session.add_all(
        [
            CodeEntity(
                project_id=project,
                name="COACTUPC",
                type="program",
                qualified_name="COACTUPC",
                file_path="app/cbl/COACTUPC.cbl",
                start_line=1,
                end_line=4000,
            ),
            CodeEntity(
                project_id=project,
                name="1250-EDIT-SIGNED-9V2",
                type="paragraph",
                qualified_name="COACTUPC.1250-EDIT-SIGNED-9V2",
                file_path="app/cbl/COACTUPC.cbl",
                start_line=2180,
                end_line=2221,
            ),
        ]
    )
    chunk = _chunk(project, "app/cbl/COACTUPC.cbl", 2185, 2200)
    db_session.add(chunk)
    db_session.commit()
    _serve(monkeypatch, [chunk])

    hit = concept_search.concept_hits(db_session, user, project, "Kreditlimit prüfen")["hits"][0]

    assert (hit["unit_type"], hit["unit"]) == ("paragraph", "COACTUPC.1250-EDIT-SIGNED-9V2")
    assert hit["cite"] == "app/cbl/COACTUPC.cbl:2185"


def test_without_embeddings_identifiers_with_several_query_terms_still_answer(
    db_session, user, project, monkeypatch
):
    db_session.add_all(
        [
            CodeEntity(
                project_id=project,
                name="mustChangePassword",
                type="method",
                qualified_name="app.UserSelfLogic#mustChangePassword",
                file_path="core/UserSelfLogic.java",
                start_line=228,
                end_line=245,
            ),
            CodeEntity(
                project_id=project,
                name="password",
                type="method",
                qualified_name="app.Other#password",
                file_path="core/Other.java",
                start_line=1,
                end_line=2,
            ),
        ]
    )
    db_session.commit()
    monkeypatch.setattr(concept_search, "_embed_query", lambda *_a, **_k: None)

    result = concept_search.concept_hits(db_session, user, project, "must change password flow")

    assert result["mode"] == "names"
    assert [hit["file"] for hit in result["hits"]] == ["core/UserSelfLogic.java"]


def test_nothing_found_gives_none(db_session, user, project, monkeypatch):
    _serve(monkeypatch, [])
    assert (
        concept_search.concept_hits(db_session, user, project, "irgendetwas ohne Treffer") is None
    )
    assert concept_search.concept_hits(db_session, user, project, "   ") is None


def test_answer_context_adds_concept_hits_only_when_no_symbol_resolves(
    db_session, user, project, monkeypatch
):
    _java(db_session, project)
    chunk = _chunk(project, "core/logic/UserLogic.java", 121, 129)
    db_session.add(chunk)
    db_session.commit()
    _serve(monkeypatch, [chunk])
    monkeypatch.setattr(answer_context, "stale_sources", lambda *_a, **_k: [])

    asked = answer_context.build_answer_context(
        db_session, user, project, question="Wo wird ein Benutzer gelöscht?", use_embeddings=False
    )
    named = answer_context.build_answer_context(
        db_session, user, project, question="Was macht UserLogic?", use_embeddings=False
    )

    assert asked["resolved"] == [] and asked["concept_hits"]["hits"][0]["file"].endswith(
        "UserLogic.java"
    )
    assert "concept_hits" not in named and named["resolved"]


def test_search_code_falls_back_to_concept_hits_for_a_description_but_not_for_alternatives(
    db_session,
    mcp_project_context,  # noqa: F811
    monkeypatch,
):
    mcp_tests._use_test_session(monkeypatch, db_session)
    owner, _outsider, project_id, _foreign = mcp_project_context
    chunk = _chunk(project_id, "app/cbl/COCRDUPC.cbl", 913, 945)
    db_session.add(chunk)
    db_session.add(
        CodeEntity(
            project_id=project_id,
            name="COCRDUPC",
            type="program",
            qualified_name="COCRDUPC",
            file_path="app/cbl/COCRDUPC.cbl",
            start_line=1,
            end_line=2000,
        )
    )
    db_session.commit()
    _serve(monkeypatch, [chunk])
    context = mcp_tests._context(owner.id)

    described = mcp_server.search_code(
        context, project_id=project_id, query="Ablaufjahr der Karte prüfen"
    )
    alternatives = mcp_server.search_code(
        context, project_id=project_id, query="Ablaufjahr|Kartenjahr"
    )

    assert described["results"] == []
    package = described["answer_context"]
    assert package["concept_hits"]["hits"][0]["cite"] == "app/cbl/COCRDUPC.cbl:913"
    assert "names, not descriptions" in described["hint"]
    assert (
        list(described)[0] == "answer_context"
    )  # vor den Treffern, damit Kürzen die Belege nicht trifft
    assert "answer_context" not in alternatives

    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.query(DocumentChunk).filter(DocumentChunk.project_id == project_id).delete()
    db_session.commit()


def test_concept_hits_become_clickable_sources(db_session):
    from services.chat_sources import extract_tool_sources

    result = {
        "resolved": [],
        "concept_hits": {
            "hits": [
                {
                    "file": "core/UserLogic.java",
                    "lines": [121, 129],
                    "cite": "core/UserLogic.java:121",
                }
            ]
        },
    }
    sources: list[dict] = []

    extract_tool_sources(
        {"type": "tool_result", "name": "answer_context", "result": json.dumps(result)},
        sources,
        None,
    )

    assert {(s["file"], tuple(s["lines"])) for s in sources} == {
        ("core/UserLogic.java", (121, 129))
    }


def test_search_code_points_named_symbols_to_answer_context(
    db_session,
    mcp_project_context,  # noqa: F811
    monkeypatch,
):
    mcp_tests._use_test_session(monkeypatch, db_session)
    owner, _outsider, project_id, _foreign = mcp_project_context
    _java(db_session, project_id)
    context = mcp_tests._context(owner.id)

    found = mcp_server.search_code(
        context, project_id=project_id, query="UserLogic", include_source=False
    )

    first = found["follow_up_actions"][0]
    assert first["tool"] == "answer_context"
    assert first["arguments"]["symbols"] == ["app.UserLogic"]
    assert "answer_context" not in found

    db_session.query(CodeEntity).filter(CodeEntity.project_id == project_id).delete()
    db_session.commit()


@pytest.mark.parametrize(
    "query, describes",
    [
        ("card expiry year validation", True),
        ("Wie wird ein Benutzer gelöscht", True),
        ("CARD-YEAR-CHECK VALID-YEAR", False),
        ("COACTUPC 1250-EDIT-SIGNED-9V2", False),
        ("authenticate AuthDataAccessor", False),
        ("UserLogic#delete", False),
        ("mustChangePassword", False),
        ("Ablaufjahr|Kartenjahr", False),
    ],
)
def test_descriptions_are_told_apart_from_names_in_cobol_and_java(query, describes):
    assert mcp_server._describes(query) is describes
