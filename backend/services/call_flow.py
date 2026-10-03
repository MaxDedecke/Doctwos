"""Directed, bounded call-flow traversal for the chat agent.

The regular call-graph view intentionally shows the neighbourhood around an
entity.  A question such as "what happens after this endpoint is called?"
needs a different projection: follow only outgoing calls, retain their
direction and return a compact sequence that can be rendered in chat.
"""

from __future__ import annotations

from html import escape
from typing import Literal

from sqlalchemy import case, or_
from sqlalchemy.orm import Session, aliased

from models.database import CodeEdge, CodeEntity


CALL_FLOW_MAX_HOPS = 5
CALL_FLOW_MAX_NODES = 150
CALL_FLOW_MAX_EDGES = 500
CALL_FLOW_EDGE_TYPES = {
    "CALL",
    "PERFORM",
    "GOTO",
    "COPY",
    "CALLS",
    "INSTANTIATES",
    "EXECUTES",
    "CONTAINS",
    "USES_DATASET",
    "READS",
    "WRITES",
    "USES_RESOURCE",
    "INCLUDES",
    "IMPORTS",
    "TRANSFORMS_WITH",
    "READS_XML",
    "SOURCES",
    "EXECUTES_SCRIPT",
    "STARTS_JAVA",
    "REFERENCES_RESOURCE",
    "REFERENCES_PROPERTY_KEY",
    "LINKS_TO",
}
CALL_EXECUTION_EDGE_TYPES = {
    "CALL", "PERFORM", "GOTO", "CALLS", "STARTS_JAVA", "EXECUTES_SCRIPT"
}
CALL_DEPENDENCY_EDGE_TYPES = CALL_FLOW_EDGE_TYPES - CALL_EXECUTION_EDGE_TYPES
CALL_FLOW_EDGE_PRIORITY = {
    "CALL": 0,
    "PERFORM": 0,
    "CALLS": 0,
    "EXECUTES": 0,
    "STARTS_JAVA": 0,
    "GOTO": 1,
    "READS": 1,
    "WRITES": 1,
}
CallFlowDirection = Literal["outgoing", "incoming", "both"]
CallFlowScope = Literal["execution", "dependencies", "all"]


# Verzeichnis `test`/`tests`/`src/test` oder Java-Testklassen (`FooTest`, `FooTests`, `FooIT`).
TEST_PATH_PATTERN = r"(^|/)(src/test|tests?)/|(Test|Tests|IT|ITCase)\.java$"


