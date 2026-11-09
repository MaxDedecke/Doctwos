"""Eine Seite der Aufrufkette einer Routine mit Fakten, Gliederung und Datenzugriffen.

Genutzt von get_call_flow, research_project und der Erklärung einer Entität (aus mcp_server.py herausgelöst).
"""

import logging
import base64
import binascii
import json
import re

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from doctus_models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    User,
)
from services.call_flow import (
    CALL_FLOW_MAX_EDGES,
    CALL_FLOW_MAX_NODES,
    trace_call_flow,
)
from services.source_access import source_visible as _source_visible


from services.code_symbols import (
    _STRUCTURAL,
    _entity,
)

logger = logging.getLogger(__name__)


def _flow_edge_excerpt(
    db: Session,
    project_id: int,
    source_node: dict,
    edge: dict,
    char_budget: int,
) -> dict | None:
    focus_line = edge.get("start_line")
    if not isinstance(focus_line, int) or focus_line < 1:
        return None
    query = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id == source_node.get("source_id"),
        DocumentChunk.file_path == source_node.get("file_path"),
        DocumentChunk.start_line <= focus_line,
        DocumentChunk.end_line >= focus_line,
    )
    chunk = query.order_by(DocumentChunk.start_line, DocumentChunk.id).first()
    if chunk is None:
        return None
    lines = chunk.content.splitlines(keepends=True)
    if not lines:
        return None
    focus_index = max(0, min(len(lines) - 1, focus_line - chunk.start_line))
    first_index = max(0, focus_index - 5)
    last_index = min(len(lines), focus_index + 9)
    prefix_chars = sum(len(value) for value in lines[:first_index])
    excerpt = "".join(lines[first_index:last_index])
    content = excerpt[:char_budget]
    delivered_start = chunk.start_line + first_index
    delivered_lines = content.count("\n") + int(bool(content) and not content.endswith("\n"))
    delivered_end = min(chunk.end_line, delivered_start + max(0, delivered_lines - 1))
    truncated = len(content) < len(excerpt)
    return {
        "chunk_id": chunk.id,
        "focus_line": focus_line,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "delivered_start_line": delivered_start,
        "delivered_end_line": delivered_end,
        "content": content,
        "truncated": truncated,
        "follow_up_action": {
            "tool": "get_code_entity",
            "arguments": {
                "project_id": project_id,
                "entity_id": edge.get("source"),
                "chunk_id": chunk.id,
                "char_offset": prefix_chars + len(content) if truncated else 0,
                "max_chars": 5000,
            },
            "reason": "Read the original indexed chunk around this call site.",
        },
    }


def _flow_summary(flow: dict, direction: str, limit: int = 12) -> list[dict]:
    nodes = {node.get("id"): node for node in flow.get("nodes", [])}
    items = []
    for edge in flow.get("edges", [])[:limit]:
        other = nodes.get(edge.get("target") if direction == "outgoing" else edge.get("source"))
        item = {
            "type": edge.get("type"),
            ("to" if direction == "outgoing" else "from"): (other or {}).get("qualified_name")
            or edge.get("target_name"),
            "line": edge.get("start_line"),
            "resolution": edge.get("resolution"),
        }
        if other and other.get("file_path"):
            item["location"] = f"{other['file_path']}:{other.get('start_line')}"
        items.append(item)
    return items


def _fact_line(buckets: dict[str, list[str]]) -> str:
    parts = []
    for label in ("calls", "performs", "cics", "datasets", "io", "computes", "sets", "msgs"):
        literal = label in {"sets", "msgs", "computes"}
        names = [
            name if literal else name.split("(", 1)[0][-48:] for name in (buckets.get(label) or [])
        ]
        if names:
            parts.append(f"{label} {', '.join(names[: 3 if literal else 5])}")
    return "; ".join(parts)[:320]


