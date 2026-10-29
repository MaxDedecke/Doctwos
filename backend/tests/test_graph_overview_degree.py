"""Übersichtsknoten tragen ihre echte Verbindungszahl (`degree`), auch wenn die Code-Beziehungen
nur als Stichprobe geladen wurden. Das Frontend zeigt die Differenz als nicht geladene Kanten an."""

from unittest.mock import patch

from api.graph import _code_file_id
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource


def _hub_graph(db, project_id, team_id):
    source = KnowledgeSource(
        name="degree-source",
        type="Git",
        url="https://example.test/degree.git",
        branch="main",
        project_id=project_id,
        team_id=team_id,
    )
    db.add(source)
    db.flush()

    def entity(path, name):
        item = CodeEntity(
            project_id=project_id,
            source_id=source.id,
            file_path=path,
            name=name,
            qualified_name=name,
            type="program",
            start_line=1,
            end_line=10,
        )
        db.add(item)
        db.flush()
        return item

    hub, hub_para = entity("HUB.CBL", "HUB"), entity("HUB.CBL", "HUB-PARA")
    a, b, c = entity("A.CBL", "A"), entity("B.CBL", "B"), entity("C.CBL", "C")

    def edge(src, dst, kind="CALL"):
        db.add(
            CodeEdge(
                project_id=project_id,
                source_id=source.id,
                src_entity_id=src.id,
                dst_entity_id=dst.id if dst else None,
                dst_name=dst.name if dst else "EXTERNAL",
                type=kind,
                resolution="resolved" if dst else "unresolved",
            )
        )

    # Zwei Beziehungen HUB -> A ergeben eine Dateikante; dateiinterne und unaufgelöste zählen nicht.
    edge(hub, a)
    edge(hub_para, a, "PERFORM")
    edge(hub, b)
    edge(c, hub)
    edge(hub, hub_para, "PERFORM")
    edge(hub, None)
    db.commit()
    return source


def _shipped_degree(body, node_id):
    return sum(1 for e in body["edges"] if node_id in (e["source"], e["target"]))


def test_overview_degree_counts_all_file_connections_when_code_edges_are_sampled(
    client, db_session, test_project, test_team
):
    source = _hub_graph(db_session, test_project, test_team)
    hub_id = _code_file_id(test_project, source.id, "HUB.CBL")
    try:
        with patch("api.graph._code_edge_budget", return_value=1):
            body = client.get(f"/graph?project_id={test_project}").json()
        assert body["edges_sampled"] is True
        hub = next(n for n in body["nodes"] if n["id"] == hub_id)
        assert hub["degree"] == 3
        assert _shipped_degree(body, hub_id) < 3
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()


def test_overview_degree_matches_shipped_edges_without_sampling(
    client, db_session, test_project, test_team
):
    source = _hub_graph(db_session, test_project, test_team)
    try:
        body = client.get(f"/graph?project_id={test_project}").json()
        assert body["edges_sampled"] is False
        for node in body["nodes"]:
            assert node["degree"] == _shipped_degree(body, node["id"])
        hub = next(
            n for n in body["nodes"] if n["id"] == _code_file_id(test_project, source.id, "HUB.CBL")
        )
        assert hub["degree"] == 3
    finally:
        db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
        db_session.commit()
