from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, Project
from services.graph_retrieval import expand_chunks_with_graph


def _fixture_graph(db, project_id, team_id):
    source = KnowledgeSource(name="ap4-source", type="Git", url="https://example.test/ap4.git",
                             branch="main", project_id=project_id, team_id=team_id)
    db.add(source)
    db.flush()
    caller = CodeEntity(project_id=project_id, source_id=source.id, file_path="CALLER.CBL",
                        name="CALLER", qualified_name="CALLER", type="program", start_line=1, end_line=20)
    target = CodeEntity(project_id=project_id, source_id=source.id, file_path="TARGET.CBL",
                        name="TARGET", qualified_name="TARGET", type="program", start_line=1, end_line=20)
    copybook = CodeEntity(project_id=project_id, source_id=source.id, file_path="FIELDS.CPY",
                          name="FIELDS", qualified_name="FIELDS", type="copybook", start_line=1, end_line=10)
    db.add_all([caller, target, copybook])
    db.flush()
    paragraph = CodeEntity(project_id=project_id, source_id=source.id, file_path="TARGET.CBL",
                           name="TARGET.INIT-PARA", qualified_name="TARGET.INIT-PARA", type="paragraph",
                           parent_id=target.id, start_line=5, end_line=8)
    db.add(paragraph)
    db.flush()
    db.add_all([
        CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=caller.id,
                 dst_entity_id=target.id, dst_name="TARGET", type="CALL", resolution="resolved"),
        CodeEdge(project_id=project_id, source_id=source.id, src_entity_id=target.id,
                 dst_entity_id=copybook.id, dst_name="FIELDS", type="COPY", resolution="resolved"),
    ])
    chunks = [
        DocumentChunk(project_id=project_id, source_id=source.id, file_path="TARGET.CBL", content="TARGET definition", start_line=1, end_line=20),
        DocumentChunk(project_id=project_id, source_id=source.id, file_path="CALLER.CBL", content="CALLER definition", start_line=1, end_line=20),
        DocumentChunk(project_id=project_id, source_id=source.id, file_path="FIELDS.CPY", content="FIELDS definition", start_line=1, end_line=10),
    ]
    db.add_all(chunks)
    db.commit()
    return source, caller, target, copybook, paragraph, chunks