_STRING_LITERAL = re.compile(r"\"([^\"\n]{8,80})\"|'([^'\n]{8,80})'")
_NOISE_VARIABLE = re.compile(
    r"RESULT|IO-STATUS|ABCODE|TIMING|TWO-BYTES|^DB2-REST|-BINARY$|-IDX$|-SUB$", re.I
)
_COBOL_ARITHMETIC = re.compile(
    r"\b(?:COMPUTE\s+([A-Z][A-Z0-9-]*)|(?:ADD|SUBTRACT)\s+[A-Z0-9][A-Z0-9-]*\s+(?:TO|FROM)\s+([A-Z][A-Z0-9-]*))",
    re.I,
)
_COBOL_SET_CODE = re.compile(
    r"\bMOVE\s+(?:'([A-Za-z0-9]{1,8})'|\"([A-Za-z0-9]{1,8})\"|(\d{1,4}))\s+TO\s+([A-Z0-9][A-Z0-9-]*)",
    re.I,
)


def _literal_facts(
    db: Session, entity: CodeEntity, children: list[CodeEntity]
) -> dict[int, dict[str, list[str]]]:
    """Message texts and assigned status codes inside each child, read from the indexed source lines."""
    if not children:
        return {}
    chunks = (
        db.query(DocumentChunk)
        .filter(
            DocumentChunk.project_id == entity.project_id,
            DocumentChunk.source_id == entity.source_id,
            DocumentChunk.file_path == entity.file_path,
            DocumentChunk.start_line <= entity.end_line,
            DocumentChunk.end_line >= entity.start_line,
        )
        .order_by(DocumentChunk.start_line)
        .limit(120)
        .all()
    )
    lines: dict[int, str] = {}
    for chunk in chunks:
        for offset, text in enumerate(chunk.content.splitlines()):
            lines.setdefault(chunk.start_line + offset, text)
    result: dict[int, dict[str, list[str]]] = {}
    for child in children:
        found: dict[str, list[str]] = {}
        for number in range(
            child.start_line or 0, min(child.end_line or 0, (child.start_line or 0) + 400) + 1
        ):
            text = lines.get(number)
            if (
                not text
                or text.lstrip().startswith(("*", "//", "/*"))
                or (len(text) > 6 and text[6] == "*")
            ):
                continue
            for match in _COBOL_ARITHMETIC.finditer(text):
                target = (match.group(1) or match.group(2)).upper()
                if not _NOISE_VARIABLE.search(target) and target not in found.setdefault(
                    "computes", []
                ):
                    found["computes"].append(target)
            for match in _COBOL_SET_CODE.finditer(text):
                if _NOISE_VARIABLE.search(match.group(4)):
                    continue
                code = match.group(1) or match.group(2) or match.group(3)
                item = f"{match.group(4)}={code}"
                if item not in found.setdefault("sets", []):
                    found["sets"].append(item)
            for match in _STRING_LITERAL.finditer(text):
                literal = (
                    (match.group(1) or match.group(2)).strip().replace("(", "[").replace(")", "]")
                )
                if (
                    re.search(r"[A-Za-z]{3}", literal)
                    and " " in literal
                    and literal not in found.setdefault("msgs", [])
                ):
                    found["msgs"].append(f'"{literal[:44]}"')
        if found:
            result[child.id] = found
    return result


