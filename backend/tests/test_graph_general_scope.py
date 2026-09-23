"""Regressionstest für den ursprünglich gemeldeten Fehler: GET /graph ohne project_id
("Allgemein"-Wissensnetz/Graph-View) zeigte Code-Analyse-Objekte JEDES Projekts, auf
das der Nutzer irgendeine Team-/Projekt-Sichtbarkeit hatte -- unabhängig vom
Projekt-Kontext. Jetzt braucht das Ziel-Projekt dafür das explizite Opt-in
`expose_code_analysis_globally` (siehe core/projects.py, backend/api/graph.py)."""

from models.database import (
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeLink,
    KnowledgeSource,
    Project,
)


def _code_file_paths(response_json: dict) -> set[str]:
    return {n["file_path"] for n in response_json["nodes"] if n["type"] == "code_file"}


def _doc_node_ids(response_json: dict) -> set[str]:
    return {n["label"] for n in response_json["nodes"] if n["type"] == "document"}


def test_general_graph_hides_project_entities_unless_opted_in(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="scope-source",
        type="Git",
        url="https://example.test/scope.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="SCOPED.CBL",
        name="SCOPED",
        qualified_name="SCOPED",
        type="program",
        start_line=1,
        end_line=10,
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    try:
        # Innerhalb des eigenen Projekt-Kontexts (project_id mitgeschickt) immer sichtbar.
        scoped = client.get(
            "/graph", params={"project_id": test_project, "include_isolated": "true"}
        )
        assert scoped.status_code == 200
        assert "SCOPED.CBL" in _code_file_paths(scoped.json())

        # "Allgemein" (kein project_id) -- default aus, Entity darf nicht auftauchen.
        general = client.get("/graph", params={"include_isolated": "true"})
        assert general.status_code == 200
        assert "SCOPED.CBL" not in _code_file_paths(general.json())

        # Nach Opt-in erscheint dieselbe Entity auch im Allgemein-Graph.
        db_session.query(Project).filter(Project.id == test_project).update(
            {"expose_code_analysis_globally": True}
        )
        db_session.commit()
        general_after_optin = client.get("/graph", params={"include_isolated": "true"})
        assert "SCOPED.CBL" in _code_file_paths(general_after_optin.json())
    finally:
        db_session.query(Project).filter(Project.id == test_project).update(
            {"expose_code_analysis_globally": False}
        )
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_general_graph_hides_project_documents_and_git_source_chunks(
    client, db_session, test_project, test_team
):
    """Projektgebundene Chunks bleiben auch dann im Projektkontext, wenn es sich
    um echte Dokumentation wie ein PDF/Confluence-Dokument handelt."""
    git_source = KnowledgeSource(
        name="scope-git-source",
        type="Git",
        url="https://example.test/scope2.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    doc_source = KnowledgeSource(
        name="scope-confluence-source",
        type="Confluence",
        url="https://example.test/wiki",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add_all([git_source, doc_source])
    db_session.flush()
    git_chunk = DocumentChunk(
        project_id=test_project,
        source_id=git_source.id,
        file_path="SCOPED.CBL",
        content="SCOPED source",
        start_line=1,
        end_line=10,
    )
    doc_chunk = DocumentChunk(
        project_id=test_project,
        source_id=doc_source.id,
        file_path="Runbook",
        content="Real documentation",
        start_line=1,
        end_line=1,
    )
    db_session.add_all([git_chunk, doc_chunk])
    db_session.commit()
    db_session.refresh(git_chunk)
    db_session.refresh(doc_chunk)

    try:
        # Ein Projekt-Chunk erscheint erst, wenn ihn eine genehmigte Beziehung
        # in den Graph aufnimmt.
        scoped = client.get(
            "/graph", params={"project_id": test_project, "include_isolated": "true"}
        )
        assert scoped.status_code == 200
        assert "SCOPED.CBL" not in _doc_node_ids(scoped.json())
        assert "Runbook" not in _doc_node_ids(scoped.json())

        # "Allgemein" -- kein projektgebundener Chunk ist sichtbar.
        general = client.get("/graph", params={"include_isolated": "true"})
        assert general.status_code == 200
        general_docs = _doc_node_ids(general.json())
        assert "SCOPED.CBL" not in general_docs
        assert "Runbook" not in general_docs

        # Das Opt-in betrifft nur Code-Analyse; die Doku bleibt projektgebunden.
        db_session.query(Project).filter(Project.id == test_project).update(
            {"expose_code_analysis_globally": True}
        )
        db_session.commit()
        general_after_optin = client.get("/graph", params={"include_isolated": "true"})
        assert "SCOPED.CBL" not in _doc_node_ids(general_after_optin.json())
        assert "Runbook" not in _doc_node_ids(general_after_optin.json())
    finally:
        db_session.query(Project).filter(Project.id == test_project).update(
            {"expose_code_analysis_globally": False}
        )
        db_session.query(KnowledgeSource).filter(
            KnowledgeSource.id.in_([git_source.id, doc_source.id])
        ).delete(synchronize_session=False)
        db_session.commit()


def test_graph_document_nodes_require_an_approved_relationship(
    client, db_session, test_project, test_team
):
    source = KnowledgeSource(
        name="approved-document-links",
        type="Local",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(
        project_id=test_project,
        source_id=source.id,
        file_path="APP.CBL",
        name="APP",
        qualified_name="APP",
        type="program",
        start_line=1,
        end_line=10,
    )
    approved_chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="approved.md",
        content="Approved documentation",
        start_line=1,
        end_line=5,
        metadata_json={"title": "approved.md"},
    )
    pending_chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="pending.md",
        content="Unreviewed documentation",
        start_line=1,
        end_line=5,
        metadata_json={"title": "pending.md"},
    )
    unlinked_chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="unlinked.md",
        content="Unlinked documentation",
        start_line=1,
        end_line=5,
        metadata_json={"title": "unlinked.md"},
    )
    db_session.add_all([entity, approved_chunk, pending_chunk, unlinked_chunk])
    db_session.flush()
    links = [
        EntityDocLink(
            project_id=test_project,
            entity_id=entity.id,
            chunk_id=approved_chunk.id,
            doc_title="approved.md",
            source_type="local_document",
            status="approved",
        ),
        EntityDocLink(
            project_id=test_project,
            entity_id=entity.id,
            chunk_id=pending_chunk.id,
            doc_title="pending.md",
            source_type="local_document",
            status="pending",
        ),
    ]
    db_session.add_all(links)
    db_session.commit()
    link_ids = [link.id for link in links]

    try:
        response = client.get(
            "/graph", params={"project_id": test_project, "include_isolated": "true"}
        )
        assert response.status_code == 200
        nodes = _doc_node_ids(response.json())
        assert "approved.md" in nodes
        assert "pending.md" not in nodes
        assert "unlinked.md" not in nodes
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id.in_(link_ids)).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_general_graph_hides_project_documents_through_knowledge_links(
    client, db_session, test_project, test_team
):
    """Admin visibility must not let a project PDF re-enter Allgemein through
    an approved cross-source KnowledgeLink."""
    source = KnowledgeSource(
        name="scope-link-source", type="Local", project_id=test_project, team_id=test_team
    )
    db_session.add(source)
    db_session.flush()
    project_chunk = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="private.pdf",
        content="private project document",
        start_line=1,
        end_line=1,
    )
    global_chunk = DocumentChunk(
        project_id=None,
        source_id=None,
        file_path="global.md",
        content="global document",
        start_line=1,
        end_line=1,
    )
    db_session.add_all([project_chunk, global_chunk])
    db_session.flush()
    link = KnowledgeLink(
        source_a_type="document",
        source_a_chunk_id=global_chunk.id,
        source_a_title="global.md",
        source_b_type="document",
        source_b_chunk_id=project_chunk.id,
        source_b_title="private.pdf",
        status="approved",
        link_type="semantic",
    )
    db_session.add(link)
    db_session.commit()

    try:
        general = client.get("/graph", params={"include_isolated": "true"})
        assert general.status_code == 200
        docs = _doc_node_ids(general.json())
        # Die Kante wird verworfen, weil ihr anderes Ende projektgebunden und
        # im globalen Graph nicht sichtbar ist. Das globale Dokument bleibt
        # damit ebenfalls außerhalb des Graphen, statt isoliert aufzutauchen.
        assert "global.md" not in docs
        assert "private.pdf" not in docs
    finally:
        db_session.delete(link)
        db_session.query(DocumentChunk).filter(
            DocumentChunk.id.in_([project_chunk.id, global_chunk.id])
        ).delete(synchronize_session=False)
        db_session.delete(source)
        db_session.commit()
