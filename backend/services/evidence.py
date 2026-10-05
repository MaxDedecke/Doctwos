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
from services.call_flow import TEST_PATH_PATTERN
from services.source_access import site_excerpt, source_visible

# Question wording that asks for one block; a block is only built when the question asks for it.
INCLUDES_INTENT = re.compile(
    r"copy|copybook|include|einbind|import|abh[aä]ngig|depend|extends|implements|erb[t]|implementier|"
    r"binden .{0,40}ein|welche (typen|klassen) .{0,30}nutz", re.I)
# The question asks about a value or a field rather than about behaviour: a data entity wins over a same-named method.
DATA_INTENT = re.compile(
    r"\bfeld(es|er|s)?\b|\bfield\b|variable|attribut|herkunft|origin|befüll|"
    r"\bwert\b.{0,40}(stammt|kommt|gesetzt)|woher .{0,40}(wert|betrag|inhalt)", re.I)
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
            groups["resolved"].append({**item, "defined_in": target.file_path})
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
        step["defined_in"] = target.file_path
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
# Parser contract (docs/ENTSCHEIDUNGEN.md E-15): statement-level data flow reaches the server in one of two shapes.
#   (a) READS/WRITES edge metadata `operation` + `operand_role` (COBOL): the operands of one statement are found next
#       to the write edge;
#   (b) a table `meta["data_flow"]` on the routine (Java): one row per statement with target and sources.
# A routine that carries the table is read through (b), every other through (a); no language is named here.
def _entity_by_qname(db: Session, project_id: int, qualified_name: str | None) -> CodeEntity | None:
    if not qualified_name:
        return None
    return db.query(CodeEntity).filter(
        CodeEntity.project_id == project_id, CodeEntity.qualified_name == qualified_name).first()


