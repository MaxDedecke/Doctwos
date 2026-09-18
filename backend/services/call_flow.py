"""Directed, bounded call-flow traversal for the chat agent.

The regular call-graph view intentionally shows the neighbourhood around an
entity.  A question such as "what happens after this endpoint is called?"
needs a different projection: follow only outgoing calls, retain their
direction and return a compact sequence that can be rendered in chat.
"""

from __future__ import annotations

from html import escape
from typing import Literal

from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.database import CodeEdge, CodeEntity


CALL_FLOW_MAX_HOPS = 5
CALL_FLOW_MAX_NODES = 150
CALL_FLOW_EDGE_TYPES = {
    "CALL", "PERFORM", "GOTO", "COPY", "CALLS", "INSTANTIATES",
    "USES_RESOURCE", "INCLUDES", "IMPORTS", "TRANSFORMS_WITH", "READS_XML",
    "SOURCES", "EXECUTES_SCRIPT", "STARTS_JAVA", "REFERENCES_RESOURCE", "LINKS_TO",
}
CallFlowDirection = Literal["outgoing", "incoming", "both"]


def _node_json(entity: CodeEntity) -> dict:
    return {
        "id": entity.id,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "type": entity.type,
        "file_path": entity.file_path,
        "source_id": entity.source_id,
        "start_line": entity.start_line,
        "end_line": entity.end_line,
    }


def _mermaid_label(value: str) -> str:
    """Keep parser-provided names inert when placed in a Mermaid label."""
    # Mermaid's strict security mode is also enabled by the frontend.  Escaping
    # its syntax here keeps malformed or surprising symbol names from changing
    # the graph structure before they ever reach the renderer.
    return escape(value, quote=True).replace("[", "(").replace("]", ")").replace('"', "'")


def _to_mermaid(nodes: list[dict], edges: list[dict]) -> str:
    lines = ["flowchart TD"]
    declared: set[str] = set()

    def declare(identifier: str, label: str) -> None:
        if identifier not in declared:
            declared.add(identifier)
            lines.append(f'  {identifier}["{_mermaid_label(label)}"]')

    for node in nodes:
        declare(f"n{node['id']}", f"{node['name']} ({node['type']})")
    for edge in edges:
        source = f"n{edge['source']}"
        if edge["target"] is None:
            target = f"u{edge['id']}"
            declare(target, f"{edge['target_name']} (unaufgeloest)")
        else:
            target = f"n{edge['target']}"
        lines.append(f"  {source} -->|{_mermaid_label(edge['type'])}| {target}")
    return "\n".join(lines)


def trace_call_flow(
    db: Session,
    *,
    project_id: int,
    entity_id: int,
    hops: int = CALL_FLOW_MAX_HOPS,
    direction: CallFlowDirection = "outgoing",
) -> dict:
    """Return a directional call flow rooted at one indexed code entity.

    The agent is scoped to an already authorized project.  Still, querying the
    root with ``project_id`` prevents an entity ID from another project from
    ever leaking into a tool result.  The hard limits protect both the model
    context and a Mermaid diagram from fan-out-heavy applications.
    """
    if direction not in {"outgoing", "incoming", "both"}:
        return {"error": "direction must be outgoing, incoming, or both"}
    if not isinstance(hops, int) or isinstance(hops, bool):
        return {"error": "hops must be an integer"}
    hops = max(0, min(hops, CALL_FLOW_MAX_HOPS))

    root = (
        db.query(CodeEntity)
        .filter(CodeEntity.id == entity_id, CodeEntity.project_id == project_id)
        .first()
    )
    if root is None:
        return {"error": "Entity was not found in the current project"}

    seen = {root.id}
    frontier = {root.id}
    edge_rows: dict[int, CodeEdge] = {}
    truncated = False

    for _ in range(hops):
        if not frontier:
            break
        predicates = []
        if direction in {"outgoing", "both"}:
            predicates.append(CodeEdge.src_entity_id.in_(frontier))
        if direction in {"incoming", "both"}:
            predicates.append(CodeEdge.dst_entity_id.in_(frontier))
        rows = (
            db.query(CodeEdge)
            .filter(
                CodeEdge.project_id == project_id,
                CodeEdge.type.in_(CALL_FLOW_EDGE_TYPES),
                or_(*predicates),
            )
            .order_by(CodeEdge.id)
            .all()
        )
        next_frontier: set[int] = set()
        for edge in rows:
            edge_rows[edge.id] = edge
            for candidate in (edge.src_entity_id, edge.dst_entity_id):
                if candidate is None or candidate in seen:
                    continue
                if len(seen) >= CALL_FLOW_MAX_NODES:
                    truncated = True
                    continue
                seen.add(candidate)
                next_frontier.add(candidate)
        frontier = next_frontier

    entities = (
        db.query(CodeEntity).filter(CodeEntity.id.in_(seen)).order_by(CodeEntity.id).all()
    )
    nodes = [_node_json(entity) for entity in entities]
    edges = [
        {
            "id": edge.id,
            "source": edge.src_entity_id,
            "target": edge.dst_entity_id,
            "target_name": edge.dst_name,
            "type": edge.type,
            "resolution": edge.resolution,
            "meta": edge.meta_json or {},
            "start_line": edge.src_start_line,
            "end_line": edge.src_end_line,
        }
        for edge in edge_rows.values()
        if edge.src_entity_id in seen
        and (edge.dst_entity_id is None or edge.dst_entity_id in seen)
    ]
    return {
        "root": _node_json(root),
        "hops": hops,
        "direction": direction,
        "truncated": truncated,
        "nodes": nodes,
        "edges": edges,
        "mermaid": _to_mermaid(nodes, edges),
    }
