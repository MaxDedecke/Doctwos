"""O-147: Programm-Dataset-Zuordnung über den DD-Namen.

Ein COBOL-Programm bindet eine Datei per `SELECT … ASSIGN TO ddname` an einen JCL-DD-Namen. Startet ein
JCL-Step dieses Programm (`EXEC PGM=…`, als `EXECUTES` aufgelöst) und trägt ein DD-Statement denselben
Namen, dann ist das Dataset dieses DD die Datei des Programms in diesem Lauf. Daraus wird eine abgeleitete
Kante `ASSIGNED_DATASET` von der Datei-Entity (`file_fd`) zur Dataset-Entity (`jcl_dataset`).

Nur belegte Fälle: exakter DD-Name (ohne Groß-/Kleinschreibung), genau eine Datei mit diesem Namen im
Programm, aufgelöstes Programm und aufgelöstes Dataset. Die Kante bleibt `possible`, weil ein Lauf
Datasets überschreiben, verketten oder per PROC ändern kann; Lese- oder Schreibrichtung ergibt sich aus
dem DD nicht (siehe `access_certainty`). Abgeleitete Kanten tragen `meta.derived_by` und werden bei
jedem Lauf des Resolvers neu berechnet, veraltete entfernt.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

EDGE_TYPE = "ASSIGNED_DATASET"
DERIVED_BY = "jcl_dd_assign"
_DD_EDGE_TYPES = frozenset({"READS", "WRITES", "USES_DATASET"})
_BASIS = (
    "DD name equals the ASSIGN TO name of a file in the program started by the step; "
    "a run may override, concatenate or change datasets"
)


def assignment_key(record: dict[str, Any]) -> tuple[int, int, int, str]:
    """Identität einer abgeleiteten Kante: Datei, Dataset, Step, DD-Name."""
    meta = record["meta"]
    return (record["src_entity_id"], record["dst_entity_id"], meta["jcl_step_entity_id"], meta["ddname"])


def derive_assignments(entities: Iterable[Any], edges: Iterable[Any]) -> list[dict[str, Any]]:
    """Abgeleitete Kanten als Datensätze (ohne Datenbankbezug)."""
    by_id = {entity.id: entity for entity in entities}
    program_of_step: dict[int, Any] = {}
    dd_edges: dict[int, list[Any]] = defaultdict(list)
    for edge in edges:
        source = by_id.get(edge.src_entity_id)
        if source is None or source.type != "jcl_step":
            continue
        meta = edge.meta_json or {}
        if edge.type == "EXECUTES" and edge.resolution == "resolved" and edge.dst_entity_id in by_id:
            target = by_id[edge.dst_entity_id]
            if target.type == "program":
                program_of_step[source.id] = target
        elif edge.type in _DD_EDGE_TYPES and meta.get("ddname") and edge.dst_entity_id in by_id:
            if by_id[edge.dst_entity_id].type == "jcl_dataset":
                dd_edges[source.id].append(edge)

    files_by_program: dict[int, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for entity in by_id.values():
        if entity.type != "file_fd" or entity.parent_id is None:
            continue
        assign = str((entity.meta_json or {}).get("assign") or "").strip().upper()
        if assign:
            files_by_program[entity.parent_id][assign].append(entity)

    records: list[dict[str, Any]] = []
    seen: set[tuple[int, int, int, str]] = set()
    for step_id, program in program_of_step.items():
        step = by_id[step_id]
        for edge in dd_edges.get(step_id, []):
            ddname = str((edge.meta_json or {})["ddname"]).strip().upper()
            candidates = files_by_program.get(program.id, {}).get(ddname, [])
            if len(candidates) != 1:
                continue  # kein Treffer oder mehrdeutig: nichts raten
            file_entity, dataset = candidates[0], by_id[edge.dst_entity_id]
            dd_meta = edge.meta_json or {}
            record = {
                "src_entity_id": file_entity.id,
                "dst_entity_id": dataset.id,
                "project_id": file_entity.project_id,
                "source_id": file_entity.source_id,
                "variant_key": file_entity.variant_key,
                "dst_name": dataset.name,
                "src_start_line": file_entity.start_line or 0,
                "src_end_line": file_entity.end_line or file_entity.start_line or 0,
                "meta": {
                    "language": "cobol",
                    "derived_by": DERIVED_BY,
                    "certainty": "possible",
                    "basis": _BASIS,
                    "ddname": ddname,
                    "assign": str((file_entity.meta_json or {}).get("assign")),
                    "program_qualified_name": program.qualified_name,
                    "jcl_step_entity_id": step.id,
                    "jcl_step_qualified_name": step.qualified_name,
                    "jcl_file_path": step.file_path,
                    "jcl_start_line": edge.src_start_line,
                    "dataset_name": (dataset.meta_json or {}).get("dataset_name") or dataset.name,
                    "dynamic_dataset": bool((dataset.meta_json or {}).get("dynamic")),
                    "disposition": dd_meta.get("disposition"),
                    "access_certainty": dd_meta.get("access_certainty"),
                },
            }
            key = assignment_key(record)
            if key not in seen:
                seen.add(key)
                records.append(record)
    return records
