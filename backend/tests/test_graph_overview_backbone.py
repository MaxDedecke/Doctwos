"""Grundgerüst der Graph-Übersicht: Ab einer Größe zeigt die Übersicht je Datei nur die gewichtigsten
Dateikanten, aber jede vernetzte Datei. Jeder Knoten trägt seine echte Verbindungszahl (`degree`),
damit das Frontend die übrigen Kanten als nicht geladen anzeigen und nachladen kann."""

from unittest.mock import patch

from sqlalchemy import text

import pytest

from api.graph import _code_file_id
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource
from doctus_models.code_file_edges import rebuild_code_file_edges
from services.graph_overview_backbone import load_code_file_graph

BACKBONE = "doctus_models.code_file_edges"


@pytest.fixture
def hub_graph(db_session, test_project, test_team):
    """HUB ruft A, importiert B fünfmal, nutzt Daten aus C; D ruft HUB; A ruft B; COBOL kopiert ein
    Copybook. Die Import-Kante ist die zahlenmäßig stärkste, inhaltlich aber die schwächste."""
    source = KnowledgeSource(
        name="backbone-source",
        type="Git",
        url="https://example.test/backbone.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    files = {}
    for name, kind in [
        ("HUB", "class"),
        ("A", "class"),
        ("B", "class"),
        ("C", "class"),
        ("D", "class"),
        ("PROG", "program"),
        ("FIELDS", "copybook"),
    ]:
        entity = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=f"{name}.{'cbl' if kind == 'program' else 'cpy' if kind == 'copybook' else 'java'}",
            name=name,
            qualified_name=name,
            type=kind,
            start_line=1,
            end_line=10,
        )
        db_session.add(entity)
        db_session.flush()
        files[name] = entity

    def edge(src, dst, kind, times=1):
        for _ in range(times):
            db_session.add(
                CodeEdge(
                    project_id=test_project,
                    source_id=source.id,
                    src_entity_id=files[src].id,
                    dst_entity_id=files[dst].id,
                    dst_name=dst,
                    type=kind,
                    resolution="resolved",
                )
            )

    edge("HUB", "A", "CALLS")
    edge("HUB", "B", "IMPORTS", times=5)
    edge("HUB", "C", "READS")
    edge("D", "HUB", "CALLS")
    edge("A", "B", "CALLS")
    edge("PROG", "FIELDS", "COPY")
    db_session.commit()
    yield source, files
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def _file_id(test_project, source, name):
    path = {"PROG": "PROG.cbl", "FIELDS": "FIELDS.cpy"}.get(name, f"{name}.java")
    return _code_file_id(test_project, source.id, path)


def _pairs(graph):
    return {(pair.source[2].split(".")[0], pair.target[2].split(".")[0]) for pair in graph.pairs}


def test_small_file_graphs_keep_every_file_edge(db_session, test_project, hub_graph):
    graph = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)
    assert graph.backbone is False
    assert graph.total_pairs == 6
    assert len(graph.pairs) == 6
    hub_to_a = next(pair for pair in graph.pairs if pair.target[2] == "A.java")
    assert hub_to_a.edge_types == ["CALLS"]


def test_backbone_prefers_strong_relationships_and_keeps_every_file(
    db_session, test_project, hub_graph
):
    source, _ = hub_graph
    with (
        patch(f"{BACKBONE}.BACKBONE_MIN_FILE_EDGES", 0),
        patch(f"{BACKBONE}.BACKBONE_EDGES_PER_NODE", 1),
        patch(f"{BACKBONE}.BACKBONE_MIN_PER_EDGE_TYPE", 0),
    ):
        graph = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)

    pairs = _pairs(graph)
    assert graph.backbone is True
    assert graph.total_pairs == 6
    # B ist trotz fünf Imports über den Aufruf aus A angebunden, die Import-Kante entfällt.
    assert ("HUB", "B") not in pairs
    assert ("A", "B") in pairs
    files = {name for pair in pairs for name in pair}
    assert files == {"HUB", "A", "B", "C", "D", "PROG", "FIELDS"}
    assert graph.degree[_file_id(test_project, source, "HUB")] == 4
    assert graph.degree[_file_id(test_project, source, "B")] == 2
    hub_to_c = next(pair for pair in graph.pairs if pair.target[2] == "C.java")
    assert hub_to_c.edge_count == 1


