"""CICS-Bezüge über Dateigrenzen: Masken der Dialogprogramme und Datasets hinter CICS-Dateien.

`USES_MAP` (cobol/exec.py) nennt Maske und Mapset; die Maske liegt in einer BMS-Datei (bms/parse.py). Aufgelöst wird
nur bei genau einem Treffer (E-1 „kein Raten“): gleicher Maskenname, gleiches Mapset, sofern die Kante eins nennt.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from core.dataset_assignment import (
    EDGE_TYPE as ASSIGNED_DATASET,
    assignment_key,
    derive_assignments,
)
from doctus_models.database import CodeEdge, CodeEntity


def resolve_map_edges(db: Session, source_id: int) -> int:
    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.type == "USES_MAP",
            CodeEdge.resolution == "unresolved",
            CodeEdge.dst_entity_id.is_(None),
        )
        .all()
    )
    if not edges:
        return 0
    maps = defaultdict(list)
    for entity in (
        db.query(CodeEntity)
        .filter(CodeEntity.source_id == source_id, CodeEntity.type == "bms_map")
        .all()
    ):
        maps[entity.name.upper()].append(entity)
    resolved = 0
    for edge in edges:
        mapset = ((edge.meta_json or {}).get("mapset") or "").upper()
        matches = [
            entity
            for entity in maps.get(edge.dst_name.upper(), [])
            if entity.variant_key in (edge.variant_key, "default")
            and (not mapset or ((entity.meta_json or {}).get("mapset") or "").upper() == mapset)
        ]
        if len(matches) == 1:
            edge.dst_entity_id = matches[0].id
            edge.resolution = "resolved"
            resolved += 1
    return resolved


def derive_dataset_assignments(db: Session, source_id: int) -> int:
    """O-147: `ASSIGNED_DATASET`-Kanten Datei → Dataset neu ableiten (idempotent). Gibt neue Kanten zurück."""
    entities = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.type.in_(("jcl_step", "jcl_dataset", "program", "file_fd")),
        )
        .all()
    )
    step_ids = [entity.id for entity in entities if entity.type == "jcl_step"]
    edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.src_entity_id.in_(step_ids),
            CodeEdge.type.in_(("EXECUTES", "READS", "WRITES", "USES_DATASET")),
        )
        .all()
        if step_ids
        else []
    )
    desired = {assignment_key(record): record for record in derive_assignments(entities, edges)}
    existing = {}
    for edge in (
        db.query(CodeEdge)
        .filter(CodeEdge.source_id == source_id, CodeEdge.type == ASSIGNED_DATASET)
        .all()
    ):
        meta = edge.meta_json or {}
        key = (
            edge.src_entity_id,
            edge.dst_entity_id,
            meta.get("jcl_step_entity_id"),
            meta.get("ddname"),
        )
        if key in desired and key not in existing:
            existing[key] = edge
        else:
            db.delete(edge)  # veraltet (Ziel/Step/Programm hat sich geändert) oder doppelt
    created = 0
    for key, record in desired.items():
        edge = existing.get(key)
        if edge is not None:
            if edge.meta_json != record["meta"]:
                edge.meta_json = record["meta"]
            continue
        db.add(
            CodeEdge(
                project_id=record["project_id"],
                source_id=record["source_id"],
                variant_key=record["variant_key"],
                src_entity_id=record["src_entity_id"],
                dst_entity_id=record["dst_entity_id"],
                dst_name=record["dst_name"],
                type=ASSIGNED_DATASET,
                resolution="resolved",
                src_start_line=record["src_start_line"],
                src_end_line=record["src_end_line"],
                meta_json=record["meta"],
            )
        )
        created += 1
    return created
