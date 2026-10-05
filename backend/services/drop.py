"""Drop view: hop layers around one start entity, widening like a pyramid (O-387).

``direction="down"`` follows what the start point uses (callees, includes, data it touches), ``"up"`` follows who
uses it. Which edge types count as ``control``, ``data`` or ``includes`` comes from ``core.language_profile``, so the
view works for every language with a profile. Every node and edge carries ``cite`` (``path/file.ext:line``); edges the
index could not resolve are counted per layer (``unresolved``), never invented. Layers larger than ``collapse_above``
come back collapsed (count only) and are expanded on demand with ``expand``; nothing below a collapsed layer is
computed until then, so one call stays bounded.
"""

from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy.orm import Session

from core.language_profile import CONTROL_EDGES, DATA_EDGES, INCLUDE_EDGES, role_of
from models.database import CodeEdge, CodeEntity, User
from services.call_flow import TEST_PATH_PATTERN
from services.source_access import source_visible

KIND_EDGES = {"control": CONTROL_EDGES, "data": DATA_EDGES, "includes": INCLUDE_EDGES}
MAX_LAYERS = 6
MAX_FRONTIER = 400  # nodes followed into the next layer; more are reported as ``truncated``
_CHUNK = 500


def _node(entity: CodeEntity, layer: int) -> dict:
    return {
        "id": entity.id, "name": entity.name, "qualified_name": entity.qualified_name, "type": entity.type, "source_id": entity.source_id,
        "role": role_of(entity.type), "file_path": entity.file_path, "start_line": entity.start_line,
        "cite": f"{entity.file_path}:{entity.start_line}", "layer": layer,
    }


def _members(db: Session, project_id: int, root: CodeEntity) -> list[int]:
    """The start entity plus what it contains (a class's methods, a program's paragraphs): their edges are its edges."""
    if role_of(root.type) != "container":
        return [root.id]
    ids, frontier = [root.id], [root.id]
    for _ in range(3):
        rows = db.query(CodeEntity.id).filter(CodeEntity.project_id == project_id, CodeEntity.parent_id.in_(frontier)).all()
        frontier = [row[0] for row in rows if row[0] not in ids]
        ids.extend(frontier)
        if not frontier:
            break
    return ids


def _edges(db: Session, project_id: int, ids: Iterable[int], types: set[str], down: bool) -> list[CodeEdge]:
    ids = list(ids)
    column = CodeEdge.src_entity_id if down else CodeEdge.dst_entity_id
    rows: list[CodeEdge] = []
    for start in range(0, len(ids), _CHUNK):
        rows.extend(
            db.query(CodeEdge).filter(
                CodeEdge.project_id == project_id, column.in_(ids[start:start + _CHUNK]), CodeEdge.type.in_(sorted(types)),
            ).order_by(CodeEdge.id).all()
        )
    return rows


def drop(
    db: Session, user: User, project_id: int, root: CodeEntity, *, direction: str = "down", layers: int = 3,
    kinds: Iterable[str] = ("control",), collapse_above: int = 40, expand: Iterable[int] = (), include_tests: bool = False,
) -> dict:
    down = direction != "up"
    layers = max(1, min(int(layers), MAX_LAYERS))
    kinds = [kind for kind in dict.fromkeys(kinds) if kind in KIND_EDGES] or ["control"]
    types = set().union(*(KIND_EDGES[kind] for kind in kinds))
    expanded = {int(n) for n in expand}
    seen = {root.id}
    frontier = _members(db, project_id, root)
    seen.update(frontier)
    result_layers: list[dict] = [{"layer": 0, "count": 1, "nodes": [_node(root, 0)], "edges": [], "unresolved": 0}]
    stopped = None
    visibility: dict[int | None, bool] = {}

    for layer in range(1, layers + 1):
        rows = _edges(db, project_id, frontier, types, down)
        unresolved = sum(1 for row in rows if row.dst_entity_id is None) if down else 0
        other = (lambda row: row.dst_entity_id) if down else (lambda row: row.src_entity_id)
        targets = {
            e.id: e for e in db.query(CodeEntity).filter(
                CodeEntity.project_id == project_id, CodeEntity.id.in_({other(r) for r in rows if other(r)} - seen)
            )
        } if rows else {}
        holders = {
            e.id: e.file_path for e in db.query(CodeEntity.id, CodeEntity.file_path).filter(
                CodeEntity.id.in_({r.src_entity_id for r in rows})
            )
        } if rows else {}
        nodes: dict[int, dict] = {}
        edges: list[dict] = []
        for row in rows:
            entity = targets.get(other(row))
            if entity is None:
                continue
            if entity.source_id not in visibility:
                visibility[entity.source_id] = source_visible(db, user, entity.source_id)
            if not visibility[entity.source_id] or (not include_tests and re.search(TEST_PATH_PATTERN, entity.file_path or "")):
                continue
            nodes.setdefault(entity.id, _node(entity, layer))
            if len(edges) < 4 * collapse_above:
                src, dst = (row.src_entity_id, entity.id) if down else (entity.id, row.dst_entity_id)
                site = f"{holders.get(row.src_entity_id)}:{row.src_start_line or 0}"
                edges.append({"from": src, "to": dst, "type": row.type, "resolution": row.resolution, "cite": site})
        entry = {"layer": layer, "count": len(nodes), "unresolved": unresolved}
        collapsed = len(nodes) > collapse_above and layer not in expanded
        if collapsed:
            entry.update(collapsed=True, nodes=[], edges=[])
        else:
            shown = list(nodes.values())
            entry.update(nodes=shown, edges=[e for e in edges if e["to" if down else "from"] in nodes])
        result_layers.append(entry)
        if not nodes:
            stopped = "end"
            break
        if collapsed:
            stopped = "collapsed"
            break
        seen.update(nodes)
        frontier = list(nodes)[:MAX_FRONTIER]
        if len(nodes) > MAX_FRONTIER:
            entry["truncated"] = True

    return {
        "root": _node(root, 0), "direction": "down" if down else "up", "kinds": kinds, "layers": result_layers,
        "stopped": stopped, "collapse_above": collapse_above,
    }