def test_entity_neighbors_resolve_and_callgraph_exports(client, db_session, test_project, test_team):
    """Deckt den regulären Projekt-Kontext ab (Code-Editor/projektgebundene Panels
    schicken ihre eigene project_id mit) -- das bleibt vom Default-Deny-Opt-in für
    projektübergreifende Sichtbarkeit (test_entity_access_denied_outside_project_...
    unten) unberührt, siehe core/projects.py::assert_project_code_visible_in_context."""
    source, caller, target, copybook, paragraph, _ = _fixture_graph(db_session, test_project, test_team)
    try:
        assert client.get(f"/entities/resolve?source_id={source.id}&path=TARGET.CBL&project_id={test_project}").json()["id"] == target.id
        entity = client.get(f"/entities/{target.id}?project_id={test_project}")
        assert entity.status_code == 200
        assert entity.json()["definition"]["content"] == "TARGET definition"

        neighbors = client.get(f"/entities/{target.id}/neighbors?types=CALL&direction=in&project_id={test_project}").json()
        assert list(neighbors["groups"]) == ["CALL:in"]
        assert neighbors["groups"]["CALL:in"][0]["entity"]["id"] == caller.id

        graph = client.get(f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}").json()
        assert {n["id"] for n in graph["nodes"]} == {caller.id, target.id, copybook.id}
        assert client.get(f"/callgraph/export?entity_id={target.id}&format=json&project_id={test_project}").status_code == 200
        assert client.get(f"/callgraph/export?entity_id={target.id}&format=csv&project_id={test_project}").status_code == 200
        graphml = client.get(f"/callgraph/export?entity_id={target.id}&format=graphml&project_id={test_project}")
        assert graphml.status_code == 200
        assert "graphml" in graphml.text

        # CONTAINS (Struktur-Vorfahren über CodeEntity.parent_id) wird nur nach
        # oben nachgezogen: Fokus auf den Paragraphen zeigt sein Programm, ohne
        # dass ein CALL/COPY/PERFORM den Paragraphen je durchlaufen hätte.
        para_graph = client.get(f"/callgraph/focus?entity_id={paragraph.id}&hops=0&project_id={test_project}").json()
        assert {n["id"] for n in para_graph["nodes"]} == {paragraph.id, target.id}
        contains_edges = [e for e in para_graph["edges"] if e["type"] == "CONTAINS"]
        assert len(contains_edges) == 1
        assert contains_edges[0]["source"] == target.id
        assert contains_edges[0]["target"] == paragraph.id

        search_result = client.get("/search", params={"q": "TARGET", "types": "entity", "project_id": test_project})
        assert search_result.status_code == 200
        target_hit = next(hit for hit in search_result.json()["results"] if hit["node_id"] == target.id)
        assert target_hit["node_meta"]["source_id"] == source.id
        assert target_hit["node_meta"]["file_path"] == "TARGET.CBL"
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_entity_access_denied_outside_project_context_unless_opted_in(client, db_session, test_project, test_team):
    """Default-Deny: außerhalb des eigenen Projekt-Kontexts (kein project_id, wie in der
    "Allgemein"-Suche/-Graph-View) sind Code-Analyse-Objekte eines Projekts erst nach
    explizitem Opt-in (Project.expose_code_analysis_globally) sichtbar."""
    source, caller, target, copybook, paragraph, _ = _fixture_graph(db_session, test_project, test_team)
    try:
        assert client.get(f"/entities/resolve?source_id={source.id}&path=TARGET.CBL").status_code == 404
        assert client.get(f"/entities/{target.id}").status_code == 404
        assert client.get(f"/entities/{target.id}/neighbors").status_code == 404
        assert client.get(f"/callgraph/focus?entity_id={target.id}&hops=1").status_code == 404
        assert client.get(f"/callgraph/export?entity_id={target.id}&format=json").status_code == 404

        search_result = client.get("/search", params={"q": "TARGET", "types": "entity"})
        assert search_result.status_code == 200
        assert all(hit["node_id"] != target.id for hit in search_result.json()["results"])

        # Dieselbe Sperre gilt für Dokument-Chunks der Git-Wissensquelle (rohe
        # Repo-Quelldateien, siehe core/projects.py::build_document_chunk_code_gate).
        doc_search = client.get("/search", params={"q": "TARGET.CBL", "types": "document"})
        assert doc_search.status_code == 200
        assert all(hit["node_meta"]["source_id"] != source.id for hit in doc_search.json()["results"])

        # Aus einem ANDEREN Projekt-Kontext heraus gilt dieselbe Sperre.
        other_project = Project(name="Other Project", team_id=test_team, creator_id=None)
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)
        try:
            assert client.get(f"/entities/{target.id}?project_id={other_project.id}").status_code == 404
        finally:
            db_session.query(Project).filter(Project.id == other_project.id).delete()
            db_session.commit()

        # Nach dem Opt-in ist derselbe Aufruf ohne project_id erlaubt.
        db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": True})
        db_session.commit()
        try:
            assert client.get(f"/entities/{target.id}").status_code == 200
            assert client.get(f"/callgraph/focus?entity_id={target.id}&hops=1").status_code == 200
            search_result = client.get("/search", params={"q": "TARGET", "types": "entity"})
            assert any(hit["node_id"] == target.id for hit in search_result.json()["results"])
            doc_search = client.get("/search", params={"q": "TARGET.CBL", "types": "document"})
            assert any(hit["node_meta"]["source_id"] == source.id for hit in doc_search.json()["results"])
        finally:
            db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": False})
            db_session.commit()
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_retrieval_adds_callers_and_copy_targets_with_budget(db_session, test_project, test_team):
    source, caller, target, copybook, paragraph, chunks = _fixture_graph(db_session, test_project, test_team)
    try:
        # Treffer TARGET: eingehender CALL ergänzt CALLER; ausgehender COPY ergänzt FIELDS.
        expanded = expand_chunks_with_graph(db_session, [chunks[0]], token_budget=100)
        assert {chunk.file_path for chunk in expanded} == {"TARGET.CBL", "CALLER.CBL", "FIELDS.CPY"}
        budgeted = expand_chunks_with_graph(db_session, [chunks[0]], token_budget=1)
        assert [chunk.file_path for chunk in budgeted] == ["TARGET.CBL"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