def test_backbone_keeps_representatives_of_every_relationship_type(
    db_session, test_project, hub_graph
):
    with (
        patch(f"{BACKBONE}.BACKBONE_MIN_FILE_EDGES", 0),
        patch(f"{BACKBONE}.BACKBONE_EDGES_PER_NODE", 1),
        patch(f"{BACKBONE}.BACKBONE_MIN_PER_EDGE_TYPE", 1),
    ):
        graph = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)
    assert ("HUB", "B") in _pairs(graph)
    assert {t for pair in graph.pairs for t in pair.edge_types} == {
        "CALLS",
        "IMPORTS",
        "READS",
        "COPY",
    }


def test_overview_ships_the_backbone_with_real_degrees(client, test_project, hub_graph):
    source, _ = hub_graph
    with (
        patch(f"{BACKBONE}.BACKBONE_MIN_FILE_EDGES", 0),
        patch(f"{BACKBONE}.BACKBONE_EDGES_PER_NODE", 1),
        patch(f"{BACKBONE}.BACKBONE_MIN_PER_EDGE_TYPE", 0),
    ):
        body = client.get(f"/graph?project_id={test_project}").json()

    assert body["edges_sampled"] is True
    hub_id = _file_id(test_project, source, "HUB")
    hub = next(node for node in body["nodes"] if node["id"] == hub_id)
    shipped = sum(1 for edge in body["edges"] if hub_id in (edge["source"], edge["target"]))
    assert hub["degree"] == 4
    assert shipped < 4
    b_id = _file_id(test_project, source, "B")
    assert any(node["id"] == b_id for node in body["nodes"])
    c_id = _file_id(test_project, source, "C")
    hub_to_c = next(e for e in body["edges"] if e["id"] == f"code-files:{hub_id}:{c_id}")
    assert hub_to_c["meta"]["edge_count"] == 1
    assert hub_to_c["meta"]["references"]


def test_overview_without_backbone_ships_every_edge(client, test_project, hub_graph):
    source, _ = hub_graph
    body = client.get(f"/graph?project_id={test_project}").json()
    assert body["edges_sampled"] is False
    for node in body["nodes"]:
        shipped = sum(1 for edge in body["edges"] if node["id"] in (edge["source"], edge["target"]))
        assert node["degree"] == shipped
    hub_id, b_id = _file_id(test_project, source, "HUB"), _file_id(test_project, source, "B")
    hub_to_b = next(e for e in body["edges"] if e["id"] == f"code-files:{hub_id}:{b_id}")
    assert hub_to_b["meta"]["edge_count"] == 5


def test_precomputed_file_edges_match_the_live_aggregation(db_session, test_project, hub_graph):
    with (
        patch(f"{BACKBONE}.BACKBONE_MIN_FILE_EDGES", 0),
        patch(f"{BACKBONE}.BACKBONE_EDGES_PER_NODE", 1),
        patch(f"{BACKBONE}.BACKBONE_MIN_PER_EDGE_TYPE", 0),
    ):
        live = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)
        assert rebuild_code_file_edges(db_session, test_project) == len(live.pairs) < 6
        db_session.commit()
    stored = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)

    assert live.precomputed is False
    assert stored.precomputed is True
    assert _pairs(stored) == _pairs(live)
    assert stored.degree == live.degree
    assert (stored.total_pairs, stored.backbone) == (live.total_pairs, live.backbone)
    a_to_b = next(p for p in stored.pairs if p.target[2] == "B.java" and p.source[2] == "A.java")
    assert a_to_b.edge_types == ["CALLS"] and len(a_to_b.sample_edge_ids) == 1


def test_rebuild_replaces_the_previous_state(db_session, test_project, hub_graph):
    source, files = hub_graph
    rebuild_code_file_edges(db_session, test_project)
    db_session.commit()
    db_session.query(CodeEdge).filter(CodeEdge.src_entity_id == files["PROG"].id).delete()
    rebuild_code_file_edges(db_session, test_project)
    db_session.commit()
    graph = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)
    assert graph.total_pairs == 5
    assert ("PROG", "FIELDS") not in _pairs(graph)


