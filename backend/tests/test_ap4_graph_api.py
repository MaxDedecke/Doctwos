from models.database import CodeEdge, CodeEntity, DocumentChunk, KnowledgeSource, Project
from services.graph_retrieval import expand_chunks_with_graph


def _fixture_graph(db, project_id, team_id):
    source = KnowledgeSource(
        name="ap4-source",
        type="Git",
        url="https://example.test/ap4.git",
        branch="main",
        project_id=project_id,
        team_id=team_id,
    )
    db.add(source)
    db.flush()
    caller = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="CALLER.CBL",
        name="CALLER",
        qualified_name="CALLER",
        type="program",
        start_line=1,
        end_line=20,
    )
    target = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="TARGET.CBL",
        name="TARGET",
        qualified_name="TARGET",
        type="program",
        start_line=1,
        end_line=20,
    )
    copybook = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="FIELDS.CPY",
        name="FIELDS",
        qualified_name="FIELDS",
        type="copybook",
        start_line=1,
        end_line=10,
    )
    db.add_all([caller, target, copybook])
    db.flush()
    paragraph = CodeEntity(
        project_id=project_id,
        source_id=source.id,
        file_path="TARGET.CBL",
        name="TARGET.INIT-PARA",
        qualified_name="TARGET.INIT-PARA",
        type="paragraph",
        parent_id=target.id,
        start_line=5,
        end_line=8,
    )
    db.add(paragraph)
    db.flush()
    db.add_all(
        [
            CodeEdge(
                project_id=project_id,
                source_id=source.id,
                src_entity_id=caller.id,
                dst_entity_id=target.id,
                dst_name="TARGET",
                type="CALL",
                resolution="resolved",
            ),
            CodeEdge(
                project_id=project_id,
                source_id=source.id,
                src_entity_id=target.id,
                dst_entity_id=copybook.id,
                dst_name="FIELDS",
                type="COPY",
                resolution="resolved",
            ),
        ]
    )
    chunks = [
        DocumentChunk(
            project_id=project_id,
            source_id=source.id,
            file_path="TARGET.CBL",
            content="TARGET definition",
            start_line=1,
            end_line=20,
        ),
        DocumentChunk(
            project_id=project_id,
            source_id=source.id,
            file_path="CALLER.CBL",
            content="CALLER definition",
            start_line=1,
            end_line=20,
        ),
        DocumentChunk(
            project_id=project_id,
            source_id=source.id,
            file_path="FIELDS.CPY",
            content="FIELDS definition",
            start_line=1,
            end_line=10,
        ),
    ]
    db.add_all(chunks)
    db.commit()
    return source, caller, target, copybook, paragraph, chunks


