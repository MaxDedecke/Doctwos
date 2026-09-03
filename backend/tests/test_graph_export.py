"""Regressionstests für O-034: GET /graph/export liefert einen neutralen CSV-/
GraphML-Export des Wissensgraphen, analog zu /callgraph/export -- bisher gab
es dafür nur /graph/export/neo4j (Cypher, an Neo4j gebunden)."""
import csv
import io

from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource


def _fixture_graph(db, project_id, team_id):
    source = KnowledgeSource(name="graph-export-source", type="Git", url="https://example.test/export.git",
                             branch="main", project_id=project_id, team_id=team_id)
    db.add(source)
    db.flush()
    entity = CodeEntity(project_id=project_id, source_id=source.id, file_path="EXPORT.CBL",
                        name="EXPORT-PROGRAM", qualified_name="EXPORT-PROGRAM", type="program",
                        start_line=1, end_line=10)
    db.add(entity)
    db.flush()
    chunk = DocumentChunk(project_id=project_id, source_id=source.id, file_path="Runbook.md",
                          content="Runbook content", start_line=1, end_line=1,
                          metadata_json={"title": "Runbook"})
    db.add(chunk)
    db.flush()
    link = EntityDocLink(project_id=project_id, entity_id=entity.id, chunk_id=chunk.id,
                        doc_title="Runbook", source_type="local_document", score=0.87,
                        link_type="semantic", status="approved", context="passt inhaltlich")
    db.add(link)
    db.commit()
    db.refresh(entity)
    db.refresh(chunk)
    return source, entity, chunk, link


def test_graph_csv_export_contains_the_approved_link_as_an_edge_row(client, db_session, test_project, test_team):
    source, entity, chunk, link = _fixture_graph(db_session, test_project, test_team)
    try:
        response = client.get(f"/graph/export?format=csv&project_id={test_project}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]

        rows = list(csv.reader(io.StringIO(response.text)))
        assert rows[0] == ["source", "target", "link_type", "score", "context"]
        data_rows = {tuple(row) for row in rows[1:]}
        assert (f"entity:{entity.id}", "doc:Runbook", "semantic", "0.87", "passt inhaltlich") in data_rows
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_graphml_export_contains_matching_nodes_and_edge(client, db_session, test_project, test_team):
    source, entity, chunk, link = _fixture_graph(db_session, test_project, test_team)
    try:
        response = client.get(f"/graph/export?format=graphml&project_id={test_project}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/graphml+xml")

        body = response.text
        assert "graphml" in body
        assert f'<node id="entity:{entity.id}">' in body
        assert '<node id="doc:Runbook">' in body
        assert f'source="entity:{entity.id}"' in body
        assert 'target="doc:Runbook"' in body
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_export_rejects_unknown_format(client, db_session, test_project, test_team):
    response = client.get(f"/graph/export?format=xml&project_id={test_project}")
    assert response.status_code == 422


def test_graph_export_respects_project_visibility(client, db_session, test_project, test_team):
    """Dieselbe Sichtbarkeitsprüfung wie GET /graph selbst -- /export ruft
    get_graph() intern auf, statt die project_id ungeprüft durchzureichen."""
    source, entity, chunk, link = _fixture_graph(db_session, test_project, test_team)
    try:
        response = client.get("/graph/export?format=csv&project_id=999999")
        assert response.status_code == 404
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
