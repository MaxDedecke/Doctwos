"""
Regressionstests für O-053: GET /graph (Knowledge-Graph-Übersicht) lud bisher
jede sichtbare Code-Entity und jeden Dokument-Chunk unbegrenzt -- bei einem
großen COBOL-Bestand (Ziel-Skalierung laut CLAUDE.md Prinzip 4) sowohl ein
Server- (Antwortgröße) als auch ein Client-Risiko (Kraftsimulation im
Browser-Hauptthread). Analog zu callgraph.py's MAX_NODES-Deckel (F-066), aber
über KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES konfigurierbar und mit Priorisierung
der am dichtesten verlinkten Knoten beim Kappen (die Übersicht zeigt bewusst
auch unverlinkte Entities -- die sind beim Kappen der uninteressanteste Teil).
"""
from unittest.mock import patch

from models.database import CodeEntity, DocumentChunk, EntityDocLink, KnowledgeSource


def _make_source(db, project_id, team_id):
    source = KnowledgeSource(name="truncation-test-source", type="Git", url="https://example.test/trunc.git",
                             branch="main", project_id=project_id, team_id=team_id)
    db.add(source)
    db.flush()
    return source


def _make_linked_entity(db, project_id, source_id, index):
    """An entity with one approved doc link -- degree 1, should survive capping
    ahead of anything unlinked."""
    entity = CodeEntity(project_id=project_id, source_id=source_id, file_path=f"LINKED{index}.CBL",
                        name=f"LINKED-{index}", qualified_name=f"LINKED-{index}", type="program",
                        start_line=1, end_line=10)
    db.add(entity)
    db.flush()
    chunk = DocumentChunk(project_id=project_id, source_id=source_id, file_path=f"Runbook{index}.md",
                          content="content", start_line=1, end_line=1,
                          metadata_json={"title": f"Runbook{index}"})
    db.add(chunk)
    db.flush()
    link = EntityDocLink(project_id=project_id, entity_id=entity.id, chunk_id=chunk.id,
                        doc_title=f"Runbook{index}", source_type="local_document", score=0.9,
                        link_type="semantic", status="approved", context=None)
    db.add(link)
    db.flush()
    return entity, chunk, link


def _make_isolated_entity(db, project_id, source_id, index):
    """An entity with no links at all -- degree 0, should be the first dropped."""
    entity = CodeEntity(project_id=project_id, source_id=source_id, file_path=f"ISOLATED{index}.CBL",
                        name=f"ISOLATED-{index}", qualified_name=f"ISOLATED-{index}", type="program",
                        start_line=1, end_line=10)
    db.add(entity)
    db.flush()
    return entity


def _make_double_linked_entity(db, project_id, source_id):
    """One entity linked to two documents -- degree 2, clearly outranking any
    single-link (degree 1) node when capping."""
    entity = CodeEntity(project_id=project_id, source_id=source_id, file_path="DOUBLE.CBL",
                        name="DOUBLE-LINKED", qualified_name="DOUBLE-LINKED", type="program",
                        start_line=1, end_line=10)
    db.add(entity)
    db.flush()
    links = []
    for suffix in ("a", "b"):
        chunk = DocumentChunk(project_id=project_id, source_id=source_id, file_path=f"Runbook3{suffix}.md",
                              content="content", start_line=1, end_line=1,
                              metadata_json={"title": f"Runbook3{suffix}"})
        db.add(chunk)
        db.flush()
        link = EntityDocLink(project_id=project_id, entity_id=entity.id, chunk_id=chunk.id,
                            doc_title=f"Runbook3{suffix}", source_type="local_document", score=0.9,
                            link_type="semantic", status="approved", context=None)
        db.add(link)
        db.flush()
        links.append(link)
    return entity, links


def test_graph_overview_is_not_truncated_below_the_cap(client, db_session, test_project, test_team):
    source = _make_source(db_session, test_project, test_team)
    entity, chunk, link = _make_linked_entity(db_session, test_project, source.id, 0)
    db_session.commit()
    try:
        response = client.get(f"/graph?project_id={test_project}")
        assert response.status_code == 200
        body = response.json()

        assert body["truncated"] is False
        assert body["total_nodes"] == len(body["nodes"])
        assert body["total_edges"] == len(body["edges"])
        assert any(n["id"] == f"entity:{entity.id}" for n in body["nodes"])
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_overview_truncates_and_reports_the_true_totals_when_over_the_cap(client, db_session, test_project, test_team):
    source = _make_source(db_session, test_project, test_team)
    linked_entity, chunk, link = _make_linked_entity(db_session, test_project, source.id, 1)
    isolated_entity = _make_isolated_entity(db_session, test_project, source.id, 1)
    db_session.commit()
    try:
        # Cap so low that only the linked entity (degree 1) and its doc node
        # (degree 1) fit -- the unlinked entity (degree 0) must be the one cut.
        with patch("api.graph.cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES", 2):
            response = client.get(f"/graph?project_id={test_project}")
        assert response.status_code == 200
        body = response.json()

        assert body["truncated"] is True
        assert len(body["nodes"]) == 2
        assert body["total_nodes"] == 3  # linked entity + isolated entity + doc node
        assert body["total_edges"] == 1

        node_ids = {n["id"] for n in body["nodes"]}
        assert f"entity:{linked_entity.id}" in node_ids
        assert "doc:Runbook1" in node_ids
        assert f"entity:{isolated_entity.id}" not in node_ids
    finally:
        db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_graph_overview_truncation_drops_edges_whose_far_end_did_not_survive(client, db_session, test_project, test_team):
    """A degree-2 entity linked to two documents, capped to fit the entity plus
    only one of the two docs: the edge to the doc that got cut must not appear
    in the response with a target nothing else in it points to."""
    source = _make_source(db_session, test_project, test_team)
    entity, links = _make_double_linked_entity(db_session, test_project, source.id)
    db_session.commit()
    try:
        # 3 candidate nodes (entity, doc:Runbook3a, doc:Runbook3b), cap = 2.
        # "doc:Runbook3a" sorts before "doc:Runbook3b" alphabetically, so given
        # both have the same degree (1), it wins the tie-break deterministically.
        with patch("api.graph.cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES", 2):
            response = client.get(f"/graph?project_id={test_project}")
        assert response.status_code == 200
        body = response.json()

        assert body["truncated"] is True
        node_ids = {n["id"] for n in body["nodes"]}
        assert node_ids == {f"entity:{entity.id}", "doc:Runbook3a"}

        assert len(body["edges"]) == 1
        edge = body["edges"][0]
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert edge["target"] == "doc:Runbook3a"
    finally:
        for link in links:
            db_session.query(EntityDocLink).filter(EntityDocLink.id == link.id).delete()
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