def test_entity_neighbors_resolve_and_callgraph_exports(
    client, db_session, test_project, test_team
):
    """Deckt den regulären Projekt-Kontext ab (Code-Editor/projektgebundene Panels
    schicken ihre eigene project_id mit) -- das bleibt vom Default-Deny-Opt-in für
    projektübergreifende Sichtbarkeit (test_entity_access_denied_outside_project_...
    unten) unberührt, siehe core/projects.py::assert_project_code_visible_in_context."""
    source, caller, target, copybook, paragraph, _ = _fixture_graph(
        db_session, test_project, test_team
    )
    try:
        assert (
            client.get(
                f"/entities/resolve?source_id={source.id}&path=TARGET.CBL&project_id={test_project}"
            ).json()["id"]
            == target.id
        )
        entity = client.get(f"/entities/{target.id}?project_id={test_project}")
        assert entity.status_code == 200
        assert entity.json()["definition"]["content"] == "TARGET definition"

        neighbors = client.get(
            f"/entities/{target.id}/neighbors?types=CALL&direction=in&project_id={test_project}"
        ).json()
        assert list(neighbors["groups"]) == ["CALL:in"]
        assert neighbors["groups"]["CALL:in"][0]["entity"]["id"] == caller.id

        graph = client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}"
        ).json()
        assert {n["id"] for n in graph["nodes"]} == {caller.id, target.id, copybook.id}
        # Der Graph ist weiterhin durch MAX_NODES begrenzt, erlaubt für eine
        # technische Ablaufanalyse aber nun bis zu fünf Beziehungsebenen.
        assert client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=5&project_id={test_project}"
        ).status_code == 200
        assert (
            client.get(
                f"/callgraph/export?entity_id={target.id}&format=json&project_id={test_project}"
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/callgraph/export?entity_id={target.id}&format=csv&project_id={test_project}"
            ).status_code
            == 200
        )
        graphml = client.get(
            f"/callgraph/export?entity_id={target.id}&format=graphml&project_id={test_project}"
        )
        assert graphml.status_code == 200
        assert "graphml" in graphml.text

        # CONTAINS (Struktur-Vorfahren über CodeEntity.parent_id) wird nur nach
        # oben nachgezogen: Fokus auf den Paragraphen zeigt sein Programm, ohne
        # dass ein CALL/COPY/PERFORM den Paragraphen je durchlaufen hätte.
        para_graph = client.get(
            f"/callgraph/focus?entity_id={paragraph.id}&hops=0&project_id={test_project}"
        ).json()
        assert {n["id"] for n in para_graph["nodes"]} == {paragraph.id, target.id}
        contains_edges = [e for e in para_graph["edges"] if e["type"] == "CONTAINS"]
        assert len(contains_edges) == 1
        assert contains_edges[0]["source"] == target.id
        assert contains_edges[0]["target"] == paragraph.id

        search_result = client.get(
            "/search", params={"q": "TARGET", "types": "entity", "project_id": test_project}
        )
        assert search_result.status_code == 200
        target_hit = next(
            hit for hit in search_result.json()["results"] if hit["node_id"] == target.id
        )
        assert target_hit["node_meta"]["source_id"] == source.id
        assert target_hit["node_meta"]["file_path"] == "TARGET.CBL"
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_api_and_graph_transport_java_edge_types_and_optional_inheritance(
    client, db_session, test_project, test_team
):
    source, caller, target, copybook, paragraph, _ = _fixture_graph(
        db_session, test_project, test_team
    )
    java_call = CodeEdge(
        project_id=test_project,
        source_id=source.id,
        src_entity_id=caller.id,
        dst_entity_id=target.id,
        dst_name="com.example.Target.run",
        type="CALLS",
        resolution="resolved",
    )
    java_inheritance = CodeEdge(
        project_id=test_project,
        source_id=source.id,
        src_entity_id=caller.id,
        dst_entity_id=target.id,
        dst_name="com.example.Target",
        type="EXTENDS",
        resolution="resolved",
    )
    db_session.add_all([java_call, java_inheritance])
    db_session.commit()
    try:
        default_graph = client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}"
        ).json()
        default_types = {edge["type"] for edge in default_graph["edges"]}
        assert "CALLS" in default_types
        assert "EXTENDS" not in default_types
        assert "CALLS" in default_graph["edge_types"]

        inheritance_graph = client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}"
            "&include_inheritance=true"
        ).json()
        assert "EXTENDS" in {edge["type"] for edge in inheritance_graph["edges"]}

        explicit_graph = client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}&types=EXTENDS"
        ).json()
        assert {edge["type"] for edge in explicit_graph["edges"]} == {"EXTENDS"}

        overview = client.get(f"/graph?project_id={test_project}").json()
        code_edge = next(edge for edge in overview["edges"] if edge["id"] == f"code:{java_call.id}")
        assert code_edge["link_type"] == "CALLS"
        assert code_edge["type"] == "CALLS"
        assert code_edge["direction"] == "directed"
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_callgraph_focus_marks_nodes_from_incompletely_analyzed_files(
    client, db_session, test_project, test_team
):
    """O-120: ein Knoten aus einer nur teilweise geparsten Datei darf im
    Call-Graph nicht wie ein uneingeschränkt analysierter Knoten aussehen."""
    from models.database import SourceScanFile

    source, caller, target, copybook, paragraph, _ = _fixture_graph(
        db_session, test_project, test_team
    )
    try:
        db_session.add(
            SourceScanFile(
                source_id=source.id,
                file_path="TARGET.CBL",
                content_hash="abc",
                parse_status="partial",
                parse_error="mismatched input",
            )
        )
        db_session.commit()

        graph = client.get(
            f"/callgraph/focus?entity_id={target.id}&hops=1&project_id={test_project}"
        ).json()
        nodes_by_id = {n["id"]: n for n in graph["nodes"]}

        # TARGET.CBL beherbergt sowohl target als auch paragraph.
        assert nodes_by_id[target.id]["analysis_status"] == "partial"
        assert nodes_by_id[target.id]["analysis_reasons"] == ["mismatched input"]
        # CALLER.CBL/FIELDS.CPY blieben unberührt -- kein Eintrag.
        assert "analysis_status" not in nodes_by_id[caller.id]
        assert "analysis_status" not in nodes_by_id[copybook.id]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_entity_access_denied_outside_project_context_unless_opted_in(
    client, db_session, test_project, test_team
):
    """Default-Deny: außerhalb des eigenen Projekt-Kontexts (kein project_id, wie in der
    "Allgemein"-Suche/-Graph-View) sind Code-Analyse-Objekte eines Projekts erst nach
    explizitem Opt-in (Project.expose_code_analysis_globally) sichtbar."""
    source, caller, target, copybook, paragraph, _ = _fixture_graph(
        db_session, test_project, test_team
    )
    try:
        assert (
            client.get(f"/entities/resolve?source_id={source.id}&path=TARGET.CBL").status_code
            == 404
        )
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
        assert all(
            hit["node_meta"]["source_id"] != source.id for hit in doc_search.json()["results"]
        )

        # Aus einem ANDEREN Projekt-Kontext heraus gilt dieselbe Sperre.
        other_project = Project(name="Other Project", team_id=test_team, creator_id=None)
        db_session.add(other_project)
        db_session.commit()
        db_session.refresh(other_project)
        try:
            assert (
                client.get(f"/entities/{target.id}?project_id={other_project.id}").status_code
                == 404
            )
        finally:
            db_session.query(Project).filter(Project.id == other_project.id).delete()
            db_session.commit()

        # Nach dem Opt-in ist derselbe Aufruf ohne project_id erlaubt.
        db_session.query(Project).filter(Project.id == test_project).update(
            {"expose_code_analysis_globally": True}
        )
        db_session.commit()
        try:
            assert client.get(f"/entities/{target.id}").status_code == 200
            assert client.get(f"/callgraph/focus?entity_id={target.id}&hops=1").status_code == 200
            search_result = client.get("/search", params={"q": "TARGET", "types": "entity"})
            assert any(hit["node_id"] == target.id for hit in search_result.json()["results"])
            doc_search = client.get("/search", params={"q": "TARGET.CBL", "types": "document"})
            assert any(
                hit["node_meta"]["source_id"] == source.id for hit in doc_search.json()["results"]
            )
        finally:
            db_session.query(Project).filter(Project.id == test_project).update(
                {"expose_code_analysis_globally": False}
            )
            db_session.commit()
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_retrieval_adds_callers_and_copy_targets_with_budget(
    db_session, test_project, test_team
):
    source, caller, target, copybook, paragraph, chunks = _fixture_graph(
        db_session, test_project, test_team
    )
    try:
        # Treffer TARGET: eingehender CALL ergänzt CALLER; ausgehender COPY ergänzt FIELDS.
        expanded = expand_chunks_with_graph(db_session, [chunks[0]], token_budget=100)
        assert {chunk.file_path for chunk in expanded} == {"TARGET.CBL", "CALLER.CBL", "FIELDS.CPY"}
        budgeted = expand_chunks_with_graph(db_session, [chunks[0]], token_budget=1)
        assert [chunk.file_path for chunk in budgeted] == ["TARGET.CBL"]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_retrieval_adds_resolved_java_neighbors_with_budget(
    db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="java-retrieval-source",
        type="Git",
        url="https://example.test/java-retrieval.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    service = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="src/PaymentService.java",
        name="PaymentService",
        qualified_name="com.acme.PaymentService",
        type="class",
        start_line=1,
        end_line=20,
        meta_json={"language": "java"},
    )
    repository = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="src/PaymentRepository.java",
        name="PaymentRepository",
        qualified_name="com.acme.PaymentRepository",
        type="class",
        start_line=1,
        end_line=20,
        meta_json={"language": "java"},
    )
    db_session.add_all([service, repository])
    db_session.flush()
    db_session.add(
        CodeEdge(
            project_id=test_project,
            source_id=source.id,
            src_entity_id=service.id,
            dst_entity_id=repository.id,
            dst_name="com.acme.PaymentRepository",
            type="USES_TYPE",
            resolution="resolved",
        )
    )
    hit = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path=service.file_path,
        content="PaymentService definition",
        start_line=1,
        end_line=20,
    )
    neighbor = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path=repository.file_path,
        content="PaymentRepository definition",
        start_line=1,
        end_line=20,
    )
    db_session.add_all([hit, neighbor])
    db_session.commit()
    try:
        expanded = expand_chunks_with_graph(db_session, [hit], token_budget=100)
        assert [chunk.file_path for chunk in expanded] == [hit.file_path, neighbor.file_path]
        assert [
            chunk.file_path for chunk in expand_chunks_with_graph(db_session, [hit], token_budget=1)
        ] == [hit.file_path]
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
