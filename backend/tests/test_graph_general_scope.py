"""Regressionstest für den ursprünglich gemeldeten Fehler: GET /graph ohne project_id
("Allgemein"-Wissensnetz/Graph-View) zeigte Code-Analyse-Objekte JEDES Projekts, auf
das der Nutzer irgendeine Team-/Projekt-Sichtbarkeit hatte -- unabhängig vom
Projekt-Kontext. Jetzt braucht das Ziel-Projekt dafür das explizite Opt-in
`expose_code_analysis_globally` (siehe core/projects.py, backend/api/graph.py)."""

from models.database import CodeEntity, KnowledgeSource, Project


def _entity_node_ids(response_json: dict) -> set[str]:
    return {n["id"] for n in response_json["nodes"] if n["type"] == "entity"}


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
