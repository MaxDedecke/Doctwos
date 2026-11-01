"""Drop view: hop layers around one start entity, widening like a pyramid (O-387).

``direction="down"`` follows what the start point uses (callees, includes, data it touches), ``"up"`` follows who
uses it. Which edge types count as ``control``, ``data`` or ``includes`` comes from ``doctus_models.language_profile``, so the
view works for every language with a profile. Every node and edge carries ``cite`` (``path/file.ext:line``); edges the
index could not resolve are counted per layer (``unresolved``), never invented. Layers larger than ``collapse_above``
come back collapsed (count only) and are expanded on demand with ``expand``; nothing below a collapsed layer is
computed until then, so one call stays bounded. Edges leading back to a node already shown (same layer, an earlier
one, a cycle) are listed apart in ``back_edges``, so the edges of ``layers`` stay a clean descent. An empty first layer
says what else exists (``alternatives``). ``unresolved_external`` is the part of ``unresolved`` whose target an import
in the same file places outside the index; the rest is an open gap.
"""

from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from doctus_models.language_profile import (
    CONTROL_EDGES,
    DATA_EDGES,
    INCLUDE_EDGES,
    NAMING_EDGES,
    role_of,
)
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, User
from services.call_flow import TEST_PATH_PATTERN
from services.provenance import build_provenance
from services.source_access import source_visible

KIND_EDGES = {"control": CONTROL_EDGES, "data": DATA_EDGES, "includes": INCLUDE_EDGES}
MAX_LAYERS = 6
MAX_FRONTIER = 400  # nodes followed into the next layer; more are reported as ``truncated``
_CHUNK = 500


def _node(entity: CodeEntity, layer: int) -> dict:
    return {
        "id": entity.id,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "type": entity.type,
        "source_id": entity.source_id,
        "role": role_of(entity.type),
        "file_path": entity.file_path,
        "start_line": entity.start_line,
        "cite": f"{entity.file_path}:{entity.start_line}",
        "layer": layer,
    }


def _members(db: Session, project_id: int, root: CodeEntity) -> list[int]:
    """The start entity plus what it contains (a class's methods, a program's paragraphs): their edges are its edges."""
    if role_of(root.type) != "container":
        return [root.id]
    ids, frontier = [root.id], [root.id]
    for _ in range(3):
        rows = (
            db.query(CodeEntity.id)
            .filter(CodeEntity.project_id == project_id, CodeEntity.parent_id.in_(frontier))
            .all()
        )
        frontier = [row[0] for row in rows if row[0] not in ids]
        ids.extend(frontier)
        if not frontier:
            break
    return ids


def _edges(
    db: Session, project_id: int, ids: Iterable[int], types: set[str], down: bool
) -> list[CodeEdge]:
    ids = list(ids)
    column = CodeEdge.src_entity_id if down else CodeEdge.dst_entity_id
    rows: list[CodeEdge] = []
    for start in range(0, len(ids), _CHUNK):
        rows.extend(
            db.query(CodeEdge)
            .filter(
                CodeEdge.project_id == project_id,
                column.in_(ids[start : start + _CHUNK]),
                CodeEdge.type.in_(sorted(types)),
            )
            .order_by(CodeEdge.id)
            .all()
        )
    return rows


def _outside_index(
    db: Session, project_id: int, rows: list[CodeEdge], holders: dict[int, tuple[str, int | None]]
) -> int:
    """Offene Kanten, deren Ziel ein Import derselben Datei benennt, der selbst nicht im Index liegt."""
    open_rows = [row for row in rows if row.dst_entity_id is None]
    files = {holders[row.src_entity_id][0] for row in open_rows if row.src_entity_id in holders}
    if not files:
        return 0
    imported: dict[str, set[str]] = {}
    for file_path, name in (
        db.query(CodeEntity.file_path, CodeEdge.dst_name)
        .join(CodeEdge, CodeEdge.src_entity_id == CodeEntity.id)
        .filter(
            CodeEdge.project_id == project_id,
            CodeEdge.type.in_(sorted(NAMING_EDGES)),
            CodeEdge.resolution == "unresolved",
            CodeEntity.project_id == project_id,
            CodeEntity.file_path.in_(list(files)[:_CHUNK]),
        )
    ):
        imported.setdefault(file_path, set()).add((name or "").rsplit(".", 1)[-1])
    count = 0
    for row in open_rows:
        names = imported.get(holders.get(row.src_entity_id, ("",))[0])
        if names:
            receiver = (row.meta_json or {}).get("receiver")
            count += (receiver or (row.dst_name or "")).split(".", 1)[0] in names
    return count


