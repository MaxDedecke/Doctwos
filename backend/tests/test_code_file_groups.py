"""Gruppen-Knoten der Graph-Übersicht: Kopplungsgruppen (Louvain), Topics gehen vor."""

from unittest.mock import patch

import pytest

from sqlalchemy import text

from doctus_models.code_file_groups import build_groups, louvain, rebuild_code_file_groups
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, Topic, TopicNode


def _clique(prefix, size):
    names = [f"{prefix}{i}" for i in range(size)]
    return [(a, b) for i, a in enumerate(names) for b in names[i + 1 :]]


def _adjacency(edges):
    adjacency = {}
    for a, b in edges:
        adjacency.setdefault(a, {})[b] = adjacency.get(a, {}).get(b, 0) + 1
        adjacency.setdefault(b, {})[a] = adjacency.get(b, {}).get(a, 0) + 1
    return adjacency


def _file(name):
    return (1, 2, f"src/{name[0]}/{name}.java")


def _pairs(edges, kind="CALLS"):
    return [(_file(a), _file(b), 1, 3, [kind]) for a, b in edges]


def test_louvain_separates_two_loosely_joined_clusters_deterministically():
    edges = _clique("a", 6) + _clique("b", 6) + [("a0", "b0")]
    first = louvain(_adjacency(edges))
    assert first == louvain(_adjacency(edges))
    assert len({first[f"a{i}"] for i in range(6)}) == 1
    assert len({first[f"b{i}"] for i in range(6)}) == 1
    assert first["a0"] != first["b0"]


def test_groups_bundle_edges_between_communities_and_name_them():
    edges = _clique("a", 5) + _clique("b", 5) + [("a0", "b0"), ("a1", "b0")]
    groups, leaf, group_edges = build_groups(_pairs(edges), {}, {})
    assert [g.kind for g in groups] == ["community", "community"]
    assert leaf[_file("a0")] != leaf[_file("b0")]
    assert len(group_edges) == 1
    assert group_edges[0].edge_count == 2 and group_edges[0].file_edge_count == 2
    a_group = next(g for g in groups if g.key == leaf[_file("a0")])
    assert a_group.path_prefix == "src/a" and a_group.label.startswith("src/a · a")


@pytest.mark.parametrize(
    "ext, edge_type, hub_name",
    [("cbl", "COPY", "HUB.cpy"), ("java", "CALLS", "Hub.java")],
    ids=["cobol", "java"],
)
def test_group_is_named_after_a_file_that_uses_others_not_after_the_hub_everyone_uses(
    ext, edge_type, hub_name
):
    users = [(1, 2, f"src/P{i}.{ext}") for i in range(5)]
    hub = (1, 2, f"src/{hub_name}")
    pairs = [(user, hub, 9, 3, [edge_type]) for user in users]
    pairs += [(a, b, 1, 3, ["CALL"]) for a, b in zip(users, users[1:])]
    groups, _, _ = build_groups(pairs, {}, {})
    group = next(g for g in groups if hub in g.files)
    assert group.central_file != hub[2]
    assert group.central_file.startswith("src/P") and "HUB" not in group.label.upper()


def test_topics_take_precedence_and_the_smallest_topic_wins():
    edges = _clique("a", 5) + _clique("b", 5) + [("a0", "b0")]
    topics = {7: {_file("a0"), _file("a1")}, 8: {_file("a0")}}
    groups, leaf, group_edges = build_groups(_pairs(edges), topics, {7: 2, 8: 1})
    assert leaf[_file("a0")] == "t8"
    assert leaf[_file("a1")] == "t7"
    assert {g.key for g in groups if g.kind == "topic"} == {"t7", "t8"}
    assert all(leaf[_file(f"a{i}")].startswith("c") for i in range(2, 5))
    assert any(e.source == "t8" or e.target == "t8" for e in group_edges)


