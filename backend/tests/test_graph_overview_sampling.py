from api.graph import _capped_overview


def _code(i, source_id=1):
    return {"id": f"file:{i}", "type": "code_file", "source_id": source_id}


def _doc(i, resource_type, source_id):
    return {
        "id": f"doc:{i}",
        "type": "document",
        "resource_type": resource_type,
        "source_id": source_id,
    }


def _edge(eid, src, tgt, link_type, relation_type=None, score=None):
    return {
        "id": eid,
        "source": src,
        "target": tgt,
        "link_type": link_type,
        "relation_type": relation_type,
        "score": score,
    }


def _busy_code_graph(count=40):
    """Ein dichtes Code-Geflecht, das die seltenen Arten sonst verdrängt."""
    nodes = {n["id"]: n for n in (_code(i) for i in range(count))}
    edges = [
        _edge(f"c{i}-{j}", f"file:{i}", f"file:{j}", "code_dependency", "code_dependency")
        for i in range(count)
        for j in range(count)
        if i != j
    ]
    return nodes, edges


def _add_rare_kinds(nodes, edges):
    for i in range(4):
        nodes[f"doc:j{i}"] = _doc(f"j{i}", "jira_issue", 9)
        edges.append(_edge(f"k{i}", f"doc:j{i}", f"file:{i}", "keyword", "documented", 0.9))
    for i in range(4):
        nodes[f"doc:l{i}"] = _doc(f"l{i}", "document", 7)
    for i in range(3):
        edges.append(_edge(f"s{i}", f"doc:l{i}", f"doc:l{i + 1}", "semantic"))


def test_every_node_and_edge_kind_is_represented_when_capped():
    nodes, edges = _busy_code_graph()
    _add_rare_kinds(nodes, edges)

    result = _capped_overview(nodes, edges, limit=20, min_per_kind=2)

    assert result["truncated"] is True
    kept = {n["id"]: n for n in result["nodes"]}
    assert len(kept) <= 20
    kinds = [(n["type"], n.get("resource_type")) for n in kept.values()]
    for kind in [("code_file", None), ("document", "jira_issue"), ("document", "document")]:
        assert kinds.count(kind) >= 2, kind
    edge_kinds = [(e["link_type"], e["relation_type"]) for e in result["edges"]]
    for kind in [
        ("code_dependency", "code_dependency"),
        ("keyword", "documented"),
        ("semantic", None),
    ]:
        assert edge_kinds.count(kind) >= 2, kind


def test_focus_source_fills_budget_with_its_nodes_and_their_neighbours():
    nodes, edges = _busy_code_graph()
    for i in range(10):
        nodes[f"doc:j{i}"] = _doc(f"j{i}", "jira_issue", 9)
        edges.append(_edge(f"k{i}", f"doc:j{i}", f"file:{i}", "keyword", "documented", 0.9))

    result = _capped_overview(nodes, edges, limit=14, min_per_kind=1, focus_source_id=9)

    kept = result["nodes"]
    assert len(kept) <= 14
    focus_nodes = [n for n in kept if n.get("source_id") == 9]
    # 70 % des Budgets gehören der Fokus-Quelle, der Rest ihren am stärksten verbundenen Nachbarn.
    assert len(focus_nodes) == 9
    focus_edges = [e for e in result["edges"] if e["link_type"] == "keyword"]
    assert len(focus_edges) >= 4


def test_focus_source_without_matches_behaves_like_the_default():
    nodes, edges = _busy_code_graph()
    default = _capped_overview(nodes, edges, limit=12, min_per_kind=1)
    focused = _capped_overview(nodes, edges, limit=12, min_per_kind=1, focus_source_id=404)

    assert {n["id"] for n in default["nodes"]} == {n["id"] for n in focused["nodes"]}


def test_rare_insight_is_reserved_before_edge_coverage_exhausts_budget():
    nodes, edges = _busy_code_graph()
    _add_rare_kinds(nodes, edges)
    nodes["insight:1"] = {"id": "insight:1", "type": "insight"}
    result = _capped_overview(nodes, edges, limit=8, min_per_kind=3)
    assert {n["type"] for n in result["nodes"]} == {"code_file", "document", "insight"}
    assert "insight:1" in {n["id"] for n in result["nodes"]}
    assert len(result["nodes"]) <= 8