def test_deleting_a_source_requests_a_rebuild(client, db_session, test_project, hub_graph):
    source, _ = hub_graph
    rebuild_code_file_edges(db_session, test_project)
    db_session.commit()
    with patch("api.knowledge_sources.celery_app.send_task") as send_task:
        assert client.delete(f"/knowledge-sources/{source.id}").status_code == 200
    send_task.assert_called_once_with("rebuild_code_file_edges", args=[test_project])
    remaining = db_session.execute(
        text("SELECT count(*) FROM code_file_edges WHERE project_id = :p"), {"p": test_project}
    ).scalar_one()
    assert remaining == 0


def _crowded_entry_graph(db_session, test_project, test_team, *, kind, ext, hub_kind, hub_ext, hub_edge):
    """ENTRY ruft NEXT1 und NEXT2 je einmal und nutzt vier Hub-Dateien je achtmal. Dieselben Hubs
    nutzen auch sechs andere Dateien, und auch NEXT1/NEXT2 hängen an drei Hubs: Nach Zahl der
    Einzelbeziehungen verdrängen die Hub-Kanten den Aufruf an beiden Enden."""
    source = KnowledgeSource(
        name=f"crowded-{ext}",
        type="Git",
        url=f"https://example.test/crowded-{ext}.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()

    def entity(name, type_, extension):
        item = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=f"{name}.{extension}",
            name=name,
            qualified_name=name,
            type=type_,
            start_line=1,
            end_line=10,
        )
        db_session.add(item)
        db_session.flush()
        return item

    def edge(src, dst, kind_, times=1):
        for _ in range(times):
            db_session.add(
                CodeEdge(
                    project_id=test_project,
                    source_id=source.id,
                    src_entity_id=src.id,
                    dst_entity_id=dst.id,
                    dst_name=dst.name,
                    type=kind_,
                    resolution="resolved",
                )
            )

    entry = entity("ENTRY", kind, ext)
    nexts = [entity(f"NEXT{i}", kind, ext) for i in (1, 2)]
    hubs = [entity(f"HUB{i}", hub_kind, hub_ext) for i in range(4)]
    users = [entity(f"USER{i}", kind, ext) for i in range(6)]
    for target in nexts:
        edge(entry, target, "CALL" if kind == "program" else "CALLS")
        for hub in hubs[:3]:
            edge(target, hub, hub_edge, times=8)
    for hub in hubs:
        edge(entry, hub, hub_edge, times=8)
        for user in users:
            edge(user, hub, hub_edge, times=8)
    db_session.commit()
    yield source
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


@pytest.fixture
def crowded_cobol(db_session, test_project, test_team):
    yield from _crowded_entry_graph(
        db_session, test_project, test_team,
        kind="program", ext="cbl", hub_kind="copybook", hub_ext="cpy", hub_edge="COPY",
    )


@pytest.fixture
def crowded_java(db_session, test_project, test_team):
    yield from _crowded_entry_graph(
        db_session, test_project, test_team,
        kind="class", ext="java", hub_kind="class", hub_ext="java", hub_edge="CALLS",
    )


def _backbone_pairs(db_session, test_project):
    with (
        patch(f"{BACKBONE}.BACKBONE_MIN_FILE_EDGES", 0),
        patch(f"{BACKBONE}.BACKBONE_EDGES_PER_NODE", 3),
        patch(f"{BACKBONE}.BACKBONE_MIN_PER_EDGE_TYPE", 0),
    ):
        graph = load_code_file_graph(db_session, test_project, [], _code_file_id, max_pairs=1000)
    return graph, _pairs(graph)


def test_cobol_backbone_keeps_calls_between_programs_despite_hub_copybooks(
    db_session, test_project, crowded_cobol
):
    graph, pairs = _backbone_pairs(db_session, test_project)
    assert graph.backbone is True
    assert {("ENTRY", "NEXT1"), ("ENTRY", "NEXT2")} <= pairs


def test_java_backbone_keeps_calls_to_rarely_used_classes_despite_hub_classes(
    db_session, test_project, crowded_java
):
    graph, pairs = _backbone_pairs(db_session, test_project)
    assert graph.backbone is True
    assert {("ENTRY", "NEXT1"), ("ENTRY", "NEXT2")} <= pairs