def test_large_communities_are_divided_into_subgroups():
    edges = _clique("a", 8) + _clique("b", 8) + [("a0", "b0")] * 2
    calls = []

    def coarse_first(adjacency, resolution=1.0):
        # The first pass returns one group for everything, as Louvain may for a dense graph.
        calls.append(len(adjacency))
        return {n: 0 for n in adjacency} if len(calls) == 1 else louvain(adjacency)

    with (
        patch("doctus_models.code_file_groups.GROUP_MAX_FILES", 10),
        patch("doctus_models.code_file_groups.louvain", side_effect=coarse_first),
    ):
        groups, leaf, _ = build_groups(_pairs(edges), {}, {})
    top = [g for g in groups if g.parent_key is None]
    children = [g for g in groups if g.parent_key == top[0].key]
    assert len(top) == 1 and top[0].files and len(top[0].files) == 16
    assert len(children) == 2 and all(c.level == 1 for c in children)
    assert set(leaf.values()) == {c.key for c in children}


@pytest.fixture
def hub_files(db_session, test_project, test_team):
    source = KnowledgeSource(
        name="groups-source",
        type="Git",
        url="https://example.test/groups.git",
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
    topic = Topic(project_id=test_project, name="Abrechnung")
    db_session.add(topic)
    db_session.flush()
    db_session.add(
        TopicNode(topic_id=topic.id, node_type="entity", node_id=entities["B2"].id, node_label="B2")
    )
    db_session.commit()
    yield topic
    db_session.query(Topic).filter(Topic.id == topic.id).delete()
    db_session.query(KnowledgeSource).filter(KnowledgeSource.id == source.id).delete()
    db_session.commit()


def test_rebuild_stores_groups_members_and_bundled_edges(db_session, test_project, hub_files):
    topic = hub_files
    assert rebuild_code_file_groups(db_session, test_project) == 3
    db_session.commit()
    groups = db_session.execute(
        text(
            "SELECT group_key, kind, topic_id, file_count FROM code_file_groups WHERE project_id = :p ORDER BY group_key"
        ),
        {"p": test_project},
    ).all()
    assert [(g.kind, g.file_count) for g in groups] == [
        ("community", 3),
        ("community", 2),
        ("topic", 1),
    ]
    members = dict(
        db_session.execute(
            text("SELECT file_path, group_key FROM code_file_group_members WHERE project_id = :p"),
            {"p": test_project},
        ).all()
    )
    assert members["B/B2.java"] == f"t{topic.id}"
    assert members["A/A0.java"] != members["B/B0.java"]
    edges = db_session.execute(
        text(
            "SELECT src_group_key, dst_group_key, edge_count FROM code_group_edges WHERE project_id = :p"
        ),
        {"p": test_project},
    ).all()
    assert {(e.src_group_key, e.dst_group_key) for e in edges} == {
        (members["A/A0.java"], members["B/B0.java"]),
        (members["B/B0.java"], f"t{topic.id}"),
        (members["B/B1.java"], f"t{topic.id}"),
    }


def test_very_large_projects_group_directories_instead_of_files(
    db_session, test_project, hub_files
):
    from doctus_models.code_file_edges import rebuild_code_file_edges

    rebuild_code_file_edges(db_session, test_project)
    with patch("doctus_models.code_file_groups.LOUVAIN_MAX_FILE_EDGES", 0):
        rebuild_code_file_groups(db_session, test_project)
    db_session.commit()
    members = dict(
        db_session.execute(
            text("SELECT file_path, group_key FROM code_file_group_members WHERE project_id = :p"),
            {"p": test_project},
        ).all()
    )
    # Dateien desselben Verzeichnisses landen in derselben Gruppe.
    assert members["A/A0.java"] == members["A/A1.java"] == members["A/A2.java"]
    assert members["B/B2.java"].startswith("t")
    counts = dict(
        db_session.execute(
            text("SELECT group_key, file_count FROM code_file_groups WHERE project_id = :p"),
            {"p": test_project},
        ).all()
    )
    key = members["A/A0.java"]
    assert counts[key] == sum(1 for group in members.values() if group == key)