def _outline(db: Session, entity: CodeEntity) -> list[dict]:
    """Children of a large entity with one-line facts per child (calls, performs, CICS commands, datasets)."""
    same_file = [
        CodeEntity.project_id == entity.project_id,
        CodeEntity.source_id == entity.source_id,
        CodeEntity.file_path == entity.file_path,
    ]
    children = (
        db.query(CodeEntity)
        .filter(
            *same_file,
            CodeEntity.id != entity.id,
            CodeEntity.type.in_(list(_STRUCTURAL)),
            CodeEntity.start_line >= entity.start_line,
            CodeEntity.end_line <= entity.end_line,
        )
        .order_by(CodeEntity.start_line, CodeEntity.id)
        .limit(80)
        .all()
    )
    edges = (
        db.query(CodeEdge)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.project_id == entity.project_id,
            *same_file,
            or_(
                CodeEdge.type.in_(
                    [
                        "CALL",
                        "CALLS",
                        "DISPATCHES_TO",
                        "PERFORM",
                        "GOTO",
                        "EXECUTES",
                        "USES_DATASET",
                    ]
                ),
                and_(
                    CodeEdge.type.in_(["READS", "WRITES"]),
                    func.json_extract_path_text(CodeEdge.meta_json, "io_target_kind").isnot(None),
                ),
            ),
            CodeEdge.src_start_line >= entity.start_line,
            CodeEdge.src_start_line <= entity.end_line,
        )
        .order_by(CodeEdge.src_start_line, CodeEdge.id)
        .limit(2500)
        .all()
    )
    labels = {
        "CALL": "calls",
        "CALLS": "calls",
        "DISPATCHES_TO": "calls",
        "PERFORM": "performs",
        "GOTO": "performs",
        "EXECUTES": "cics",
        "USES_DATASET": "datasets",
        "READS": "io",
        "WRITES": "io",
    }
    outline = []
    literals = _literal_facts(db, entity, children)
    for child in children:
        buckets: dict[str, list[str]] = dict(literals.get(child.id, {}))
        for edge in edges:
            if child.start_line <= (edge.src_start_line or 0) <= child.end_line and edge.dst_name:
                names = buckets.setdefault(labels[edge.type], [])
                label = edge.dst_name
                if edge.type in {"READS", "WRITES"}:
                    label = (
                        f"{(edge.meta_json or {}).get('operation') or edge.type} {edge.dst_name}"
                    )
                if label not in names:
                    names.append(label)
        item = {
            "symbol": child.qualified_name,
            "type": child.type,
            "lines": f"{child.start_line}-{child.end_line}",
        }
        facts = _fact_line(buckets)
        if facts:
            item["facts"] = facts
        outline.append(item)
    return outline


def _data_access_summary(db: Session, entity: CodeEntity, limit: int = 15) -> list[dict]:
    rows = (
        db.query(CodeEdge)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.project_id == entity.project_id,
            CodeEntity.source_id == entity.source_id,
            CodeEntity.file_path == entity.file_path,
            CodeEdge.type.in_(["READS", "WRITES", "USES_DATASET", "ASSIGNED_DATASET"]),
            CodeEdge.src_start_line >= entity.start_line,
            CodeEdge.src_start_line <= entity.end_line,
        )
        .order_by(CodeEdge.src_start_line, CodeEdge.id)
        .limit(400)
        .all()
    )
    groups: dict[tuple[str, str], dict] = {}
    for edge in rows:
        key = (edge.type, edge.dst_name or "")
        group = groups.setdefault(key, {"access": edge.type, "target": edge.dst_name, "lines": []})
        if len(group["lines"]) < 4:
            group["lines"].append(edge.src_start_line)
        meta = edge.meta_json or {}
        if meta.get("operation") and "operation" not in group:
            group["operation"] = meta["operation"]
        if meta.get("io_target_kind"):
            group["file_io"] = True
        if meta.get("derived_by") == "jcl_dd_assign" and "ddname" not in group:
            # O-147: Datei des Programms ↔ Dataset aus dem JCL-DD gleichen Namens (nur `possible`).
            group["ddname"] = meta.get("ddname")
            group["via_jcl"] = f"{meta.get('jcl_file_path')}:{meta.get('jcl_start_line')}"
            group["certainty"] = "possible"
    order = {"WRITES": 0, "USES_DATASET": 1, "ASSIGNED_DATASET": 1, "READS": 2}
    return sorted(
        groups.values(),
        key=lambda g: (0 if g.get("file_io") else 1, order.get(g["access"], 3), g["lines"][0] or 0),
    )[:limit]