def _without_test_code(query):
    """Filtert Kanten, deren Aufrufer oder aufgelöstes Ziel in Testcode liegt."""
    src = aliased(CodeEntity)
    dst = aliased(CodeEntity)
    return (
        query.join(src, src.id == CodeEdge.src_entity_id)
        .outerjoin(dst, dst.id == CodeEdge.dst_entity_id)
        .filter(~src.file_path.op("~")(TEST_PATH_PATTERN))
        .filter(or_(dst.id.is_(None), ~dst.file_path.op("~")(TEST_PATH_PATTERN)))
    )


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
    scope: CallFlowScope = "all",
    node_limit: int = CALL_FLOW_MAX_NODES,
    edge_limit: int = CALL_FLOW_MAX_EDGES,
    include_tests: bool = True,
) -> dict:
    """Return a directional call flow rooted at one indexed code entity.

    The agent is scoped to an already authorized project.  Still, querying the
    root with ``project_id`` prevents an entity ID from another project from
    ever leaking into a tool result.  The hard limits protect both the model
    context and a Mermaid diagram from fan-out-heavy applications.

    ``include_tests=False`` (O-377) drops edges whose caller or resolved target
    lives in test code (see ``TEST_PATH_PATTERN``), so impact and caller
    questions are not dominated by JUnit/Mockito call sites.
    """
    if direction not in {"outgoing", "incoming", "both"}:
        return {"error": "direction must be outgoing, incoming, or both"}
    if scope not in {"execution", "dependencies", "all"}:
        return {"error": "scope must be execution, dependencies, or all"}
    if not isinstance(hops, int) or isinstance(hops, bool):
        return {"error": "hops must be an integer"}
    hops = max(0, min(hops, CALL_FLOW_MAX_HOPS))
    node_limit = max(1, min(int(node_limit), 1_000))
    edge_limit = max(1, min(int(edge_limit), 3_000))

    root = (
        db.query(CodeEntity)
        .filter(CodeEntity.id == entity_id, CodeEntity.project_id == project_id)
        .first()
    )
    if root is None:
        return {"error": "Entity was not found in the current project"}

    requested_root = root
    entry_resolution = "requested_entity"
    # COBOL callers often select a program (or its source file) while the
    # executable call edges are attached to internal paragraphs. Resolve only
    # a single conventional entry paragraph; otherwise return candidates and
    # let the caller choose explicitly.
    if direction == "outgoing" and root.type in {"program", "cobol_program"}:
        paragraphs = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.source_id == root.source_id,
                CodeEntity.variant_key == root.variant_key,
                CodeEntity.parent_id == root.id,
                CodeEntity.type.in_(["paragraph", "section"]),
            )
            .order_by(CodeEntity.start_line, CodeEntity.id)
            .limit(node_limit + 1)
            .all()
        )
        candidates_truncated = len(paragraphs) > node_limit
        named_entries = [
            item for item in paragraphs
            if item.name.casefold() in {"main-para", "main", "procedure-division", "procedure-start"}
            or (item.qualified_name or "").casefold().endswith((".main-para", ".main", ".procedure-division", ".procedure-start"))
        ]
        if not candidates_truncated and len(named_entries) == 1:
            root = named_entries[0]
            entry_resolution = "unique_cobol_entry"
        elif len(paragraphs) == 1:
            root = paragraphs[0]
            entry_resolution = "only_cobol_paragraph"
        elif paragraphs:
            return {
                "status": "entry_point_selection_required",
                "root": _node_json(root),
                "requested_root": _node_json(requested_root),
                "entry_resolution": "ambiguous_cobol_entry",
                "entry_candidates": [_node_json(item) for item in paragraphs[:node_limit]],
                "truncated": candidates_truncated,
                "nodes": [_node_json(root)],
                "edges": [],
                "mermaid": "",
                "notice": "Mehrere COBOL-Einstiegspunkte vorhanden. Wähle einen Absatz anhand der Quelle; es wurde keiner automatisch ausgewählt.",
            }
        else:
            return {
                "status": "entry_point_not_found",
                "root": _node_json(root),
                "requested_root": _node_json(requested_root),
                "entry_resolution": "missing_cobol_entry",
                "entry_candidates": [],
                "truncated": False,
                "nodes": [_node_json(root)],
                "edges": [],
                "mermaid": "",
                "notice": "Unter diesem COBOL-Programm ist kein Einstieg-Paragraph indexiert.",
            }
    if direction == "outgoing" and root.type in {"class", "interface", "enum", "record"}:
        methods = (
            db.query(CodeEntity)
            .filter(
                CodeEntity.project_id == project_id,
                CodeEntity.source_id == root.source_id,
                CodeEntity.variant_key == root.variant_key,
                CodeEntity.parent_id == root.id,
                CodeEntity.type == "method",
            )
            .order_by(CodeEntity.start_line, CodeEntity.id)
            .limit(node_limit + 1)
            .all()
        )
        candidates_truncated = len(methods) > node_limit
        mains = [method for method in methods if _is_java_main(method)]
        if not candidates_truncated and len(mains) == 1:
            root = mains[0]
            entry_resolution = "unique_java_main"
        elif len(methods) == 1:
            root = methods[0]
            entry_resolution = "only_method"
        elif methods:
            return {
                "status": "entry_point_selection_required",
                "root": _node_json(root),
                "requested_root": _node_json(root),
                "entry_candidates": [
                    _node_json(method) for method in methods[:node_limit]
                ],
                "truncated": candidates_truncated,
                "nodes": [_node_json(root)],
                "edges": [],
                "mermaid": "",
                "notice": "Mehrere Methoden vorhanden. Wähle den zur Frage passenden Einstieg "
                "anhand der Quellen oder frage nach; rufe trace_call_flow mit dessen ID erneut auf.",
            }

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
        remaining_edges = edge_limit - len(edge_rows)
        if scope == "execution":
            edge_filter = or_(
                CodeEdge.type.in_(CALL_EXECUTION_EDGE_TYPES),
                (CodeEdge.type == "EXECUTES")
                & (CodeEdge.meta_json["language"].as_string() == "jcl"),
            )
        elif scope == "dependencies":
            language = CodeEdge.meta_json["language"].as_string()
            edge_filter = or_(
                CodeEdge.type.in_(CALL_DEPENDENCY_EDGE_TYPES - {"EXECUTES"}),
                (CodeEdge.type == "EXECUTES")
                & or_(language.is_(None), language != "jcl"),
            )
        else:
            edge_filter = CodeEdge.type.in_(CALL_FLOW_EDGE_TYPES)
        query = db.query(CodeEdge).filter(
            CodeEdge.project_id == project_id,
            edge_filter,
            or_(*predicates),
        )
        if edge_rows:
            query = query.filter(CodeEdge.id.notin_(edge_rows))
        if not include_tests:
            query = _without_test_code(query)
        edge_priority = case(
            *[
                (CodeEdge.type == edge_type, priority)
                for edge_type, priority in CALL_FLOW_EDGE_PRIORITY.items()
            ],
            else_=2,
        )
        resolution_priority = case((CodeEdge.resolution == "resolved", 0), else_=1)
        rows = query.order_by(
            edge_priority,
            resolution_priority,
            CodeEdge.src_start_line,
            CodeEdge.id,
        ).limit(remaining_edges + 1).all()
        if len(rows) > remaining_edges:
            truncated = True
            rows = rows[:remaining_edges]
        next_frontier: set[int] = set()
        for edge in rows:
            edge_rows[edge.id] = edge
            for candidate in (edge.src_entity_id, edge.dst_entity_id):
                if candidate is None or candidate in seen:
                    continue
                if len(seen) >= node_limit:
                    truncated = True
                    continue
                seen.add(candidate)
                next_frontier.add(candidate)
        frontier = next_frontier
        if truncated:
            break

    entities = (
        db.query(CodeEntity)
        .filter(CodeEntity.id.in_(seen), CodeEntity.project_id == project_id)
        .order_by(CodeEntity.id)
        .all()
    )
    visible_ids = {entity.id for entity in entities}
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
        if edge.src_entity_id in visible_ids
        and (edge.dst_entity_id is None or edge.dst_entity_id in visible_ids)
    ]
    return {
        "root": _node_json(root),
        "requested_root": _node_json(requested_root),
        "entry_resolution": entry_resolution,
        "status": "ok" if edges else "no_indexed_calls",
        "notice": None
        if edges
        else "Für diesen Einstieg und die gewählte Tiefe/Richtung sind "
        "keine Aufrufkanten indexiert. Das belegt nicht, dass zur Laufzeit keine Aufrufe erfolgen.",
        "hops": hops,
        "direction": direction,
        "scope": scope,
        "truncated": truncated,
        "nodes": nodes,
        "edges": edges,
        "mermaid": _to_mermaid(nodes, edges),
    }


def _is_java_main(entity: CodeEntity) -> bool:
    meta = entity.meta_json or {}
    return (
        entity.file_path.endswith(".java")
        and entity.name == "main"
        and {"public", "static"}.issubset(meta.get("modifiers") or [])
        and meta.get("return_type") == "void"
        and meta.get("parameter_types")
        in (["String[]"], ["java.lang.String[]"], ["String..."], ["java.lang.String..."])
    )
