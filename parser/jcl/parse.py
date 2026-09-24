"""Conservative, non-executing JCL structure parser.

The parser records job steps, literal program/PROC invocations and DD datasets.
It does not expand symbols, execute procedures, interpret IF/COND control flow,
or claim that a DISP value proves a COBOL OPEN mode.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from code_parser import CodeParser
from core.model import Chunk, Entity, ParseResult, ParsedEdge

_STATEMENT = re.compile(r"^([A-Z]+)\b(.*)$", re.I | re.S)
_RECOGNIZED = {"JOB", "EXEC", "DD", "PROC", "PEND", "SET", "INCLUDE"}
_DSN = re.compile(r"\bDSN(?:AME)?\s*=\s*(?:'([^']+)'|\"([^\"]+)\"|([^,\s()]+))", re.I)
_PGM = re.compile(r"\bPGM\s*=\s*(?:'([^']+)'|\"([^\"]+)\"|([^,\s()]+))", re.I)
_PROC = re.compile(r"\bPROC\s*=\s*(?:'([^']+)'|\"([^\"]+)\"|([^,\s()]+))", re.I)
_DISP = re.compile(r"\bDISP\s*=\s*\(?\s*([A-Z]+)", re.I)


def _logical_statements(source: str):
    """Yield fixed-column JCL statements with physical start/end lines."""
    current: dict | None = None
    in_stream = False
    for line_number, line in enumerate(source.splitlines(), 1):
        if in_stream:
            if line.startswith("/*"):
                in_stream = False
            continue
        if line.startswith("//*"):
            continue
        if not line.startswith("//"):
            continue

        label = line[2:10].strip() if len(line) > 2 else ""
        operand = line[11:71].strip() if len(line) > 11 else ""
        if not operand:
            continue
        match = _STATEMENT.match(operand)
        keyword = match.group(1).upper() if match else ""
        begins_statement = bool(label) or keyword in _RECOGNIZED
        if begins_statement:
            if current is not None:
                yield current
            current = {"label": label, "operand": operand, "line": line_number, "end_line": line_number}
            if keyword == "DD" and re.match(r"^DD\s+(?:\*|DATA)(?:\s|,|$)", operand, re.I):
                yield current
                current = None
                in_stream = True
        elif current is not None:
            # Continuation cards contribute operands only; no arbitrary source
            # text is interpreted as a second statement.
            current["operand"] += " " + operand
            current["end_line"] = line_number
    if current is not None:
        yield current


def _value(match: re.Match | None) -> str | None:
    if match is None:
        return None
    return next((value for value in match.groups() if value), None)


def _qualified(path: str, kind: str, name: str) -> str:
    return f"{path}::{kind}:{name}"


def _is_dynamic(value: str) -> bool:
    return "&" in value or value.startswith("*.")


def _unique_name(name: str, counts: dict[str, int]) -> str:
    key = name.upper()
    counts[key] = counts.get(key, 0) + 1
    return name if counts[key] == 1 else f"{name}#{counts[key]}"


def parse_jcl_file(source: str, path: str, **_: object) -> ParseResult:
    normalized = PurePosixPath(path.replace("\\", "/")).as_posix()
    filename = PurePosixPath(normalized).name
    file_root = Entity(
        type="jcl_file", name=filename, start_line=1,
        end_line=max(1, len(source.splitlines())), qualified_name=normalized,
        meta={"language": "jcl", "is_file_root": True},
    )
    entities = [file_root]
    edges: list[ParsedEdge] = []
    jobs: list[Entity] = []
    procedures: list[Entity] = []
    datasets: dict[str, Entity] = {}
    job_counts: dict[str, int] = {}
    proc_counts: dict[str, int] = {}
    step_counts: dict[str, int] = {}
    current_job: Entity | None = None
    current_proc: Entity | None = None
    current_step: Entity | None = None
    implicit_job: Entity | None = None
    step_order = 0

    def make_job(name: str, line: int, *, implicit: bool = False) -> Entity:
        unique = _unique_name(name, job_counts)
        entity = Entity(
            type="jcl_job", name=unique, start_line=line, end_line=line,
            parent_name=file_root.name, parent_qualified_name=normalized,
            qualified_name=_qualified(normalized, "job", unique),
            meta={"language": "jcl", "implicit": implicit},
        )
        jobs.append(entity)
        entities.append(entity)
        return entity

    def make_proc(name: str, line: int) -> Entity:
        unique = _unique_name(name, proc_counts)
        entity = Entity(
            type="jcl_proc", name=unique, start_line=line, end_line=line,
            parent_name=file_root.name, parent_qualified_name=normalized,
            qualified_name=_qualified(normalized, "proc", unique),
            meta={"language": "jcl"},
        )
        procedures.append(entity)
        entities.append(entity)
        return entity

    for statement in _logical_statements(source):
        match = _STATEMENT.match(statement["operand"])
        if not match:
            continue
        keyword, arguments = match.group(1).upper(), match.group(2).strip()
        line = statement["line"]

        if keyword == "JOB":
            current_job = make_job(statement["label"] or f"JOB-{len(jobs) + 1}", line)
            current_proc = current_step = None
            continue
        if keyword == "PROC":
            current_proc = make_proc(statement["label"] or f"PROC-{len(procedures) + 1}", line)
            current_step = None
            current_proc.meta["parameters_declared"] = "=" in arguments
            continue
        if keyword == "PEND":
            if current_proc is not None:
                current_proc.end_line = statement["end_line"]
            current_proc = current_step = None
            continue
        if keyword == "EXEC":
            if current_job is None and current_proc is None:
                if implicit_job is None:
                    implicit_job = make_job(PurePosixPath(normalized).stem or "JOB", line, implicit=True)
                current_job = implicit_job
            step_order += 1
            parent = current_proc or current_job
            container_qname = parent.qualified_name if parent else normalized
            container_name = parent.name if parent else file_root.name
            base_name = statement["label"] or f"STEP-{step_order}"
            unique = _unique_name(base_name, step_counts)
            step = Entity(
                type="jcl_step", name=unique, start_line=line, end_line=statement["end_line"],
                parent_name=container_name, parent_qualified_name=container_qname,
                qualified_name=f"{container_qname}::step:{unique}",
                meta={"language": "jcl", "step_order": step_order},
            )
            entities.append(step)
            current_step = step
            if parent is not None:
                edges.append(ParsedEdge(
                    type="CONTAINS", src_name=parent.qualified_name or parent.name,
                    dst_name=step.name, resolution="resolved",
                    src_start_line=line, src_end_line=statement["end_line"],
                    meta={
                        "language": "jcl", "relationship_kind": "job_step",
                        "target_qualified_name": step.qualified_name,
                        "target_entity_type": "jcl_step",
                    },
                ))

            pgm = _value(_PGM.search(arguments))
            proc = _value(_PROC.search(arguments))
            if pgm:
                target, target_type, kind = pgm, "program", "program"
            elif proc:
                target, target_type, kind = proc, "jcl_proc", "procedure"
            else:
                positional = arguments.split(",", 1)[0].strip().split()
                target = positional[0] if positional and "=" not in positional[0] else None
                target, target_type, kind = target, "jcl_proc", "procedure"
            if target:
                dynamic = _is_dynamic(target)
                edges.append(ParsedEdge(
                    type="EXECUTES", src_name=step.qualified_name or step.name,
                    dst_name=target, resolution="dynamic" if dynamic else "unresolved",
                    src_start_line=line, src_end_line=statement["end_line"],
                    meta={
                        "language": "jcl", "execution_kind": kind,
                        "target_entity_type": target_type,
                        "target_program_name": target.upper() if kind == "program" and not dynamic else None,
                        "target_proc_name": target.upper() if kind == "procedure" and not dynamic else None,
                        "dynamic_target": dynamic,
                    },
                ))
            continue

        if keyword != "DD" or current_step is None:
            continue
        dataset_name = _value(_DSN.search(arguments))
        if not dataset_name or re.fullmatch(r"(?i)(?:DUMMY|SYSOUT=.*)", dataset_name):
            continue
        normalized_dataset = dataset_name.upper()
        dynamic = _is_dynamic(dataset_name)
        dataset = datasets.get(normalized_dataset)
        if dataset is None:
            dataset = Entity(
                type="jcl_dataset", name=dataset_name, start_line=line,
                end_line=statement["end_line"], parent_name=file_root.name,
                parent_qualified_name=normalized,
                qualified_name=_qualified(normalized, "dataset", normalized_dataset),
                meta={"language": "jcl", "dataset_name": dataset_name, "dynamic": dynamic},
            )
            datasets[normalized_dataset] = dataset
            entities.append(dataset)

        disp_match = _DISP.search(arguments)
        disposition = disp_match.group(1).upper() if disp_match else None
        if disposition in {"NEW", "MOD"}:
            edge_type, access_basis = "WRITES", f"DISP={disposition} suggests output allocation"
        elif disposition == "SHR":
            edge_type, access_basis = "READS", "DISP=SHR is a likely input, not proof of COBOL OPEN mode"
        else:
            edge_type, access_basis = "USES_DATASET", "JCL does not declare application read/write mode"
        edges.append(ParsedEdge(
            type=edge_type, src_name=current_step.qualified_name or current_step.name,
            dst_name=dataset_name, resolution="dynamic" if dynamic else "resolved",
            src_start_line=line, src_end_line=statement["end_line"],
            meta={
                "language": "jcl", "ddname": statement["label"] or None,
                "disposition": disposition, "access_certainty": "possible" if edge_type in {"READS", "WRITES"} else "certain",
                "access_basis": access_basis,
                "target_qualified_name": None if dynamic else dataset.qualified_name,
                "target_entity_type": "jcl_dataset",
            },
        ))

    # Resolve only an unambiguous in-file PROC statically. External procedure
    # libraries are handled later against the complete indexed source.
    procs_by_name: dict[str, list[Entity]] = {}
    for procedure in procedures:
        procs_by_name.setdefault(procedure.name.split("#", 1)[0].upper(), []).append(procedure)
    for edge in edges:
        meta = edge.meta
        proc_name = meta.get("target_proc_name")
        matches = procs_by_name.get(proc_name, []) if proc_name else []
        if len(matches) == 1:
            meta["target_qualified_name"] = matches[0].qualified_name

    chunks = [
        Chunk(
            content=item["content"], start_line=item["start_line"], end_line=item["end_line"],
            meta={"language": "jcl", "symbol_type": "source", **item.get("meta", {})},
        )
        for item in CodeParser("jcl").chunk_file(source)
    ]
    return ParseResult(
        program_name=PurePosixPath(normalized).stem or "jcl", path=path,
        source_format="fixed", entities=entities, edges=edges, chunks=chunks,
    )
