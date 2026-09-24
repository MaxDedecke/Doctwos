"""
parser/tasks/edge_resolver.py
================================
Pass 2 (Plan §6.4, docs/ENTSCHEIDUNGEN.md E-1/E-2): löst globale Kantenarten
(CALL/COPY) über `dst_name` und geerbte Copybook-USES pfadgenau auf, sobald ihr Ziel
existiert — ohne Reparse. Läuft synchron am Ende jedes `GitConnector.sync()`
(kein eigener Celery-Task nötig, es ist ein einzelner beschränkter Query plus
ein paar UPDATEs, kein Hintergrundlauf im Sinne von link_builder.py).

Braucht das nicht nur, weil ein CALL 'B' aus Programm A geparst wird, bevor B
selbst an der Reihe ist (alphabetische/Dateisystem-Reihenfolge) — auch beim
inkrementellen Sync bleibt eine Kante so lange unresolved, bis ihr Ziel zum
ersten Mal geparst wurde, unabhängig davon, wie viele Syncs dazwischen liegen.

Rein programmlokale Kantenarten (PERFORM/GOTO/USES, `scope_entity_id` gesetzt)
sind hier absichtlich außen vor — die sind laut E-1 schon beim Parsen
vollständig auflösbar (parser/structure_persist.py) und dürfen NIE global über
dst_name gejoint werden (Paragraphen-/Feldnamen wie „INIT-PARA"/„WS-STATUS"
sind in hunderten Programmen gleich benannt).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy.orm import Session

from cobol.copybook import strip_copybook_extension
from core.model import Entity, ParseResult, ParsedEdge
from core.resource_resolution import resolve_resource_edges
from java.resolution import resolve_global_edges as resolve_java_global_edges
from models.database import CodeEdge, CodeEntity

# CALL-Ziele sind Programme, COPY-Ziele sind Copybooks — getrennt statt über
# einen gemeinsamen Namensindex, damit ein Programm und ein gleichnamiges
# Copybook (unwahrscheinlich, aber möglich) sich nicht gegenseitig verdecken.
_TARGET_TYPE_BY_EDGE_TYPE = {"CALL": "program", "COPY": "copybook"}


def _resolve_cobol_edges(db: Session, source_id: int) -> int:
    """Löst offene CALL/COPY- und Copybook-USES-Kanten dieser Quelle auf. Nur bei GENAU
    EINEM Treffer (E-1/E-2 „kein Raten“) — ein Namenskonflikt (z.B. zwei
    gleich benannte Programme im selben Repo) bleibt bewusst unresolved statt
    falsch verdrahtet zu werden. Gibt die Anzahl neu aufgelöster Kanten zurück;
    der öffentliche Resolver übernimmt den gemeinsamen Commit für COBOL und
    Java."""
    candidates = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.source_id == source_id,
            CodeEdge.resolution == "unresolved",
            CodeEdge.dst_entity_id.is_(None),
            CodeEdge.type.in_((*_TARGET_TYPE_BY_EDGE_TYPE.keys(), "USES")),
        )
        .all()
    )
    if not candidates:
        return 0

    by_variant_type_and_name: dict[tuple[str, str, str], list[CodeEntity]] = {}
    targets = (
        db.query(CodeEntity)
        .filter(CodeEntity.source_id == source_id, CodeEntity.type.in_(("program", "copybook")))
        .all()
    )
    for row in targets:
        by_variant_type_and_name.setdefault(
            (row.variant_key, row.type, row.name.upper()), []
        ).append(row)

    resolved = 0
    for edge in candidates:
        if edge.type == "USES":
            meta = edge.meta_json or {}
            target_qname = meta.get("target_qualified_name")
            target_path = meta.get("copybook_path")
            if not target_qname or not target_path:
                continue
            matches = (
                db.query(CodeEntity)
                .filter(
                    CodeEntity.source_id == source_id,
                    CodeEntity.type == "data_item",
                    CodeEntity.variant_key == edge.variant_key,
                    CodeEntity.file_path == target_path,
                    CodeEntity.qualified_name == target_qname,
                )
                .all()
            )
            if len(matches) == 1:
                edge.dst_entity_id = matches[0].id
                edge.resolution = "resolved"
                resolved += 1
            continue
        target_type = _TARGET_TYPE_BY_EDGE_TYPE[edge.type]
        dst_name = strip_copybook_extension(edge.dst_name) if edge.type == "COPY" else edge.dst_name
        matches = by_variant_type_and_name.get(
            (edge.variant_key, target_type, dst_name.upper()), []
        )
        if len(matches) == 1:
            edge.dst_entity_id = matches[0].id
            edge.resolution = "resolved"
            resolved += 1

    return resolved


def _java_parse_results(
    entities: list[CodeEntity], edges: list[CodeEdge]
) -> list[tuple[ParseResult, list[CodeEdge], list[ParsedEdge]]]:
    """Rebuild the Java resolver's DB-free input from persisted rows.

    This is deliberately a small adapter rather than a second Java resolver:
    it lets resume/reparse runs resolve against unchanged files that were not
    parsed in the current sync as well as files just written by the connector.
    """
    by_id = {entity.id: entity for entity in entities}
    by_variant_path: dict[tuple[str, str], list[CodeEntity]] = defaultdict(list)
    for entity in entities:
        if (entity.meta_json or {}).get("language") == "java":
            by_variant_path[(entity.variant_key, entity.file_path)].append(entity)

    edges_by_source: dict[tuple[str, str], list[CodeEdge]] = defaultdict(list)
    for edge in edges:
        source = by_id.get(edge.src_entity_id)
        if source is None or (source.meta_json or {}).get("language") != "java":
            continue
        edges_by_source[(edge.variant_key, source.file_path)].append(edge)

    results: list[tuple[ParseResult, list[CodeEdge], list[ParsedEdge]]] = []
    for (variant_key, path), file_entities in sorted(by_variant_path.items()):
        # Package entities are shared by files.  Include the package parent of
        # this file's declarations so package/import resolution remains valid
        # even when that package row was first persisted by another file.
        included = {entity.id: entity for entity in file_entities}
        for entity in file_entities:
            parent = by_id.get(entity.parent_id)
            if parent is not None and parent.type in {"package", "module"}:
                included[parent.id] = parent

        shared_entities = [
            Entity(
                type=entity.type,
                name=entity.name,
                start_line=entity.start_line or 1,
                end_line=entity.end_line or entity.start_line or 1,
                qualified_name=entity.qualified_name,
                meta=dict(entity.meta_json or {}),
                parent_qualified_name=(
                    by_id[entity.parent_id].qualified_name if entity.parent_id in by_id else None
                ),
            )
            for entity in included.values()
        ]
        persisted_edges = edges_by_source.get((variant_key, path), [])
        parsed_edges: list[ParsedEdge] = []
        for edge in persisted_edges:
            source = by_id[edge.src_entity_id]
            scope = by_id.get(edge.scope_entity_id) if edge.scope_entity_id else None
            parsed_edges.append(
                ParsedEdge(
                    type=edge.type,
                    src_name=source.qualified_name or source.name,
                    dst_name=edge.dst_name,
                    resolution=edge.resolution,
                    src_start_line=edge.src_start_line,
                    src_end_line=edge.src_end_line,
                    scope=scope.qualified_name if scope else None,
                    meta=dict(edge.meta_json or {}),
                )
            )
        result = ParseResult(
            program_name=Path(path).stem or path,
            path=path,
            source_format="free",
            variant_key=variant_key,
            entities=shared_entities,
            edges=parsed_edges,
        )
        results.append((result, persisted_edges, parsed_edges))
    return results


def _resolve_java_edges(db: Session, source_id: int) -> int:
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all()
    result_pairs = _java_parse_results(entities, edges)
    if not result_pairs:
        return 0

    resolved = resolve_java_global_edges(pair[0] for pair in result_pairs)
    entity_by_variant_qname: dict[tuple[str, str], list[CodeEntity]] = defaultdict(list)
    for entity in entities:
        if entity.qualified_name:
            entity_by_variant_qname[(entity.variant_key, entity.qualified_name)].append(entity)

    for result, persisted_edges, parsed_edges in result_pairs:
        for persisted, parsed in zip(persisted_edges, parsed_edges):
            target_qname = (parsed.meta or {}).get("target_qualified_name")
            target_path = (parsed.meta or {}).get("target_file_path")
            target_matches = (
                entity_by_variant_qname.get((result.variant_key, target_qname), [])
                if target_qname
                else []
            )
            if target_path:
                target_matches = [
                    entity for entity in target_matches if entity.file_path == target_path
                ]
            if parsed.resolution == "resolved" and len(target_matches) == 1:
                persisted.dst_entity_id = target_matches[0].id
                persisted.resolution = "resolved"
            elif parsed.resolution != "resolved":
                persisted.dst_entity_id = None
                persisted.resolution = parsed.resolution
            persisted.meta_json = parsed.meta or None

    return resolved


def _resolve_xslt_edges(db: Session, source_id: int) -> int:
    """Resolve XSLT module/resource and unambiguous template references.

    XSLT parsing is intentionally file-local.  Includes, imports and XML
    inputs can therefore only be connected after the repository has been
    persisted.  Named templates and match/mode pairs are resolved only when
    exactly one candidate exists; cycles and ambiguous modes remain visible as
    unresolved edges instead of being guessed.
    """
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = (
        db.query(CodeEdge)
        .filter(CodeEdge.source_id == source_id, CodeEdge.resolution == "unresolved")
        .all()
    )
    if not edges:
        return 0

    by_variant_qname: dict[tuple[str, str], list[CodeEntity]] = defaultdict(list)
    templates_by_name: dict[tuple[str, str], list[CodeEntity]] = defaultdict(list)
    templates_by_match_mode: dict[tuple[str, str, str], list[CodeEntity]] = defaultdict(list)
    for entity in entities:
        if entity.qualified_name:
            by_variant_qname[(entity.variant_key, entity.qualified_name)].append(entity)
        if entity.type != "xslt_template":
            continue
        meta = entity.meta_json or {}
        name = meta.get("template_name")
        mode = meta.get("mode") or "#default"
        match = meta.get("match")
        if name:
            templates_by_name[(entity.variant_key, name)].append(entity)
        if match:
            templates_by_match_mode[(entity.variant_key, match, mode)].append(entity)

    resolved = 0
    for edge in edges:
        meta = edge.meta_json or {}
        if meta.get("language") != "xslt":
            continue
        candidates: list[CodeEntity] = []
        target_qname = meta.get("target_qualified_name")
        target_file = meta.get("target_file_path")
        target_type = meta.get("target_entity_type")
        if target_qname and not target_file:
            candidates = [
                entity
                for entity in by_variant_qname.get((edge.variant_key, target_qname), [])
                if not target_type or entity.type == target_type
            ]
        elif target_file:
            candidates = [
                entity
                for entity in entities
                if entity.variant_key == edge.variant_key
                and entity.file_path == target_file
                and (not target_type or entity.type == target_type)
                and (not target_qname or entity.qualified_name == target_qname)
            ]
        elif edge.type == "CALLS_TEMPLATE" and meta.get("template_name"):
            candidates = templates_by_name.get(
                (edge.variant_key, meta["template_name"]), []
            )
        elif edge.type == "APPLIES_TEMPLATES":
            mode = meta.get("mode") or "#default"
            select = (meta.get("select") or "").strip()
            candidates = templates_by_match_mode.get(
                (edge.variant_key, select, mode), []
            )

        if len(candidates) == 1:
            edge.dst_entity_id = candidates[0].id
            edge.resolution = "resolved"
            meta["target_qualified_name"] = candidates[0].qualified_name
            meta["resolution_scope"] = "source"
            edge.meta_json = meta
            resolved += 1
    return resolved


def _resolve_markup_edges(db: Session, source_id: int) -> int:
    """Connect only literal repository-relative JSP/HTML resource references.

    Form actions deliberately stay unresolved: mapping a URL to a servlet or
    controller requires framework configuration (O-246), which is not inferred
    from a page alone. Includes and literal links do have a file-level proof.
    """
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(
        CodeEdge.source_id == source_id, CodeEdge.resolution == "unresolved"
    ).all()
    resolved = 0
    for edge in edges:
        meta = edge.meta_json or {}
        if meta.get("language") not in {"jsp", "html"}:
            continue
        target_file = meta.get("target_file_path")
        if not target_file:
            continue
        target_type = meta.get("target_entity_type")
        candidates = [
            entity for entity in entities
            if entity.variant_key == edge.variant_key and entity.file_path == target_file
            and (not target_type or entity.type == target_type)
        ]
        if len(candidates) == 1:
            edge.dst_entity_id = candidates[0].id
            edge.resolution = "resolved"
            meta["target_qualified_name"] = candidates[0].qualified_name
            meta["resolution_scope"] = "source"
            edge.meta_json = meta
            resolved += 1
    return resolved


def _resolve_shell_edges(db: Session, source_id: int) -> int:
    """Resolve literal script/XSLT paths and unambiguous Java main classes."""
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(
        CodeEdge.source_id == source_id, CodeEdge.resolution == "unresolved"
    ).all()
    resolved = 0
    for edge in edges:
        meta = edge.meta_json or {}
        if meta.get("language") != "shell":
            continue
        target_file = meta.get("target_file_path")
        target_qname = meta.get("target_qualified_name")
        target_type = meta.get("target_entity_type")
        candidates = [
            entity for entity in entities
            if entity.variant_key == edge.variant_key
            and ((target_file and entity.file_path == target_file) or (target_qname and entity.qualified_name == target_qname))
            and (not target_type or entity.type == target_type)
        ]
        if len(candidates) == 1:
            edge.dst_entity_id = candidates[0].id
            edge.resolution = "resolved"
            meta["target_qualified_name"] = candidates[0].qualified_name
            meta["resolution_scope"] = "source"
            edge.meta_json = meta
            resolved += 1
    return resolved


def _resolve_jcl_edges(db: Session, source_id: int) -> int:
    """Resolve literal JCL PGM/PROC targets within one source and variant."""
    entities = db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all()
    edges = db.query(CodeEdge).filter(
        CodeEdge.source_id == source_id,
        CodeEdge.type == "EXECUTES",
        CodeEdge.resolution == "unresolved",
    ).all()
    by_variant_type_name: dict[tuple[str, str, str], list[CodeEntity]] = defaultdict(list)
    for entity in entities:
        key_name = entity.name.upper()
        by_variant_type_name[(entity.variant_key, entity.type, key_name)].append(entity)

    resolved = 0
    for edge in edges:
        meta = edge.meta_json or {}
        if meta.get("language") != "jcl" or meta.get("dynamic_target"):
            continue
        target_type = meta.get("target_entity_type")
        target_name = meta.get("target_program_name") or meta.get("target_proc_name")
        if not target_type or not target_name:
            continue
        candidates = by_variant_type_name.get((edge.variant_key, target_type, target_name.upper()), [])
        if len(candidates) == 1:
            edge.dst_entity_id = candidates[0].id
            edge.resolution = "resolved"
            meta["target_qualified_name"] = candidates[0].qualified_name
            meta["resolution_scope"] = "source"
            edge.meta_json = meta
            resolved += 1
    return resolved


def resolve_global_edges(db: Session, source_id: int) -> int:
    """Resolve persisted COBOL and Java edges for one source.

    COBOL keeps its existing DB-native CALL/COPY pass. Java rows are adapted
    back to the DB-free resolver so all files in the source participate,
    including files skipped by an unchanged-content resume.
    """
    resolved = _resolve_cobol_edges(db, source_id)
    resolved += _resolve_java_edges(db, source_id)
    resolved += _resolve_xslt_edges(db, source_id)
    resolved += _resolve_markup_edges(db, source_id)
    resolved += _resolve_shell_edges(db, source_id)
    resolved += _resolve_jcl_edges(db, source_id)
    resolved += resolve_resource_edges(
        db.query(CodeEntity).filter(CodeEntity.source_id == source_id).all(),
        db.query(CodeEdge).filter(CodeEdge.source_id == source_id).all(),
    )
    # Open reasons and invalidated resource targets must also be persisted.
    db.commit()
    return resolved
