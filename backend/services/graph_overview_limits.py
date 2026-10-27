"""Independent display and raw code-edge budgets for the overview."""

from core import config as cfg

# Many entity-level relationships collapse into a single file dependency.
CODE_EDGES_PER_NODE_BUDGET = 20


def overview_node_limit(requested=None):
    configured = cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES
    return (
        min(requested, configured) if isinstance(requested, int) and requested > 0 else configured
    )


def code_edge_budget(requested=None):
    return min(
        overview_node_limit(requested) * CODE_EDGES_PER_NODE_BUDGET,
        cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_CODE_EDGES,
    )