def _alternatives(
    db: Session,
    user: User,
    project_id: int,
    members: list[int],
    kinds: list[str],
    down: bool,
    include_tests: bool,
) -> list[dict]:
    """Was es um einen Start ohne Ergebnis sonst gibt: je Richtung und Kantenart die Zahl der Nachbarn."""
    alternatives = []
    ids = members[: 4 * _CHUNK]
    for downward in (True, False):
        here = CodeEdge.src_entity_id if downward else CodeEdge.dst_entity_id
        there = CodeEdge.dst_entity_id if downward else CodeEdge.src_entity_id
        for kind, types in KIND_EDGES.items():
            if downward == down and kind in kinds:
                continue
            query = (
                db.query(CodeEntity.source_id, func.count(there.distinct()))
                .join(CodeEdge, there == CodeEntity.id)
                .filter(
                    CodeEdge.project_id == project_id,
                    here.in_(ids),
                    there.notin_(ids),
                    CodeEdge.type.in_(sorted(types)),
                )
            )
            if not include_tests:
                query = query.filter(CodeEntity.file_path.op("!~")(TEST_PATH_PATTERN))
            count = sum(
                number
                for source_id, number in query.group_by(CodeEntity.source_id)
                if source_visible(db, user, source_id)
            )
            if count:
                alternatives.append(
                    {"direction": "down" if downward else "up", "kind": kind, "count": count}
                )
    return alternatives


def _condition(meta: dict) -> str | None:
    for key in ("condition", "control_context"):
        if isinstance(meta.get(key), str):
            return meta[key]
    return None


