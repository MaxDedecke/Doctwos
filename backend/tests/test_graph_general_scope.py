"""Regressionstest für den ursprünglich gemeldeten Fehler: GET /graph ohne project_id
("Allgemein"-Wissensnetz/Graph-View) zeigte Code-Analyse-Objekte JEDES Projekts, auf
das der Nutzer irgendeine Team-/Projekt-Sichtbarkeit hatte -- unabhängig vom
Projekt-Kontext. Jetzt braucht das Ziel-Projekt dafür das explizite Opt-in
`expose_code_analysis_globally` (siehe core/projects.py, backend/api/graph.py)."""

from models.database import CodeEntity, DocumentChunk, KnowledgeSource, Project


def _entity_node_ids(response_json: dict) -> set[str]:
    return {n["id"] for n in response_json["nodes"] if n["type"] == "entity"}


def _doc_node_ids(response_json: dict) -> set[str]:
    return {n["id"] for n in response_json["nodes"] if n["type"] == "document"}


def test_general_graph_hides_project_entities_unless_opted_in(client, db_session, test_project, test_team):
    source = KnowledgeSource(name="scope-source", type="Git", url="https://example.test/scope.git",
                             branch="main", project_id=test_project, team_id=test_team)
    db_session.add(source)
    db_session.flush()
    entity = CodeEntity(project_id=test_project, source_id=source.id, file_path="SCOPED.CBL",
                        name="SCOPED", qualified_name="SCOPED", type="program", start_line=1, end_line=10)
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)

    try:
        # Innerhalb des eigenen Projekt-Kontexts (project_id mitgeschickt) immer sichtbar.
        scoped = client.get("/graph", params={"project_id": test_project})
        assert scoped.status_code == 200
        assert f"entity:{entity.id}" in _entity_node_ids(scoped.json())

        # "Allgemein" (kein project_id) -- default aus, Entity darf nicht auftauchen.
        general = client.get("/graph")
        assert general.status_code == 200
        assert f"entity:{entity.id}" not in _entity_node_ids(general.json())

        # Nach Opt-in erscheint dieselbe Entity auch im Allgemein-Graph.
        db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": True})
        db_session.commit()
        general_after_optin = client.get("/graph")
        assert f"entity:{entity.id}" in _entity_node_ids(general_after_optin.json())
    finally:
        db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": False})
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_general_graph_hides_git_source_chunks_but_keeps_real_docs(client, db_session, test_project, test_team):
    """Chunks einer Git-Wissensquelle sind rohe Repo-Quelldateien (Code-Analyse-Inhalt,
    keine echte Dokumentation) und folgen deshalb demselben Opt-in wie CodeEntity --
    sonst blieben sie in "Allgemein" als verwaiste Knoten übrig, sobald ihre
    zugehörigen Entities ausgeblendet sind (siehe build_document_chunk_code_gate).
    Chunks einer echten Doku-Quelle (hier: Confluence) bleiben davon unberührt."""
    git_source = KnowledgeSource(name="scope-git-source", type="Git", url="https://example.test/scope2.git",
                                  branch="main", project_id=test_project, team_id=test_team)
    doc_source = KnowledgeSource(name="scope-confluence-source", type="Confluence", url="https://example.test/wiki",
                                  project_id=test_project, team_id=test_team)
    db_session.add_all([git_source, doc_source])
    db_session.flush()
    git_chunk = DocumentChunk(project_id=test_project, source_id=git_source.id, file_path="SCOPED.CBL",
                               content="SCOPED source", start_line=1, end_line=10)
    doc_chunk = DocumentChunk(project_id=test_project, source_id=doc_source.id, file_path="Runbook",
                               content="Real documentation", start_line=1, end_line=1)
    db_session.add_all([git_chunk, doc_chunk])
    db_session.commit()
    db_session.refresh(git_chunk)
    db_session.refresh(doc_chunk)

    try:
        # Innerhalb des eigenen Projekt-Kontexts sind beide sichtbar.
        scoped = client.get("/graph", params={"project_id": test_project})
        assert scoped.status_code == 200
        assert {"doc:SCOPED.CBL", "doc:Runbook"} <= _doc_node_ids(scoped.json())

        # "Allgemein" -- der Git-Chunk ist ohne Opt-in nicht sichtbar, der echte
        # Doku-Chunk (Confluence) bleibt projektübergreifend sichtbar.
        general = client.get("/graph")
        assert general.status_code == 200
        general_docs = _doc_node_ids(general.json())
        assert "doc:SCOPED.CBL" not in general_docs
        assert "doc:Runbook" in general_docs

        # Nach Opt-in erscheint auch der Git-Chunk im Allgemein-Graph.
        db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": True})
        db_session.commit()
        general_after_optin = client.get("/graph")
        assert "doc:SCOPED.CBL" in _doc_node_ids(general_after_optin.json())
    finally:
        db_session.query(Project).filter(Project.id == test_project).update({"expose_code_analysis_globally": False})
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id.in_([git_source.id, doc_source.id])).delete(synchronize_session=False)
        db_session.commit()