def _origin_edge_statements(
    db: Session, user: User, project_id: int, current: CodeEntity, limit: int = 4
) -> list[tuple[dict, list[CodeEntity]]]:
    """(a) Steps from WRITES edges whose statement structure sits in the edge metadata."""
    out: list[tuple[dict, list[CodeEntity]]] = []
    writes = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id, CodeEdge.type == "WRITES", CodeEdge.dst_entity_id == current.id,
    ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(limit).all()
    for write in writes:
        routine = db.query(CodeEntity).filter(CodeEntity.id == write.src_entity_id, CodeEntity.project_id == project_id).first()
        if routine is None or not source_visible(db, user, routine.source_id) or (routine.meta_json or {}).get("data_flow"):
            continue  # a routine with a table is read through (b)
        operation = (write.meta_json or {}).get("operation")
        line = write.src_start_line or 0
        reads = db.query(CodeEdge).filter(
            CodeEdge.project_id == project_id, CodeEdge.type == "READS", CodeEdge.src_entity_id == write.src_entity_id,
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
        step = {"field": current.name, "written_by": routine.name, "file": routine.file_path, "line": line,
                "cite": f"{routine.file_path}:{line}", "operation": operation,
                "statement": ((site or {}).get("text") or "")[:140], "reads": sorted(operands.values())}
        followed = [e for e in (db.query(CodeEntity).filter(CodeEntity.project_id == project_id, CodeEntity.id.in_(list(operands))).all()
                                if operands else []) if role_of(e.type) == "data"]
        out.append((step, followed))
    return out


def _table_step(current: CodeEntity, routine: CodeEntity, row: dict) -> dict:
    sources = [item for item in row.get("sources", []) if item.get("kind") != "literal"] or row.get("sources", [])
    reads = []
    for item in sources:
        label = item["name"] if item["kind"] not in {"call", "new"} else f"{item['name']}(…)"
        if item.get("via", "").startswith(("call:", "new:")):
            label += f" (Argument von {item['via'].split(':', 1)[1]})"
        reads.append(label)
    return {"field": current.name, "written_by": routine.name, "file": routine.file_path, "line": row["line"],
            "cite": f"{routine.file_path}:{row['line']}", "operation": row["operation"],
            "statement": row.get("text", "")[:140], "reads": reads}


def _follow_table_sources(db: Session, project_id: int, row: dict, current: CodeEntity) -> list[CodeEntity]:
    found = []
    for item in row.get("sources", []):
        entity = _entity_by_qname(db, project_id, item.get("qualified_name"))
        if entity is not None and entity.id != current.id and role_of(entity.type) == "data":
            found.append(entity)
    return found


def _origin_table_statements(
    db: Session, user: User, project_id: int, current: CodeEntity
) -> list[tuple[dict, list[CodeEntity]]]:
    """(b) Steps from `data_flow` tables: where the entity is a statement target, and for a parameter its call sites."""
    out: list[tuple[dict, list[CodeEntity]]] = []
    holders: dict[int, CodeEntity] = {}
    parent = db.query(CodeEntity).filter(
        CodeEntity.project_id == project_id, CodeEntity.id == current.parent_id).first() if current.parent_id else None
    if parent is not None and role_of(current.type) == "data" and current.type != "parameter":
        holders[parent.id] = parent  # a local variable's routine or a field's class (initializers)
    if current.type not in {"local_variable", "parameter"}:
        for write in db.query(CodeEdge).filter(
            CodeEdge.project_id == project_id, CodeEdge.type == "WRITES", CodeEdge.dst_entity_id == current.id
        ).order_by(CodeEdge.src_start_line, CodeEdge.id).limit(12):
            routine = db.query(CodeEntity).filter(CodeEntity.id == write.src_entity_id, CodeEntity.project_id == project_id).first()
            if routine is not None:
                holders[routine.id] = routine
    if current.type == "parameter" and parent is not None:
        holders[parent.id] = parent  # assignments to the parameter inside its own routine
    for holder in holders.values():
        if not source_visible(db, user, holder.source_id):
            continue
        for row in (holder.meta_json or {}).get("data_flow") or []:
            target = row.get("target") or {}
            if target.get("qualified_name") == current.qualified_name:
                out.append((_table_step(current, holder, row), _follow_table_sources(db, project_id, row, current)))
                if len(out) >= 4:
                    return out
    if current.type == "parameter" and parent is not None and "@param:" in current.qualified_name:
        siblings = db.query(CodeEntity).filter(
            CodeEntity.project_id == project_id, CodeEntity.parent_id == parent.id,
            CodeEntity.type == "parameter", CodeEntity.qualified_name.like("%@param:%"),
        ).all()
        siblings.sort(key=lambda e: (e.start_line or 0, int((e.meta_json or {}).get("declaration_column", 0))))
        position = next((i for i, e in enumerate(siblings) if e.id == current.id), None)
        if position is not None:
            call_edges = db.query(CodeEdge).filter(
                CodeEdge.project_id == project_id, CodeEdge.type == "CALLS", CodeEdge.dst_entity_id == parent.id,
            ).order_by(CodeEdge.id).limit(30).all()
            callers_by_id = {
                caller.id: caller for caller in db.query(CodeEntity).filter(
                    CodeEntity.project_id == project_id, CodeEntity.id.in_([edge.src_entity_id for edge in call_edges]))
            } if call_edges else {}
            # Production callers first: a call from test code explains how the code is used, not where the value comes from.
            call_edges.sort(key=lambda edge: (bool(re.search(TEST_PATH_PATTERN, getattr(callers_by_id.get(edge.src_entity_id), "file_path", "") or "")), edge.id))
            for call in call_edges[:4]:
                meta = call.meta_json or {}
                expressions = meta.get("argument_expressions") or []
                caller = callers_by_id.get(call.src_entity_id)
                if caller is None or position >= len(expressions) or not source_visible(db, user, caller.source_id):
                    continue
                refs = meta.get("argument_refs") or []
                ref = refs[position] if position < len(refs) else None
                followed = _entity_by_qname(db, project_id, (ref or {}).get("qualified_name"))
                line = call.src_start_line or 0
                step = {"field": current.name, "passed_by": caller.name, "file": caller.file_path, "line": line,
                        "cite": f"{caller.file_path}:{line}", "operation": "argument",
                        "statement": f"{_short(parent.qualified_name)}(… {expressions[position]} …)"[:140],
                        "reads": [expressions[position]]}
                out.append((step, [followed] if followed is not None and role_of(followed.type) == "data" else []))
    return out


def data_origin(db: Session, user: User, project_id: int, field: CodeEntity, depth: int = 5, max_steps: int = 10) -> list[dict]:
    """Where a data entity gets its value, followed backwards through the sources of every writing statement.

    Works for every language that follows the parser contract (see the comment above); a step is an index fact with
    its source line (`cite`), not a complete runtime flow."""
    steps: list[dict] = []
    seen = {field.id}
    frontier = [field]
    for _level in range(depth):
        following: list[CodeEntity] = []
        for current in frontier:
            for step, followed in [*_origin_edge_statements(db, user, project_id, current),
                                   *_origin_table_statements(db, user, project_id, current)]:
                if len(steps) >= max_steps:
                    return steps
                steps.append(step)
                for entity in followed:
                    if entity.id not in seen:
                        seen.add(entity.id)
                        following.append(entity)
        if not following:
            break
        frontier = following
    return steps
