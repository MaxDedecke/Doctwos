"""Kopfzeilen-Suche: Namen vor Pfad, Teilbegriffe als UND, keine Ordnertreffer, sortierte Dokumente."""

import pytest

from models.database import CodeEntity, DocumentChunk, KnowledgeSource, Project
from services.search import search_nodes

REL = "app/app-authorization-ims-db2-mq"


@pytest.fixture
def corpus(db_session, test_project):
    team_id = db_session.query(Project.team_id).filter(Project.id == test_project).scalar()
    source = KnowledgeSource(name="search-rank", type="Git", project_id=test_project, team_id=team_id, spaces={})
    db_session.add(source)
    db_session.flush()

    def entity(name, type_, path, qualified=None, parent=None):
        item = CodeEntity(
            project_id=test_project, source_id=source.id, file_path=path, name=name, type=type_,
            qualified_name=qualified or name, start_line=1,
        )
        db_session.add(item)
        db_session.flush()
        return item

    entity("COPAUA0C", "program", f"{REL}/cbl/COPAUA0C.cbl")
    for para in ("MAIN-PARA", "1000-EXIT", "2000-EXIT"):
        entity(para, "paragraph", f"{REL}/cbl/COPAUA0C.cbl", f"COPAUA0C.{para}")
    entity("GET-AUTHORIZATIONS", "paragraph", f"{REL}/cbl/COPAUS0C.cbl", "COPAUS0C.GET-AUTHORIZATIONS")
    entity("STEP01", "jcl_step", f"{REL}/jcl/LOADPADB.JCL", f"{REL}/jcl/LOADPADB.JCL::job:LOADPADB::step:STEP01")
    entity("LOADPADB.JCL", "jcl_file", f"{REL}/jcl/LOADPADB.JCL", f"{REL}/jcl/LOADPADB.JCL")
    entity("UserLogic", "class", "core/UserLogic.java", "org.example.UserLogic")
    entity("create", "method", "core/UserLogic.java", "org.example.UserLogic#create(UserCR)")
    entity("update", "method", "core/UserLogic.java", "org.example.UserLogic#update(UserUR)")
    entity("PENDING-AUTH-REQUEST", "data_item", f"{REL}/cpy/CCPAURQY.cpy", "CCPAURQY.PENDING-AUTH-REQUEST")
    entity("SALES_100", "data_item", "x/SALES.cpy", "SALES.SALES_100")
    entity("SALES5", "data_item", "x/SALES.cpy", "SALES.SALES5")

    def doc(path, title):
        db_session.add(DocumentChunk(
            project_id=test_project, source_id=source.id, file_path=path, content="x", start_line=1, end_line=2,
            metadata_json={"title": title} if title else {},
        ))

    doc(f"{REL}/README.md", "README")
    doc(f"{REL}/docs/Authorization Guide.md", "Authorization Guide")
    doc(f"{REL}/docs/zz-appendix.md", "Appendix")
    doc("docs/authorization-notes.md", None)
    db_session.commit()
    yield test_project
    db_session.query(DocumentChunk).filter(DocumentChunk.source_id == source.id).delete()
    db_session.query(CodeEntity).filter(CodeEntity.source_id == source.id).delete()
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def _labels(db, project, q, types="entity", limit=10):
    results, counts = search_nodes(db, q=q, types=types, project_id=project, limit=limit)
    return [(r["node_label"], r["node_meta"].get("type")) for r in results], counts


def test_exact_name_comes_first_and_children_follow_only_through_their_qualified_name(db_session, corpus):
    labels, counts = _labels(db_session, corpus, "COPAUA0C")
    assert labels[0] == ("COPAUA0C", "program")
    assert {name for name, _ in labels[1:]} == {"MAIN-PARA", "1000-EXIT", "2000-EXIT"}
    assert counts["entity"] == 4


def test_a_folder_name_alone_is_no_hit(db_session, corpus):
    """`authorization` stand im Ordnernamen von JCL und Copybooks, nicht in deren Namen."""
    labels, counts = _labels(db_session, corpus, "authorization")
    assert {name for name, _ in labels} == {"GET-AUTHORIZATIONS", "PENDING-AUTH-REQUEST"} - {"PENDING-AUTH-REQUEST"}
    assert counts["entity"] == 1
    assert all(type_ != "jcl_step" for _, type_ in labels)


def test_file_entities_are_found_by_file_name_and_only_an_extension_narrows_to_them(db_session, corpus):
    labels, _ = _labels(db_session, corpus, "LOADPADB")
    # Die Datei zuerst; ihr Step folgt, weil sein Qualified Name den Dateinamen trägt.
    assert labels == [("LOADPADB.JCL", "jcl_file"), ("STEP01", "jcl_step")]
    # Mit Endung passt nur die Datei-Entity: `cbl` steht weder im Namen noch im Qualified Name der Kinder.
    cbl, counts = _labels(db_session, corpus, "COPAUA0C.cbl")
    assert cbl == [("COPAUA0C", "program")] and counts["entity"] == 1


def test_several_terms_must_all_match_and_class_method_spelling_works(db_session, corpus):
    both, _ = _labels(db_session, corpus, "pending request")
    assert both == [("PENDING-AUTH-REQUEST", "data_item")]
    only_one, _ = _labels(db_session, corpus, "pending nothingmatches")
    assert only_one == []
    method, _ = _labels(db_session, corpus, "UserLogic.create")
    assert method == [("create", "method")]
    hash_form, _ = _labels(db_session, corpus, "UserLogic#create")
    assert hash_form == [("create", "method")]


def test_percent_and_underscore_in_the_query_are_not_wildcards(db_session, corpus):
    underscore, _ = _labels(db_session, corpus, "SALES_100")
    assert underscore == [("SALES_100", "data_item")]
    percent, counts = _labels(db_session, corpus, "%")
    assert percent == [] and counts["entity"] == 0


def test_documents_are_ranked_by_title_and_ignore_folder_only_matches(db_session, corpus):
    docs, counts = search_nodes(db_session, q="authorization", types="document", project_id=corpus, limit=10)
    paths = [d["node_meta"]["file_path"] for d in docs]
    assert paths == [f"{REL}/docs/Authorization Guide.md", "docs/authorization-notes.md"]
    assert counts["document"] == 2

    exact, _ = search_nodes(db_session, q="readme", types="document", project_id=corpus, limit=1)
    assert [d["node_label"] for d in exact] == ["README"]


def test_blank_or_separator_only_queries_do_not_crash(db_session, corpus):
    for q in ("", "   ", ". #"):
        results, counts = search_nodes(db_session, q=q, types="entity,document", project_id=corpus, limit=5)
        assert isinstance(results, list) and "entity" in counts
