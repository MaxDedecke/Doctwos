"""Language-neutral evidence blocks for the MCP evidence pack (``answer_context``).

Each block answers one kind of question from the index in one go, so an agent does not have to assemble it from
several tool calls. They read roles from ``core.language_profile`` and never name a language's edge or entity types.
Every item carries ``cite`` (``path/file.ext:line``); what the index cannot prove is reported as a gap
(``unresolved``, ``external``), never filled in.
"""

from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.language_profile import CONTROL_EDGES, INCLUDE_EDGES, ROUTINE_TYPES, role_of
from models.database import CodeEdge, CodeEntity, User
from services.source_access import site_excerpt, source_visible

# Question wording that asks for one block; a block is only built when the question asks for it.
INCLUDES_INTENT = re.compile(
    r"copy|copybook|include|einbind|import|abh[aä]ngig|depend|extends|implements|erb[t]|implementier|"
    r"binden .{0,40}ein|welche (typen|klassen) .{0,30}nutz", re.I)
FLOW_INTENT = re.compile(
    r"kontrollfluss|control flow|ablauf|l[aä]uft|ausgef[uü]hrt|folgeschritt|reihenfolge|aufrufkette|call chain|"
    r"perform|schritte|was passiert|ruft .{0,60}auf|aufgerufen|call hierarch", re.I)


def _short(name: str | None) -> str:
    return (name or "").split("(", 1)[0].rsplit(".", 1)[-1].rsplit("#", 1)[-1]


