"""Graph-Übersicht mit Gruppen-Knoten: eingeklappt, aufgeklappt, Topics und Dokument-Kanten."""

from unittest.mock import patch

import pytest

from doctus_models.code_file_edges import rebuild_code_file_edges
from doctus_models.code_file_groups import rebuild_code_file_groups
from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeSource,
    Topic,
    TopicNode,
)

GROUPS = "services.graph_overview_groups.BACKBONE_MIN_FILE_EDGES"


@pytest.fixture
def grouped_project(db_session, test_project, test_team):
    source = KnowledgeSource(
        name="grouped-source",
        type="Git",
        url="https://example.test/grouped.git",
        branch="main",
        project_id=test_project,
        team_id=test_team,
    )
    db_session.add(source)
    db_session.flush()
    entities = {}
    for name in ["A0", "A1", "A2", "B0", "B1", "B2"]:
        entity = CodeEntity(
            project_id=test_project,
            source_id=source.id,
            file_path=f"{name[0]}/{name}.java",
            name=name,
            qualified_name=name,
            type="class",
            start_line=1,
            end_line=5,
        )
        db_session.add(entity)
        db_session.flush()
        entities[name] = entity
    for a, b in [
        ("A0", "A1"),
        ("A1", "A2"),
        ("A0", "A2"),
        ("B0", "B1"),
        ("B1", "B2"),
        ("B0", "B2"),
        ("A0", "B0"),
    ]:
        db_session.add(
            CodeEdge(
                project_id=test_project,
                source_id=source.id,
                src_entity_id=entities[a].id,
                dst_entity_id=entities[b].id,
                dst_name=b,
                type="CALLS",
                resolution="resolved",
            )
        )
    handbook = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="Handbuch.md",
        content="Handbuch",
        start_line=1,
        end_line=1,
        metadata_json={"title": "Handbuch"},
    )
    runbook = DocumentChunk(
        project_id=test_project,
        source_id=source.id,
        file_path="Runbook.md",
        content="Runbook",
        start_line=1,
        end_line=1,
        metadata_json={"title": "Runbook"},
    )
    db_session.add_all([handbook, runbook])
    db_session.flush()
    db_session.add(
        EntityDocLink(
            project_id=test_project,
            entity_id=entities["A1"].id,
            chunk_id=runbook.id,
            doc_title="Runbook",
            source_type="local_document",
            score=0.9,
            link_type="semantic",
            status="approved",
        )
    )
    topic = Topic(project_id=test_project, name="Abrechnung", color="emerald")
    db_session.add(topic)
    db_session.flush()
    db_session.add_all(
        [
            TopicNode(
                topic_id=topic.id, node_type="entity", node_id=entities["B2"].id, node_label="B2"
            ),
            TopicNode(
                topic_id=topic.id, node_type="document", node_id=handbook.id, node_label="Handbuch"
            ),
        ]
    )
    db_session.commit()
    rebuild_code_file_edges(db_session, test_project)
    rebuild_code_file_groups(db_session, test_project)
    db_session.commit()
    yield source, topic
    db_session.query(Topic).filter(Topic.id == topic.id).delete()
    db_session.query(EntityDocLink).filter(EntityDocLink.project_id == test_project).delete()
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def _overview(client, project_id, expanded=()):
    with patch(GROUPS, 0):
        params = {"project_id": project_id}
        if expanded:
            params["expanded"] = ",".join(expanded)
        body = client.get("/graph", params=params).json()
    nodes = {n["id"]: n for n in body["nodes"]}
    return body, nodes