def drop(
    db: Session,
    user: User,
    project_id: int,
    root: CodeEntity,
    *,
    direction: str = "down",
    layers: int = 3,
    kinds: Iterable[str] = ("control",),
    collapse_above: int = 40,
    expand: Iterable[int] = (),
    include_tests: bool = False,
    with_provenance: bool = False,
) -> dict:
    down = direction != "up"
    layers = max(1, min(int(layers), MAX_LAYERS))
    kinds = [kind for kind in dict.fromkeys(kinds) if kind in KIND_EDGES] or ["control"]
    types = set().union(*(KIND_EDGES[kind] for kind in kinds))
    expanded = {int(n) for n in expand}
    seen = {root.id}
    frontier = _members(db, project_id, root)
    seen.update(frontier)
    # Der Start steht für alles, was er enthält: Nur er ist ein Knoten, Kanten seiner Teile enden sonst im Leeren.
    members = set(frontier)

    def anchor(entity_id: int) -> int:
        return root.id if entity_id in members else entity_id

    def other(row: CodeEdge) -> int | None:
        return row.dst_entity_id if down else row.src_entity_id

    sources: dict[int, KnowledgeSource | None] = {}
    back: dict[tuple[int, int, str], dict] = {}

    def holders_of(rows: list[CodeEdge]) -> dict[int, tuple[str, int | None]]:
        if not rows:
            return {}
        return {
            e.id: (e.file_path, e.source_id)
            for e in db.query(CodeEntity.id, CodeEntity.file_path, CodeEntity.source_id).filter(
                CodeEntity.id.in_({r.src_entity_id for r in rows})
            )
        }

    def provenance_of(row: CodeEdge, file_path: str | None, source_id: int | None) -> dict:
        if source_id is not None and source_id not in sources:
            sources[source_id] = (
                db.query(KnowledgeSource)
                .filter(KnowledgeSource.id == source_id, KnowledgeSource.project_id == project_id)
                .first()
            )
        source = sources.get(source_id) if source_id is not None else None
        return build_provenance(
            source,
            kind="code_fact" if source else "unknown",
            verification_status="indexed_unreviewed" if source else "unavailable",
            locator={
                "file_path": file_path,
                "start_line": row.src_start_line,
                "end_line": row.src_end_line,
            },
        )

    def edge_of(row: CodeEdge, src: int, dst: int, holders: dict) -> dict:
        file_path, source_id = holders.get(row.src_entity_id, (None, None))
        meta = row.meta_json or {}
        edge = {
            "from": src,
            "to": dst,
            "type": row.type,
            "resolution": row.resolution,
            "cite": f"{file_path}:{row.src_start_line or 0}",
        }
        if isinstance(meta.get("resolution_reason"), str):
            edge["reason"] = meta["resolution_reason"]
        if _condition(meta):
            edge["condition"] = _condition(meta)
        if with_provenance:
            edge["provenance"] = provenance_of(row, file_path, source_id)
        return edge

    def note_back(row: CodeEdge, holders: dict) -> None:
        inner = row.src_entity_id in members and row.dst_entity_id in members
        if inner and not row.src_entity_id == row.dst_entity_id == root.id:
            return
        src, dst = anchor(row.src_entity_id), anchor(row.dst_entity_id)
        if len(back) < 4 * collapse_above:
            back.setdefault((src, dst, row.type), edge_of(row, src, dst, holders))

    result_layers: list[dict] = [
        {"layer": 0, "count": 1, "nodes": [_node(root, 0)], "edges": [], "unresolved": 0}
    ]
    stopped = None
    visibility: dict[int | None, bool] = {}

    for layer in range(1, layers + 1):
        rows = _edges(db, project_id, frontier, types, down)
        unresolved = sum(1 for row in rows if row.dst_entity_id is None) if down else 0
        targets = (
            {
                e.id: e
                for e in db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id,
                    CodeEntity.id.in_({other(r) for r in rows if other(r)} - seen),
                )
            }
            if rows
            else {}
        )
        holders = holders_of(rows)
        nodes: dict[int, dict] = {}
        edges: list[dict] = []
        for row in rows:
            if other(row) in seen:
                note_back(row, holders)
                continue
            entity = targets.get(other(row))
            if entity is None:
                continue
            if entity.source_id not in visibility:
                visibility[entity.source_id] = source_visible(db, user, entity.source_id)
            if not visibility[entity.source_id] or (
                not include_tests and re.search(TEST_PATH_PATTERN, entity.file_path or "")
            ):
                continue
            nodes.setdefault(entity.id, _node(entity, layer))
            if len(edges) < 4 * collapse_above:
                src, dst = (
                    (anchor(row.src_entity_id), entity.id)
                    if down
                    else (entity.id, anchor(row.dst_entity_id))
                )
                edges.append(edge_of(row, src, dst, holders))
        entry = {"layer": layer, "count": len(nodes), "unresolved": unresolved}
        external = _outside_index(db, project_id, rows, holders) if unresolved else 0
        if external:
            entry["unresolved_external"] = external
        collapsed = len(nodes) > collapse_above and layer not in expanded
        if collapsed:
            entry.update(collapsed=True, nodes=[], edges=[])
        else:
            shown = list(nodes.values())
            entry.update(
                nodes=shown, edges=[e for e in edges if e["to" if down else "from"] in nodes]
            )
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

    if stopped is None:
        # Tiefe erreicht: Die letzte Ebene wurde nicht mehr verfolgt, ihre Wege zurück fehlen sonst.
        rows = [r for r in _edges(db, project_id, frontier, types, down) if other(r) in seen]
        holders = holders_of(rows)
        for row in rows:
            note_back(row, holders)

    empty = len(result_layers) > 1 and result_layers[1]["count"] == 0
    return {
        "alternatives": (
            _alternatives(db, user, project_id, sorted(members), kinds, down, include_tests)
            if empty
            else []
        ),
        "root": _node(root, 0),
        "direction": "down" if down else "up",
        "kinds": kinds,
        "layers": result_layers,
        "back_edges": list(back.values()),
        "stopped": stopped,
        "collapse_above": collapse_above,
    }