def _call_flow_page(
    db: Session,
    user: User,
    project_id: int,
    entity_id: int,
    *,
    hops: int,
    direction: str,
    scope: str,
    page_size: int,
    cursor: str | None,
    include_source: bool,
    include_tests: bool = True,
) -> dict:
    """One ACL-filtered, cursor-paged call-flow page shared by all MCP entry points."""
    if direction not in {"outgoing", "incoming", "both"}:
        raise ValueError("invalid direction")
    if scope not in {"execution", "dependencies", "all"}:
        raise ValueError("invalid scope")
    requested_root = _entity(db, user, project_id, entity_id)
    offset = 0
    expansion = 0
    if cursor is not None:
        try:
            padding = "=" * (-len(cursor) % 4)
            cursor_data = json.loads(base64.urlsafe_b64decode(cursor + padding))
        except (ValueError, TypeError, binascii.Error):
            raise ValueError("invalid cursor")
        if not isinstance(cursor_data, dict):
            raise ValueError("invalid cursor")
        expected = {
            "project_id": project_id,
            "entity_id": entity_id,
            "hops": hops,
            "direction": direction,
            "scope": scope,
            "include_source": include_source,
        }
        # Ältere Cursor kennen include_tests nicht; sie gelten als include_tests=True.
        if cursor_data.get("include_tests", True) != include_tests:
            raise ValueError("cursor does not match this call-flow query")
        if any(cursor_data.get(key) != value for key, value in expected.items()):
            raise ValueError("cursor does not match this call-flow query")
        offset = cursor_data.get("offset")
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 10_000:
            raise ValueError("invalid cursor")
        expansion = cursor_data.get("expansion", 0)
        if (
            not isinstance(expansion, int)
            or isinstance(expansion, bool)
            or not 0 <= expansion <= 100
        ):
            raise ValueError("invalid cursor")

    node_limit = min(
        1_000, max(CALL_FLOW_MAX_NODES, offset + page_size * 2 + 1 + expansion * page_size * 2)
    )
    edge_limit = min(
        3_000, max(CALL_FLOW_MAX_EDGES, offset + page_size + 1 + expansion * page_size)
    )
    result = trace_call_flow(
        db,
        project_id=project_id,
        entity_id=entity_id,
        hops=hops,
        direction=direction,
        scope=scope,
        node_limit=node_limit,
        edge_limit=edge_limit,
        include_tests=include_tests,
    )
    raw_nodes = result.get("nodes", [])
    source_access = {}
    visible_nodes_by_id = {}
    for node in raw_nodes:
        source_id = node.get("source_id")
        if source_id not in source_access:
            source_access[source_id] = _source_visible(db, user, source_id)
        if source_access[source_id]:
            visible_nodes_by_id[node.get("id")] = node
    raw_edges = result.get("edges", [])
    visible_edges = [
        edge
        for edge in raw_edges
        if edge.get("source") in visible_nodes_by_id
        and (edge.get("target") is None or edge.get("target") in visible_nodes_by_id)
    ]
    page_edges = visible_edges[offset : offset + page_size]
    page_node_ids = []
    root_id = (result.get("root") or {}).get("id")
    for node_id in [
        root_id,
        *[
            node_id
            for edge in page_edges
            for node_id in (edge.get("source"), edge.get("target"))
            if node_id is not None
        ],
    ]:
        if node_id in visible_nodes_by_id and node_id not in page_node_ids:
            page_node_ids.append(node_id)
    nodes = [visible_nodes_by_id[node_id] for node_id in page_node_ids]
    allowed = set(page_node_ids)
    edges = []
    source_budget_per_edge = max(120, min(500, 4_000 // max(1, len(page_edges))))
    for edge in page_edges:
        if edge.get("source") not in allowed or (
            edge.get("target") is not None and edge.get("target") not in allowed
        ):
            continue
        meta = edge.get("meta") or {}
        response_edge = {
            **{
                key: edge.get(key)
                for key in (
                    "id",
                    "source",
                    "target",
                    "target_name",
                    "type",
                    "resolution",
                    "start_line",
                    "end_line",
                )
            },
            "resolution_evidence": {
                key: meta[key]
                for key in (
                    "target_qualified_name",
                    "target_file_path",
                    "resolution_reason",
                    "resolution_scope",
                    "receiver",
                    "receiver_resolution",
                    "receiver_symbol_qualified_name",
                    "receiver_type_qualified_name",
                    "receiver_method_qualified_name",
                    "argument_count",
                    "argument_types",
                    "argument_expressions",
                    "control_role",
                    "control_context",
                    "exception_types",
                    "dispatch_scope",
                )
                if key in meta
            },
        }
        if include_source:
            response_edge["source_excerpt"] = _flow_edge_excerpt(
                db,
                project_id,
                visible_nodes_by_id[edge["source"]],
                edge,
                source_budget_per_edge,
            )
        edges.append(response_edge)

    next_offset = offset + len(page_edges)
    page_has_more = next_offset < len(visible_edges)
    service_truncated = bool(result.get("truncated"))
    can_expand = node_limit < 1_000 or edge_limit < 3_000
    has_more = page_has_more or (service_truncated and can_expand)
    next_cursor = None
    if has_more:
        next_data = {
            "project_id": project_id,
            "entity_id": entity_id,
            "hops": hops,
            "direction": direction,
            "scope": scope,
            "include_source": include_source,
            "include_tests": include_tests,
            "offset": next_offset,
            "expansion": expansion + int(service_truncated and not page_has_more),
        }
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps(next_data, sort_keys=True, separators=(",", ":")).encode()
            )
            .decode()
            .rstrip("=")
        )
    truncated = has_more or len(visible_nodes_by_id) > len(nodes) or len(visible_edges) > len(edges)
    root = result.get("root")
    if not root or root.get("id") not in visible_nodes_by_id:
        root = {
            "id": requested_root.id,
            "name": requested_root.name,
            "qualified_name": requested_root.qualified_name,
            "type": requested_root.type,
            "file_path": requested_root.file_path,
            "source_id": requested_root.source_id,
            "start_line": requested_root.start_line,
            "end_line": requested_root.end_line,
        }
    response = {
        "project_id": project_id,
        "status": result.get("status"),
        "notice": result.get("notice"),
        "root": root,
        "entry_resolution": result.get("entry_resolution"),
        "hops_applied": hops,
        "scope": scope,
        "entry_candidates": result.get("entry_candidates", [])[:20],
        "nodes": nodes,
        "edges": edges,
        "truncated": truncated,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "limit_applied": page_size,
        "truncation": {
            "reason": "page_has_more"
            if page_has_more
            else (
                "service_limit"
                if service_truncated
                else ("source_visibility" if len(visible_edges) < len(raw_edges) else None)
            ),
            "nodes_returned": len(nodes),
            "nodes_available": len(visible_nodes_by_id),
            "nodes_omitted": max(0, len(visible_nodes_by_id) - len(nodes)),
            "edges_returned": len(edges),
            "edges_available": len(visible_edges),
            "edges_omitted": max(0, len(visible_edges) - len(edges)),
            "next_cursor": next_cursor,
            "source_visibility_filtered": len(visible_edges) < len(raw_edges)
            or len(visible_nodes_by_id) < len(raw_nodes),
            "service_truncated": service_truncated,
            "continuation_limit_reached": service_truncated and not can_expand,
        },
        "follow_up_actions": [
            {
                "tool": "get_call_flow",
                "arguments": {
                    "project_id": project_id,
                    "entity_id": entity_id,
                    "hops": hops,
                    "direction": direction,
                    "scope": scope,
                    "page_size": page_size,
                    "cursor": next_cursor,
                    "include_source": include_source,
                    "include_tests": include_tests,
                },
                "reason": "Continue the ordered visible call-flow page.",
            }
        ]
        if next_cursor
        else [],
    }
    return response
