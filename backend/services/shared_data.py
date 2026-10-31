"""Wer teilt welche Datei? Verbindet einzelne Programmabläufe zu einem Prozess.

Batch-Programme finden ihr Dataset über die DD-Anweisung des Jobs, Dialogprogramme über die CICS-Definition
der Datei, und SQL nennt die Tabelle direkt. Gemeinsam ist der Name des Datasets bzw. der Tabelle; alle Angaben
stammen aus dem Index. Eine Datei, die nur per CICS-Name bekannt ist, bleibt unter diesem Namen getrennt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from doctus_models.database import CodeEdge, CodeEntity

MAX_RESOURCES = 200
_CICS_READS = frozenset({"READ", "READNEXT", "READPREV", "STARTBR", "RESETBR", "ENDBR"})
_CICS_WRITES = frozenset({"WRITE", "REWRITE", "DELETE", "UNLOCK"})
_OPEN_ACCESS = {"INPUT": {"read"}, "OUTPUT": {"write"}, "EXTEND": {"write"}, "I-O": {"read", "write"}}


@dataclass(frozen=True)
class _Use:
    key: str
    label: str
    kind: str
    program_id: int
    access: str
    via: str
    file_path: str
    line: int
    certainty: str


def _entities(db: Session, project_id: int, *types: str) -> list[CodeEntity]:
    return (
        db.query(CodeEntity)
        .filter(CodeEntity.project_id == project_id, CodeEntity.type.in_(types))
        .all()
    )


def _batch_uses(db: Session, project_id: int) -> list[_Use]:
    files = {row.id: row for row in _entities(db, project_id, "file_fd")}
    if not files:
        return []
    assigned = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id,
        CodeEdge.type == "ASSIGNED_DATASET",
        CodeEdge.src_entity_id.in_(files),
    )
    datasets: dict[int, set[str]] = defaultdict(set)
    for edge in assigned:
        datasets[edge.src_entity_id].add(edge.dst_name)

    uses: list[_Use] = []
    opened = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id,
        CodeEdge.type == "USES",
        CodeEdge.dst_entity_id.in_(datasets),
    )
    for edge in opened:
        mode = (edge.meta_json or {}).get("open_mode")
        source = files[edge.dst_entity_id]
        for access in _OPEN_ACCESS.get(mode, ()):
            for dataset in datasets[edge.dst_entity_id]:
                uses.append(
                    _Use(
                        key=f"dataset:{dataset.upper()}",
                        label=dataset,
                        kind="dataset",
                        program_id=source.parent_id,
                        access=access,
                        via="batch",
                        file_path=source.file_path,
                        line=edge.src_start_line,
                        # Eine DD-Anweisung kann beim Lauf überschrieben werden.
                        certainty="possible",
                    )
                )
    return uses


def _cics_uses(db: Session, project_id: int) -> list[_Use]:
    blocks = {row.id: row for row in _entities(db, project_id, "exec_block")}
    if not blocks:
        return []
    datasets = {
        row.name.upper(): (row.meta_json or {}).get("dataset")
        for row in _entities(db, project_id, "cics_file")
    }
    uses: list[_Use] = []
    edges = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id,
        CodeEdge.type == "USES",
        CodeEdge.src_entity_id.in_(blocks),
    )
    for edge in edges:
        meta = edge.meta_json or {}
        if meta.get("resource_kind") not in {"FILE", "DATASET"}:
            continue
        operation = meta.get("operation")
        access = (
            "read" if operation in _CICS_READS else "write" if operation in _CICS_WRITES else None
        )
        if access is None:
            continue
        block = blocks[edge.src_entity_id]
        if meta.get("dynamic"):
            names = [item["name"] for item in meta.get("candidate_targets") or []]
            # Mehrere mögliche Werte: Jeder ist ein Hinweis, keiner ein Beleg.
            certainty = "certain" if len(names) == 1 else "possible"
        else:
            names, certainty = [edge.dst_name], "certain"
        for name in names:
            dataset = datasets.get(name.upper())
            uses.append(
                _Use(
                    key=f"dataset:{dataset.upper()}" if dataset else f"cics:{name.upper()}",
                    label=dataset or name,
                    kind="dataset" if dataset else "cics_file",
                    program_id=block.parent_id,
                    access=access,
                    via="cics",
                    file_path=block.file_path,
                    line=edge.src_start_line,
                    certainty=certainty,
                )
            )
    return uses


def _sql_uses(db: Session, project_id: int) -> list[_Use]:
    tables = {row.id: row for row in _entities(db, project_id, "sql_table")}
    if not tables:
        return []
    blocks = {row.id: row for row in _entities(db, project_id, "sql_block")}
    edges = db.query(CodeEdge).filter(
        CodeEdge.project_id == project_id,
        CodeEdge.type.in_(("READS", "WRITES")),
        CodeEdge.dst_entity_id.in_(tables),
    )
    uses = []
    for edge in edges:
        block = blocks.get(edge.src_entity_id)
        if block is None:
            continue
        table = tables[edge.dst_entity_id].name
        uses.append(
            _Use(
                key=f"sql:{table.upper()}",
                label=table,
                kind="sql_table",
                program_id=block.parent_id,
                access="write" if edge.type == "WRITES" else "read",
                via="sql",
                file_path=block.file_path,
                line=edge.src_start_line,
                certainty="certain",
            )
        )
    return uses


def _focus_programs(db: Session, entity: CodeEntity) -> set[int]:
    """Die Programme zum Fokus: das umgebende Programm oder die, die ein Job oder Step startet."""
    if entity.type in {"jcl_job", "jcl_proc", "jcl_step"}:
        steps = (
            [entity.id]
            if entity.type == "jcl_step"
            else [
                row.id
                for row in db.query(CodeEntity.id).filter(
                    CodeEntity.parent_id == entity.id, CodeEntity.type == "jcl_step"
                )
            ]
        )
        return {
            row.dst_entity_id
            for row in db.query(CodeEdge.dst_entity_id).filter(
                CodeEdge.type == "EXECUTES",
                CodeEdge.src_entity_id.in_(steps),
                CodeEdge.dst_entity_id.isnot(None),
            )
        }
    current: CodeEntity | None = entity
    while current is not None and current.type != "program":
        current = db.get(CodeEntity, current.parent_id) if current.parent_id else None
    return {current.id} if current is not None else set()


def _jobs_of(db: Session, program_ids: set[int]) -> dict[int, list[str]]:
    rows = (
        db.query(CodeEdge.dst_entity_id, CodeEntity.parent_id)
        .join(CodeEntity, CodeEntity.id == CodeEdge.src_entity_id)
        .filter(
            CodeEdge.type == "EXECUTES",
            CodeEdge.dst_entity_id.in_(program_ids),
            CodeEntity.type == "jcl_step",
        )
        .all()
    )
    names = {
        row.id: row.name
        for row in db.query(CodeEntity.id, CodeEntity.name).filter(
            CodeEntity.id.in_({parent for _, parent in rows if parent})
        )
    }
    jobs: dict[int, set[str]] = defaultdict(set)
    for program_id, parent_id in rows:
        if parent_id in names:
            jobs[program_id].add(names[parent_id])
    return {program_id: sorted(values) for program_id, values in jobs.items()}


def shared_data(db: Session, entity: CodeEntity) -> dict:
    focus = _focus_programs(db, entity)
    if not focus or entity.project_id is None:
        return {"resources": [], "truncated": False}
    project_id = entity.project_id
    uses = [
        *_batch_uses(db, project_id),
        *_cics_uses(db, project_id),
        *_sql_uses(db, project_id),
    ]
    by_resource: dict[str, list[_Use]] = defaultdict(list)
    for use in uses:
        if use.program_id is not None:
            by_resource[use.key].append(use)
    relevant = {
        key: items
        for key, items in by_resource.items()
        if any(item.program_id in focus for item in items)
    }
    program_ids = {item.program_id for items in relevant.values() for item in items}
    names = {
        row.id: row.name
        for row in db.query(CodeEntity.id, CodeEntity.name).filter(CodeEntity.id.in_(program_ids))
    }
    jobs = _jobs_of(db, program_ids) if program_ids else {}

    resources = []
    for key, items in relevant.items():
        merged: dict[tuple[int, str], _Use] = {}
        for item in sorted(items, key=lambda use: (use.file_path, use.line)):
            merged.setdefault((item.program_id, item.access), item)
        users = [
            {
                "program": names.get(item.program_id, "?"),
                "entity_id": item.program_id,
                "access": item.access,
                "via": item.via,
                "jobs": jobs.get(item.program_id, []),
                "is_focus": item.program_id in focus,
                "certainty": item.certainty,
                "cite": f"{item.file_path}:{item.line}",
                "file_path": item.file_path,
                "line": item.line,
            }
            for item in merged.values()
        ]
        users.sort(key=lambda user: (not user["is_focus"], user["access"] != "write", user["program"]))
        first = items[0]
        resources.append(
            {
                "key": key,
                "label": first.label,
                "kind": first.kind,
                "users": users,
                "shared": len({user["entity_id"] for user in users}) > 1,
            }
        )
    resources.sort(key=lambda item: (not item["shared"], item["label"]))
    return {"resources": resources[:MAX_RESOURCES], "truncated": len(resources) > MAX_RESOURCES}