# ---------------------------------------------------------------------------------------------------------- includes
def includes(db: Session, user: User, project_id: int, entity: CodeEntity, limit: int = 60) -> dict | None:
    """Units a file includes, imports or extends, grouped the way a question asks: resolved, external, unresolved.

    ``resolved`` exist in the repository (with their file), ``external`` are system or library units the index
    recognises (MQ copybooks, JDK types), ``unresolved`` are genuine gaps."""
    if not source_visible(db, user, entity.source_id):
        return None
    rows = db.query(CodeEdge).join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id).filter(
        CodeEdge.project_id == project_id, CodeEdge.type.in_(sorted(INCLUDE_EDGES)),
        CodeEntity.project_id == project_id, CodeEntity.source_id == entity.source_id,
        CodeEntity.file_path == entity.file_path,
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(limit + 1).all()
    targets = {
        target.id: target for target in db.query(CodeEntity).filter(
            CodeEntity.project_id == project_id, CodeEntity.id.in_([row.dst_entity_id for row in rows if row.dst_entity_id])
        )
    } if rows else {}
    groups: dict[str, list[dict]] = {"resolved": [], "external": [], "unresolved": []}
    seen: set[tuple[str, int, str]] = set()
    for row in rows[:limit]:
        line = row.src_start_line or 0
        if (row.dst_name, line, row.type) in seen:
            continue
        seen.add((row.dst_name, line, row.type))
        item = {"name": row.dst_name, "line": line, "cite": f"{entity.file_path}:{line}", "kind": row.type.lower()}
        external = (row.meta_json or {}).get("external")
        target = targets.get(row.dst_entity_id) if row.dst_entity_id else None
        if row.resolution == "resolved" and target is not None:
            groups["resolved"].append({**item, "file": target.file_path})
        elif isinstance(external, dict) and external:
            groups["external"].append({**item, "category": external.get("category"), "system_kind": external.get("kind")})
        else:
            groups["unresolved"].append(item)
    if not any(groups.values()):
        return None
    return {**groups, "counts": {name: len(items) for name, items in groups.items()}, "truncated": len(rows) > limit,
            "notice": "Includes, imports and inheritance of this file from the index; `external` names are system or "
                      "library units the index recognises, `unresolved` is a genuine gap."}


# ----------------------------------------------------------------------------------------------------- control flow
def _step(row: CodeEdge, source: CodeEntity, target: CodeEntity | None) -> dict:
    line = row.src_start_line or 0
    external = (row.meta_json or {}).get("external")
    if row.resolution == "resolved" and target is not None:
        status = "resolved"
    elif isinstance(external, dict) and external:
        status = "external"
    else:
        status = "unresolved"
    step = {"edge": row.type, "to": _short(target.qualified_name if target is not None else row.dst_name) or row.dst_name,
            "line": line, "status": status, "cite": f"{source.file_path}:{line}"}
    if target is not None and target.file_path != source.file_path:
        step["file"] = target.file_path
    if status == "external":
        step["category"] = external.get("category")
    return step


def control_flow(
    db: Session, user: User, project_id: int, entity: CodeEntity, budget_chars: int = 2600
) -> dict | None:
    """Order of execution from the index: the routines of a unit with the control transfers they make, in source order.

    For a routine: its outgoing transfers and, for every resolved target, that target's own transfers (two hops).
    For a container: every routine that transfers control, in source order. Library calls the index cannot resolve
    (e.g. logging) are counted, not listed, when a routine has repository targets."""
    role = role_of(entity.type)
    if role not in {"routine", "container"} or not source_visible(db, user, entity.source_id):
        return None
    if role == "container":
        routines = db.query(CodeEntity).filter(
            CodeEntity.project_id == project_id, CodeEntity.source_id == entity.source_id,
            CodeEntity.file_path == entity.file_path, CodeEntity.type.in_(sorted(ROUTINE_TYPES)),
        ).order_by(CodeEntity.start_line, CodeEntity.id).all()
    else:
        routines = [entity]
    if not routines:
        return None
    ids = [routine.id for routine in routines]
    rows = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id, CodeEdge.type.in_(sorted(CONTROL_EDGES)), CodeEdge.src_entity_id.in_(ids),
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(600).all()
    by_source: dict[int, list[CodeEdge]] = {}
    for row in rows:
        by_source.setdefault(row.src_entity_id, []).append(row)
    target_ids = {row.dst_entity_id for row in rows if row.dst_entity_id}
    second_rows: dict[int, list[CodeEdge]] = {}
    if role == "routine" and target_ids:
        for row in db.query(CodeEdge).filter(
            CodeEdge.project_id == project_id, CodeEdge.type.in_(sorted(CONTROL_EDGES)),
            CodeEdge.src_entity_id.in_(sorted(target_ids)),
        ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(600):
            second_rows.setdefault(row.src_entity_id, []).append(row)
        target_ids |= {row.dst_entity_id for rows_ in second_rows.values() for row in rows_ if row.dst_entity_id}
    targets = {
        target.id: target for target in db.query(CodeEntity).filter(
            CodeEntity.project_id == project_id, CodeEntity.id.in_(sorted(target_ids))
        )
    } if target_ids else {}

    def steps_of(routine: CodeEntity, edge_rows: list[CodeEdge], cap: int) -> tuple[list[tuple[dict, CodeEdge]], int]:
        pairs = [(_step(row, routine, targets.get(row.dst_entity_id)), row) for row in edge_rows]
        repository = [pair for pair in pairs if pair[0]["status"] == "resolved"]
        shown = (repository or pairs)[:cap]
        return shown, len(pairs) - len(shown)

    out: list[dict] = []
    leaves: list[str] = []
    spent = 0
    for routine in routines:
        edge_rows = by_source.get(routine.id, [])
        if not edge_rows:
            if role == "container":
                leaves.append(_short(routine.qualified_name))
            continue
        shown, omitted = steps_of(routine, edge_rows, 10 if role == "routine" else 8)
        calls = []
        for step, row in shown:
            target = targets.get(row.dst_entity_id) if row.dst_entity_id else None
            if role == "routine" and target is not None and second_rows.get(target.id):
                then, more = steps_of(target, second_rows[target.id], 6)
                step["then"] = [item for item, _row in then]
                if more:
                    step["then_more"] = more
            calls.append(step)
        item: dict = {"routine": routine.qualified_name, "line": routine.start_line, "calls": calls}
        if omitted:
            item["more_calls"] = omitted
        size = len(str(item))
        if spent + size > budget_chars and out:
            out.append({"truncated_routines": len(routines) - len(out) - len(leaves)})
            break
        spent += size
        out.append(item)
    if not out:
        return None
    result: dict = {"flow": out, "order": "source order (line)"}
    if leaves:
        result["routines_without_transfers"] = leaves[:25]
    result["notice"] = ("Control transfers from the index in source order, statuses resolved/external/unresolved; "
                        "no path-sensitive analysis, so a transfer may be conditional.")
    return result


# ----------------------------------------------------------------------------------------------------- data origin
def data_origin(db: Session, user: User, project_id: int, field: CodeEntity, depth: int = 4, max_steps: int = 10) -> list[dict]:
    """Where a data entity gets its value: indexed writes, followed backwards through the operands of each write.

    Reads the statement structure from READS/WRITES edge metadata (``operation``, ``operand_role``) as the parser
    contract requires; a write edge carries the line of its own operand, so the operands read by the same statement
    are the READS edges of the same routine and operation next to it (``MOVE``: the same line; other operations: up to
    two lines below; ``STRING``/``UNSTRING``: the source operand above the target)."""
    steps: list[dict] = []
    seen = {field.id}
    frontier = [field]
    for _level in range(depth):
        following: list[CodeEntity] = []
        for current in frontier:
            writes = db.query(CodeEdge).filter(
                CodeEdge.project_id == project_id, CodeEdge.type == "WRITES", CodeEdge.dst_entity_id == current.id,
            ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(4).all()
            for write in writes:
                if len(steps) >= max_steps:
                    return steps
                routine = db.query(CodeEntity).filter(
                    CodeEntity.id == write.src_entity_id, CodeEntity.project_id == project_id).first()
                if routine is None or not source_visible(db, user, routine.source_id):
                    continue
                operation = (write.meta_json or {}).get("operation")
                line = write.src_start_line or 0
                reads = db.query(CodeEdge).filter(
                    CodeEdge.project_id == project_id, CodeEdge.type == "READS",
                    CodeEdge.src_entity_id == write.src_entity_id,
                    CodeEdge.src_start_line.between(line - 25, line + 3),
                ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(40).all()
                operands: dict[int, str] = {}
                for read in reads:
                    meta = read.meta_json or {}
                    if meta.get("operation") != operation or read.dst_entity_id in (None, current.id):
                        continue
                    read_line = read.src_start_line or 0
                    if operation in {"STRING", "UNSTRING"}:
                        near = meta.get("operand_role") == "source" and read_line <= line
                    elif operation == "MOVE":
                        near = read_line == line  # a MOVE is one line; neighbours are other statements
                    else:
                        near = meta.get("operand_role") == "source" and 0 <= read_line - line <= 2
                    if near:
                        operands[read.dst_entity_id] = read.dst_name
                site = site_excerpt(db, user, routine, line, 0) if line else None
                steps.append({
                    "field": current.name, "written_by": routine.name, "file": routine.file_path, "line": line,
                    "cite": f"{routine.file_path}:{line}",
                    "operation": operation, "statement": ((site or {}).get("text") or "")[:140],
                    "reads": sorted(operands.values()),
                })
                for entity_id in operands:
                    if entity_id not in seen:
                        seen.add(entity_id)
                        found = db.query(CodeEntity).filter(
                            CodeEntity.id == entity_id, CodeEntity.project_id == project_id).first()
                        if found is not None and role_of(found.type) == "data":
                            following.append(found)
        if not following:
            break
        frontier = following
    return steps