def test_collapsed_overview_shows_groups_bundles_code_and_redirects_document_edges(
    client, test_project, grouped_project
):
    _, topic = grouped_project
    body, nodes = _overview(client, test_project)
    assert body["grouped"] is True
    groups = {n["group_key"]: n for n in nodes.values() if n["type"] == "group"}
    assert not [n for n in nodes.values() if n["type"] == "code_file"]
    topic_group = groups[f"t{topic.id}"]
    assert (topic_group["label"], topic_group["topic_color"]) == ("Abrechnung", "emerald")
    assert topic_group["file_count"] == 1 and topic_group["doc_count"] == 1
    # Das Handbuch gehört zum Topic und steckt in dessen Gruppe; das Runbook bleibt eigener Knoten.
    assert not [n for n in nodes.values() if n.get("label") == "Handbuch"]
    runbook = next(n for n in nodes.values() if n.get("label") == "Runbook")
    documented = next(e for e in body["edges"] if runbook["id"] in (e["source"], e["target"]))
    assert {documented["source"], documented["target"]} - {runbook["id"]} <= {
        n["id"] for n in groups.values()
    }
    code = [e for e in body["edges"] if e["link_type"] == "code_dependency"]
    assert code and all(
        e["source"].startswith("group:") and e["target"].startswith("group:") for e in code
    )
    assert sum(e["meta"]["edge_count"] for e in code) == 3


def test_expanding_a_group_shows_its_files_with_detailed_and_bundled_edges(
    client, test_project, grouped_project
):
    _, collapsed = _overview(client, test_project)
    a_group = next(
        n for n in collapsed.values() if n["type"] == "group" and n["central_file"].startswith("A/")
    )
    body, nodes = _overview(client, test_project, [a_group["group_key"]])
    assert body["expanded"] == [a_group["group_key"]]
    files = {n["file_path"]: n for n in nodes.values() if n["type"] == "code_file"}
    assert set(files) == {"A/A0.java", "A/A1.java", "A/A2.java"}
    assert all(f["group_parent"] == a_group["group_key"] for f in files.values())
    assert all(f["group_parent_label"] == a_group["label"] for f in files.values())
    assert a_group["id"] not in nodes
    inner = [e for e in body["edges"] if e["id"].startswith("code-files:")]
    assert len(inner) == 3 and all(e["meta"]["references"] for e in inner)
    outward = [
        e
        for e in body["edges"]
        if e["link_type"] == "code_dependency"
        and e["source"].startswith("file:")
        and e["target"].startswith("group:")
    ]
    assert [e["source"] for e in outward] == [files["A/A0.java"]["id"]]


def test_expanding_a_topic_shows_its_documents(client, test_project, grouped_project):
    _, topic = grouped_project
    body, nodes = _overview(client, test_project, [f"t{topic.id}"])
    handbook = next(n for n in nodes.values() if n.get("label") == "Handbuch")
    assert handbook["group_parent"] == f"t{topic.id}"
    assert any(n.get("file_path") == "B/B2.java" for n in nodes.values())


def test_small_projects_and_disabled_grouping_keep_the_file_overview(
    client, test_project, grouped_project
):
    body = client.get("/graph", params={"project_id": test_project}).json()
    assert "grouped" not in body
    with patch(GROUPS, 0):
        body = client.get("/graph", params={"project_id": test_project, "group": "false"}).json()
    assert "grouped" not in body


def test_grouped_nodes_carry_their_real_connection_count(client, test_project, grouped_project):
    _, collapsed = _overview(client, test_project)
    runbook = next(n for n in collapsed.values() if n.get("label") == "Runbook")
    # Die einzige Verbindung des Runbooks zeigt in eine eingeklappte Gruppe: gebündelt, also verdeckt.
    assert runbook["degree"] == 1
    a_group = next(
        n for n in collapsed.values() if n["type"] == "group" and n["central_file"].startswith("A/")
    )
    body, nodes = _overview(client, test_project, [a_group["group_key"]])
    a0 = next(n for n in nodes.values() if n.get("file_path") == "A/A0.java")
    individual = [
        e
        for e in body["edges"]
        if a0["id"] in (e["source"], e["target"]) and not (e.get("meta") or {}).get("bundled")
    ]
    assert a0["degree"] == len(individual) + 1


def test_neighborhood_names_the_group_of_files_shown_on_their_own(
    client, test_project, grouped_project
):
    _, collapsed = _overview(client, test_project)
    runbook = next(n for n in collapsed.values() if n.get("label") == "Runbook")
    body = client.get(
        "/graph/neighborhood", params={"node_id": runbook["id"], "project_id": test_project}
    ).json()
    a1 = next(n for n in body["nodes"] if n.get("file_path") == "A/A1.java")
    assert a1["member_group"].startswith("c") and a1["member_group_label"]
