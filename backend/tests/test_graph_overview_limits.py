from unittest.mock import patch

from api.graph import _capped_overview
from services.graph_overview_limits import code_edge_budget, overview_node_limit


def test_raw_relationship_loading_stays_bounded_when_display_limit_increases():
    with (
        patch("core.config.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES", 10000),
        patch("core.config.KNOWLEDGE_GRAPH_OVERVIEW_MAX_CODE_EDGES", 100000),
    ):
        assert code_edge_budget(2000) == 40000
        assert code_edge_budget(None) == 100000
        assert overview_node_limit(1000000) == 10000
        assert code_edge_budget(1000000) == 100000


def test_overview_accepts_ten_thousand_connected_nodes_and_reports_truncation():
    nodes = {str(i): {"id": str(i), "type": "code_file"} for i in range(10001)}
    edges = [{"source": str(i), "target": str(i + 1)} for i in range(10000)]
    with patch("core.config.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES", 10000):
        result = _capped_overview(nodes, edges, limit=1000000)
    assert len(result["nodes"]) == 10000
    assert result["total_nodes"] == 10001
    assert result["truncated"] is True
    ids = {node["id"] for node in result["nodes"]}
    assert all(edge["source"] in ids and edge["target"] in ids for edge in result["edges"])
