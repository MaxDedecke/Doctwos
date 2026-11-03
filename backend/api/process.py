"""Bounded, evidence-backed Process View projection (O-292)."""

import re
from hashlib import sha256
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.entities import _assert_entity_visible
from api.process_schemas import (
    ProcessLocator,
    ProcessNode,
    ProcessProjection,
    ProcessTransition,
    ProcessTruncation,
)
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from doctus_models.database import CodeEdge, CodeEntity, KnowledgeSource, User
from doctus_models.language_profile import JAVA, REALIZATION_EDGES, role_of
from services.call_flow import TEST_PATH_PATTERN, cobol_entry_paragraph
from services.provenance import build_provenance
from services.shared_data import shared_data

router = APIRouter(prefix="/process", tags=["process"])

MAX_NODE_LIMIT = 500
MAX_EDGE_LIMIT = 1_000

# This is deliberately a conservative cross-language baseline. O-293 and
# O-294 refine it with COBOL/Java-specific semantics; inheritance and imports
# remain structure context and never become process transitions here.
EDGE_KIND = {
    "CALL": "call",
    "CALLS": "call",
    "PERFORM": "call",
    "INSTANTIATES": "call",
    "EXECUTES": "call",
    "CONTAINS": "call",
    "EXECUTES_SCRIPT": "call",
    "STARTS_JAVA": "call",
    "GOTO": "jump",
    "USES": "data_access",
    "READS": "data_access",
    "WRITES": "data_access",
    "USES_DATASET": "data_access",
    "ASSIGNED_DATASET": "data_access",
    "USES_RESOURCE": "data_access",
    "TRANSFORMS_WITH": "data_access",
}
KNOWN_PROCESS_KINDS = frozenset(set(EDGE_KIND.values()) | {"external_call", "iteration", "exit"})
# Eingebettete Anweisungen: Der Paragraph enthält den Block, der Ablauf zeigt die Anweisung darin.
EMBEDDED_BLOCK_TYPES = frozenset({"exec_block", "sql_block"})
EXIT_OPERATIONS = frozenset({"RETURN", "ABEND"})
_MAX_LABEL_RESOURCES = 2
# Woran man einen Aufruf erkennt, der den Ablauf nur begleitet. Die Ansicht blendet ihn auf Wunsch aus
# und nennt die Zahl; es ist eine Lesehilfe, keine Aussage über den Code.
_LOGGER_RECEIVERS = frozenset({"log", "logger"})
_UTILITY_RECEIVERS = frozenset(
    {
        "Arrays",
        "Boolean",
        "Collections",
        "Integer",
        "List",
        "Long",
        "Map",
        "Math",
        "Objects",
        "Optional",
        "Set",
        "String",
    }
)
_GETTER_NAME = re.compile(r"(?:get|is)[A-Z]\w*")
_FIELD_EXPRESSION = re.compile(r"(?:this\.)?\w+")
# Mit Annotation und geschweiften Klammern auf eigenen Zeilen.
_ACCESSOR_MAX_LINES = 6
# Ohne Rückgabeausdruck: abstrakte Methode oder unbekannter Rumpf.
_ABSTRACT_MAX_LINES = 3
# Eine Datei oder Klasse hat keinen eigenen Ablauf: Einstieg sind ihre Methoden.
_ENTRY_LIST_ROOTS = JAVA.containers | {"compilation_unit"}
_MEMBER_TYPES = JAVA.containers | JAVA.routines
_REALIZATION_DEPTH = 3
_MAX_REALIZERS = 40


def _language(entity: CodeEntity) -> str:
    return str((entity.meta_json or {}).get("language") or "unknown")


def _node_id(entity_id: int) -> str:
    return f"entity:{entity_id}"


def _entity_locator(entity: CodeEntity, provenance: dict | None = None) -> ProcessLocator:
    return ProcessLocator(
        source_id=entity.source_id,
        file_path=entity.file_path or "<unknown>",
        start_line=entity.start_line or 1,
        end_line=entity.end_line,
        provenance=provenance,
    )


def _edge_locator(
    edge: CodeEdge, source: CodeEntity, provenance: dict | None = None
) -> ProcessLocator:
    # Older persisted CodeEdges can have line 0. The entity declaration is an
    # explicitly detectable fallback that remains openable; parsers should
    # populate src_start_line for the precise call site.
    start_line = edge.src_start_line if edge.src_start_line >= 1 else source.start_line or 1
    end_line = edge.src_end_line if edge.src_end_line >= start_line else start_line
    return ProcessLocator(
        source_id=source.source_id,
        file_path=source.file_path or "<unknown>",
        start_line=start_line,
        end_line=end_line,
        provenance=provenance,
    )


def _edge_kind(edge: CodeEdge) -> str | None:
    if edge.resolution != "resolved":
        if edge.type in {"CALL", "CALLS", "PERFORM"}:
            return "external_call"
    return EDGE_KIND.get(edge.type)


def _transition_kind(edge: CodeEdge) -> str | None:
    """Ein PERFORM mit eigener Schleife (UNTIL/VARYING/TIMES) ist eine Iteration, kein einfacher Aufruf."""
    kind = _edge_kind(edge)
    if kind == "call" and isinstance((edge.meta_json or {}).get("loop"), dict):
        return "iteration"
    return kind


def _condition_text(meta: dict) -> str | None:
    """Lesbare Bedingung einer Kante; nie eine Liste (COBOL-`control_context`), das Schema erwartet Text."""
    condition = meta.get("condition")
    if isinstance(condition, str):
        return condition
    context = meta.get("control_context")
    return context if isinstance(context, str) else None


def _node_kind(entity: CodeEntity, root: CodeEntity) -> str:
    if entity.id == root.id:
        return "entry"
    if _language(entity).lower() == "cobol" and entity.type in {
        "sql_block",
        "sql_table",
        "file_fd",
        "data_item",
    }:
        return "data_access"
    if _language(entity).lower() == "jcl" and entity.type == "jcl_dataset":
        return "data_access"
    return "step"


def _is_simple_getter(entity: CodeEntity | None) -> bool:
    """Gibt nur ein Feld zurück. Ohne bekanntes Ziel zählt der Name; eine `getX()` mit Logik bleibt ein Schritt."""
    if entity is None:
        return True
    if entity.start_line is None or entity.end_line is None:
        return True
    returns = (entity.meta_json or {}).get("return_expressions")
    if returns:
        if len(returns) != 1 or not _FIELD_EXPRESSION.fullmatch(returns[0].get("expression") or ""):
            return False
        return entity.end_line - entity.start_line < _ACCESSOR_MAX_LINES
    return entity.end_line - entity.start_line < _ABSTRACT_MAX_LINES


def _helper_role(edge: CodeEdge, target: CodeEntity | None) -> str | None:
    if edge.type != "CALLS":
        return None
    meta = edge.meta_json or {}
    receiver = meta.get("receiver") or ""
    if receiver.casefold() in _LOGGER_RECEIVERS:
        return "logging"
    if receiver in _UTILITY_RECEIVERS:
        return "utility"
    if (
        meta.get("argument_count") == 0
        and _GETTER_NAME.fullmatch(meta.get("method_name") or "")
        and _is_simple_getter(target)
    ):
        return "accessor"
    return None


def _member_role(entity: CodeEntity) -> str | None:
    meta = entity.meta_json or {}
    if (
        entity.type == "method"
        and not meta.get("parameter_types")
        and _GETTER_NAME.fullmatch(entity.name or "")
        and _is_simple_getter(entity)
    ):
        return "accessor"
    return None


def _add_entry_routines(
    db: Session, root: CodeEntity, projection: ProcessProjection, limit: int
) -> None:
    """Zeigt die Methoden und inneren Typen als Einstiege; hat eine Datei nur einen Typ, gleich dessen."""
    if root.type not in _ENTRY_LIST_ROOTS:
        return
    same_unit = (
        CodeEntity.project_id == root.project_id,
        CodeEntity.source_id == root.source_id,
        CodeEntity.variant_key == root.variant_key,
        CodeEntity.file_path == root.file_path,
    )
    parent_id = root.id
    members: list[CodeEntity] | None = None
    if root.type == "compilation_unit":
        types = (
            db.query(CodeEntity)
            .filter(*same_unit, CodeEntity.type.in_(JAVA.containers))
            .order_by(CodeEntity.start_line, CodeEntity.id)
            .all()
        )
        known = {item.id for item in types}
        outer = [item for item in types if item.parent_id not in known]
        if len(outer) == 1:
            parent_id = outer[0].id
        else:
            members = outer
    if members is None:
        members = (
            db.query(CodeEntity)
            .filter(
                *same_unit, CodeEntity.parent_id == parent_id, CodeEntity.type.in_(_MEMBER_TYPES)
            )
            .order_by(CodeEntity.start_line, CodeEntity.id)
            .limit(limit + 1)
            .all()
        )
    if len(members) > limit:
        projection.truncation.truncated = True
        projection.truncation.reasons = sorted({*projection.truncation.reasons, "node_limit"})
        projection.truncation.omitted_node_count += len(members) - limit
        members = members[:limit]

    known_nodes = {node.id for node in projection.nodes}
    for member in members:
        node_id = _node_id(member.id)
        locator = _entity_locator(member)
        if node_id not in known_nodes:
            projection.nodes.append(
                ProcessNode(
                    id=node_id,
                    kind=_node_kind(member, root),
                    label=_node_label(member),
                    language=_language(member),
                    locator=locator,
                    entity_id=member.id,
                )
            )
        role = _member_role(member)
        projection.transitions.append(
            ProcessTransition(
                id=f"member:{member.id}",
                source=projection.root_node_id,
                target=node_id,
                kind="step",
                certainty="certain",
                resolution="resolved",
                locator=locator,
                origin_kind="synthetic",
                meta={"helper": role} if role else {},
            )
        )


def _add_fall_through(db: Session, routine: CodeEntity, projection: ProcessProjection) -> None:
    """Der nächste Paragraph, falls der Lauf dorthin weiterläuft. Ob es dazu kommt, entscheidet der Weg
    hinein: Nach PERFORM kehrt der Lauf zurück. Das weiß nur, wer den Ablauf zusammensetzt."""
    following = (routine.meta_json or {}).get("falls_through")
    if not following:
        return
    target = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.project_id == routine.project_id,
            CodeEntity.source_id == routine.source_id,
            CodeEntity.variant_key == routine.variant_key,
            CodeEntity.file_path == routine.file_path,
            CodeEntity.qualified_name == following["paragraph"],
        )
        .first()
    )
    if target is None:
        return
    node_id = _node_id(target.id)
    locator = _entity_locator(target)
    if all(node.id != node_id for node in projection.nodes):
        projection.nodes.append(
            ProcessNode(
                id=node_id,
                kind=_node_kind(target, routine),
                label=_node_label(target),
                language=_language(target),
                locator=locator,
                entity_id=target.id,
            )
        )
    projection.transitions.append(
        ProcessTransition(
            id=f"fall-through:{routine.id}",
            source=_node_id(routine.id),
            target=node_id,
            kind="step",
            certainty="certain" if following.get("certain") else "possible",
            resolution="resolved",
            locator=locator,
            origin_kind="synthetic",
            meta={"fall_through": True},
        )
    )


def _argument_count(signature: str) -> int:
    """Parameter einer Signatur wie ``#f(Map<A,B>,C)``; Kommas in Typargumenten zählen nicht."""
    inner = signature[signature.find("(") + 1 : signature.rfind(")")] if "(" in signature else ""
    if not inner.strip():
        return 0
    depth, count = 0, 1
    for char in inner:
        depth += {"<": 1, ">": -1}.get(char, 0)
        count += char == "," and depth == 0
    return count


def _add_implementations(
    db: Session, routine: CodeEntity, projection: ProcessProjection, limit: int
) -> None:
    """Eine Routine ohne eigenen Ablauf führt zu dem, was sie umsetzt. Welche Umsetzung läuft, entscheidet
    erst die Laufzeit, deshalb sind diese Übergänge nur möglich."""
    if role_of(routine.type) != "routine" or routine.parent_id is None:
        return
    root_id = _node_id(routine.id)
    if any(transition.source == root_id for transition in projection.transitions):
        return
    parent = db.get(CodeEntity, routine.parent_id)
    if parent is None or not parent.qualified_name:
        return

    realizers: dict[int, CodeEntity] = {}
    frontier = [parent.id]
    for _ in range(_REALIZATION_DEPTH):
        if not frontier or len(realizers) >= _MAX_REALIZERS:
            break
        rows = (
            db.query(CodeEntity)
            .join(CodeEdge, CodeEdge.src_entity_id == CodeEntity.id)
            .filter(
                CodeEdge.project_id == routine.project_id,
                CodeEdge.dst_entity_id.in_(frontier),
                CodeEdge.type.in_(sorted(REALIZATION_EDGES)),
                CodeEntity.file_path.op("!~")(TEST_PATH_PATTERN),
            )
            .limit(_MAX_REALIZERS)
            .all()
        )
        frontier = [row.id for row in rows if row.id not in realizers and row.id != parent.id]
        realizers.update({row.id: row for row in rows if row.id != parent.id})
    if not realizers:
        return

    signature = (routine.qualified_name or "")[len(parent.qualified_name) :]
    candidates: dict[int, list[CodeEntity]] = defaultdict(list)
    for candidate in db.query(CodeEntity).filter(
        CodeEntity.project_id == routine.project_id,
        CodeEntity.parent_id.in_(list(realizers)),
        CodeEntity.name == routine.name,
        CodeEntity.type == routine.type,
    ):
        candidates[candidate.parent_id].append(candidate)

    targets: list[CodeEntity] = []
    for parent_id, methods in candidates.items():
        prefix = realizers[parent_id].qualified_name or ""
        tails = [(method, (method.qualified_name or "")[len(prefix) :]) for method in methods]
        exact = [method for method, tail in tails if tail == signature]
        # Typparameter heißen in der Umsetzung oft anders; dann entscheidet die Zahl der Parameter.
        arity = _argument_count(signature)
        targets += exact or [m for m, tail in tails if _argument_count(tail) == arity]

    known = {node.id for node in projection.nodes}
    for target in targets[: limit - len(projection.nodes)]:
        node_id = _node_id(target.id)
        locator = _entity_locator(target)
        if node_id not in known:
            known.add(node_id)
            projection.nodes.append(
                ProcessNode(
                    id=node_id,
                    kind=_node_kind(target, routine),
                    label=realizers[target.parent_id].name or _node_label(target),
                    language=_language(target),
                    locator=locator,
                    entity_id=target.id,
                )
            )
        projection.transitions.append(
            ProcessTransition(
                id=f"implementation:{routine.id}:{target.id}",
                source=root_id,
                target=node_id,
                kind="call",
                certainty="possible",
                resolution="resolved",
                locator=locator,
                origin_kind="synthetic",
                meta={"implementation": True},
            )
        )


def _add_exits(
    routine: CodeEntity, transitions: list[ProcessTransition], nodes: list[ProcessNode]
) -> None:
    """Beendende Anweisungen stehen in `meta.exits` der Routine; sie haben kein eigenes Ziel im Index."""
    for item in (routine.meta_json or {}).get("exits") or []:
        node_id = f"end:{routine.id}:{item['line']}"
        locator = ProcessLocator(
            source_id=routine.source_id, file_path=routine.file_path, start_line=item["line"]
        )
        nodes.append(
            ProcessNode(
                id=node_id,
                kind="exit",
                label=item["statement"],
                language=_language(routine),
                locator=locator,
            )
        )
        transitions.append(
            ProcessTransition(
                id=f"exit:{routine.id}:{item['line']}",
                source=_node_id(routine.id),
                target=node_id,
                kind="exit",
                certainty="certain",
                resolution="resolved",
                locator=locator,
                origin_kind="synthetic",
                meta={"control_path": item["control_path"]} if item.get("control_path") else {},
            )
        )


def _node_label(entity: CodeEntity) -> str:
    """Ein Block heißt nach seiner Anweisung (`CICS READ USRSEC`), nicht nach seiner Zeile."""
    if entity.type not in EMBEDDED_BLOCK_TYPES:
        return entity.name
    meta = entity.meta_json or {}
    if entity.type == "sql_block":
        words = [
            "SQL",
            meta.get("statement_type"),
            *(meta.get("tables") or [])[:_MAX_LABEL_RESOURCES],
        ]
    else:
        words = [
            meta.get("dialect"),
            meta.get("operation"),
            *(meta.get("resources") or [])[:_MAX_LABEL_RESOURCES],
        ]
    return " ".join(word for word in words if word) or entity.name


def _certainty(edge: CodeEdge, source: CodeEntity) -> str:
    if edge.resolution == "dynamic":
        return "possible"
    if edge.resolution != "resolved":
        return "unresolved"
    if (edge.meta_json or {}).get("control_role") in {"exception_handler", "cleanup"}:
        return "possible"
    if (edge.meta_json or {}).get("access_certainty") == "possible":
        return "possible"
    # Java's resolver can identify the statically declared method, but a
    # virtual call may dispatch to an implementation that is not knowable from
    # this repository snapshot. Do not present that declaration as certain.
    if (
        _language(source).lower() == "java"
        and edge.type == "CALLS"
        and (edge.meta_json or {}).get("invocation_kind") == "virtual"
    ):
        return "possible"
    return "certain"


def _annotate_semantics(transitions: list[ProcessTransition]) -> None:
    """Expose ambiguity and cycles without manufacturing a traversal order."""
    goto_groups: dict[tuple[str, str, int], list[ProcessTransition]] = defaultdict(list)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for transition in transitions:
        adjacency[transition.source].add(transition.target)
        if transition.code_edge_types == ["GOTO"]:
            goto_groups[
                (transition.source, transition.locator.file_path, transition.locator.start_line)
            ].append(transition)

    for group in goto_groups.values():
        if len({transition.target for transition in group}) < 2:
            continue
        for transition in group:
            transition.kind = "branch"
            if transition.certainty == "certain":
                transition.certainty = "possible"
            transition.meta["multiple_targets"] = True

    def reaches(start: str, destination: str) -> bool:
        pending = deque([start])
        visited: set[str] = set()
        while pending:
            current = pending.popleft()
            if current == destination:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency[current] - visited)
        return False

    for transition in transitions:
        if transition.source == transition.target:
            transition.meta["cycle"] = True
            transition.meta["recursion"] = True
        elif reaches(transition.target, transition.source):
            transition.meta["cycle"] = True


def _requested_kinds(kinds: list[str] | None) -> set[str]:
    requested = {
        item.strip().lower() for raw in kinds or [] for item in raw.split(",") if item.strip()
    }
    unknown = requested - KNOWN_PROCESS_KINDS
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unbekannte Prozessarten: {', '.join(sorted(unknown))}"
        )
    return requested or set(KNOWN_PROCESS_KINDS)


def _projection(
    db: Session,
    root: CodeEntity,
    direction: str,
    hops: int,
    node_limit: int,
    edge_limit: int,
    requested_kinds: set[str],
) -> ProcessProjection:
    entities: dict[int, CodeEntity] = {root.id: root}
    source_cache: dict[int, KnowledgeSource | None] = {}

    def provenance_for(
        entity: CodeEntity,
        start_line: int,
        end_line: int | None,
        *,
        certainty: str | None = None,
        origin: str | None = None,
    ) -> dict:
        source_id = entity.source_id
        if source_id is not None and source_id not in source_cache:
            source_cache[source_id] = (
                db.query(KnowledgeSource)
                .filter(
                    KnowledgeSource.id == source_id,
                    KnowledgeSource.project_id == entity.project_id,
                )
                .first()
            )
        source = source_cache.get(source_id) if source_id is not None else None
        return build_provenance(
            source,
            kind="code_fact" if source else "unknown",
            verification_status="indexed_unreviewed" if source else "unavailable",
            detail=(
                "Automatisch aus dem Codeindex abgeleitet; eine fachliche Freigabe ist nicht hinterlegt."
                if source
                else "Quellenmetadaten sind für diesen Codebeleg nicht verfügbar."
            ),
            locator={"file_path": entity.file_path, "start_line": start_line, "end_line": end_line},
            certainty=certainty,
            origin=origin,
        )

    frontier = {root.id}
    walked: set[int] = set()
    transitions: list[ProcessTransition] = []
    seen_edge_ids: set[int] = set()
    reasons: set[str] = set()
    omitted_nodes = 0
    omitted_transitions = 0
    # "iteration" ist eine abgeleitete Art (call-Kante mit Schleife, siehe _transition_kind):
    # die Vorauswahl muss dafuer die call-Kanten laden, der Feinfilter folgt je Zeile.
    query_kinds = requested_kinds | ({"call"} if "iteration" in requested_kinds else set())
    process_edge_types = [edge_type for edge_type, kind in EDGE_KIND.items() if kind in query_kinds]
    if "external_call" in requested_kinds:
        process_edge_types.extend(["CALL", "CALLS", "PERFORM"])

    for _ in range(hops):
        if not frontier:
            break
        if len(transitions) >= edge_limit:
            reasons.add("edge_limit")
            break
        relation_filters = []
        if direction in {"outgoing", "both"}:
            relation_filters.append(CodeEdge.src_entity_id.in_(frontier))
        if direction in {"incoming", "both"}:
            relation_filters.append(CodeEdge.dst_entity_id.in_(frontier))
        query = db.query(CodeEdge).filter(
            CodeEdge.type.in_(process_edge_types), or_(*relation_filters)
        )
        if root.project_id is not None:
            query = query.filter(CodeEdge.project_id == root.project_id)
        rows = query.order_by(CodeEdge.id).limit(edge_limit - len(transitions) + 1).all()
        if len(rows) > edge_limit - len(transitions):
            reasons.add("edge_limit")
            omitted_transitions += len(rows) - (edge_limit - len(transitions))
            rows = rows[: edge_limit - len(transitions)]

        # Ein Programmwechsel im Block gehört direkt in den Ablauf des Paragraphen: Er übernimmt dessen
        # Bedingung und kostet keinen eigenen Schritt.
        block_ids = {
            edge.dst_entity_id
            for edge in rows
            if edge.type == "CONTAINS"
            and edge.dst_entity_id is not None
            and edge.src_entity_id in frontier
            and direction != "incoming"
        }
        blocks = (
            {
                entity.id: entity
                for entity in db.query(CodeEntity).filter(
                    CodeEntity.id.in_(block_ids), CodeEntity.type.in_(EMBEDDED_BLOCK_TYPES)
                )
            }
            if block_ids
            else {}
        )
        block_calls: dict[int, list[CodeEdge]] = defaultdict(list)
        if blocks:
            for call in (
                db.query(CodeEdge)
                .filter(CodeEdge.src_entity_id.in_(blocks), CodeEdge.type == "CALL")
                .order_by(CodeEdge.id)
            ):
                block_calls[call.src_entity_id].append(call)

        steps: list[tuple[CodeEdge, int, CodeEdge | None]] = []
        for edge in rows:
            calls = block_calls.get(edge.dst_entity_id) if edge.type == "CONTAINS" else None
            if calls and edge.src_entity_id in frontier:
                steps.extend((call, edge.src_entity_id, edge) for call in calls)
            else:
                steps.append((edge, edge.src_entity_id, None))

        next_frontier: set[int] = set()
        for edge, source_id, enclosing in steps:
            if edge.id in seen_edge_ids:
                continue
            base_kind = _edge_kind(edge)
            kind = _transition_kind(edge)
            if base_kind not in requested_kinds and kind not in requested_kinds:
                continue
            block = blocks.get(edge.dst_entity_id) if edge.type == "CONTAINS" else None
            if block is not None:
                exits = (block.meta_json or {}).get("operation") in EXIT_OPERATIONS
                kind = "exit" if exits else "step"
            source = entities.get(source_id)
            if source is None:
                source = db.query(CodeEntity).filter(CodeEntity.id == source_id).first()
                if source is None:
                    continue
            # Die Operation steckt schon in der Bezeichnung des Blocks.
            if source.type in EMBEDDED_BLOCK_TYPES and edge.type == "EXECUTES":
                continue
            if source.id not in entities:
                if len(entities) >= node_limit:
                    reasons.add("node_limit")
                    omitted_nodes += 1
                    omitted_transitions += 1
                    continue
                entities[source.id] = source

            target = None
            if edge.dst_entity_id is None:
                if (
                    len(entities)
                    + sum(item.target.startswith("external:edge:") for item in transitions)
                    >= node_limit
                ):
                    reasons.add("node_limit")
                    omitted_nodes += 1
                    omitted_transitions += 1
                    continue
                target_id = f"external:edge:{edge.id}"
            else:
                target = entities.get(edge.dst_entity_id)
                if target is None:
                    target = (
                        db.query(CodeEntity).filter(CodeEntity.id == edge.dst_entity_id).first()
                    )
                    if target is None:
                        continue
                    if len(entities) >= node_limit:
                        reasons.add("node_limit")
                        omitted_nodes += 1
                        omitted_transitions += 1
                        continue
                    entities[target.id] = target
                target_id = _node_id(target.id)
                if direction in {"outgoing", "both"} and target.id not in frontier:
                    next_frontier.add(target.id)
                if direction in {"incoming", "both"} and source.id not in frontier:
                    next_frontier.add(source.id)

            transitions.append(
                ProcessTransition(
                    id=f"code-edge:{edge.id}",
                    source=_node_id(source.id),
                    target=target_id,
                    kind=kind,
                    certainty=_certainty(edge, source),
                    resolution=edge.resolution,
                    locator=_edge_locator(
                        edge,
                        source,
                        provenance_for(
                            source,
                            edge.src_start_line
                            if edge.src_start_line >= 1
                            else source.start_line or 1,
                            edge.src_end_line if edge.src_end_line >= 1 else None,
                            certainty=_certainty(edge, source),
                            origin=edge.type,
                        ),
                    ),
                    origin_kind="code_edge",
                    code_edge_ids=[edge.id],
                    code_edge_types=[edge.type],
                    sequence=(edge.meta_json or {}).get("sequence")
                    if isinstance((edge.meta_json or {}).get("sequence"), int)
                    else None,
                    condition=_condition_text(edge.meta_json or {}),
                    meta={
                        key: value
                        for key, value in {
                            **(edge.meta_json or {}),
                            **(
                                {"control_path": (enclosing.meta_json or {}).get("control_path")}
                                if enclosing is not None
                                else {}
                            ),
                        }.items()
                        if value is not None
                        and key
                        in {
                            "candidate_targets",
                            "thru",
                            "thru_resolution",
                            "thru_target_qualified_name",
                            "statement_type",
                            "cursor_name",
                            "invocation_kind",
                            "dispatch_scope",
                            "resolution_reason",
                            "control_role",
                            "control_context",
                            "exception_types",
                            "control_path",
                            "loop",
                        }
                    },
                )
            )
            helper = _helper_role(edge, target)
            if helper:
                transitions[-1].meta["helper"] = helper
            seen_edge_ids.add(edge.id)
        walked |= frontier
        frontier = next_frontier

    _annotate_semantics(transitions)

    nodes: list[ProcessNode] = []
    for entity in entities.values():
        nodes.append(
            ProcessNode(
                id=_node_id(entity.id),
                kind=_node_kind(entity, root),
                label=_node_label(entity),
                language=_language(entity),
                locator=_entity_locator(
                    entity,
                    provenance_for(
                        entity, entity.start_line or 1, entity.end_line, origin="CodeEntity"
                    ),
                ),
                entity_id=entity.id,
            )
        )
    # Unresolved nodes use the transition locator; their target has no own file.
    unresolved = [
        transition for transition in transitions if transition.target.startswith("external:edge:")
    ]
    for transition in unresolved:
        edge_id = transition.code_edge_ids[0]
        edge = db.query(CodeEdge).filter(CodeEdge.id == edge_id).first()
        nodes.append(
            ProcessNode(
                id=transition.target,
                kind=transition.kind,
                label=edge.dst_name if edge else "unresolved target",
                language=next(node.language for node in nodes if node.id == transition.source),
                locator=transition.locator,
            )
        )

    if direction != "incoming" and "exit" in requested_kinds:
        for entity_id in walked:
            _add_exits(entities[entity_id], transitions, nodes)

    identity = "|".join(
        [str(root.project_id), str(root.id), direction, str(hops), str(node_limit), str(edge_limit)]
        + sorted(requested_kinds)
        + [transition.id for transition in transitions]
    )
    return ProcessProjection(
        projection_id=f"process:{sha256(identity.encode()).hexdigest()[:20]}",
        project_id=root.project_id,
        root_node_id=_node_id(root.id),
        direction=direction,
        hops=hops,
        nodes=nodes,
        transitions=transitions,
        truncation=ProcessTruncation(
            truncated=bool(reasons),
            node_limit=node_limit,
            edge_limit=edge_limit,
            omitted_node_count=omitted_nodes,
            omitted_transition_count=omitted_transitions,
            reasons=sorted(reasons),
        ),
    )


@router.get("/shared-data")
def process_shared_data(
    entity_id: int,
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Dateien und Tabellen des fokussierten Programms oder Jobs und wer sie sonst noch nutzt."""
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return shared_data(db, entity)


@router.get("/focus", response_model=ProcessProjection)
def focus_process(
    entity_id: int,
    project_id: int | None = Query(default=None),
    direction: str = Query(default="outgoing", pattern="^(outgoing|incoming|both)$"),
    hops: int = Query(default=1, ge=0, le=5),
    node_limit: int = Query(default=200, ge=1, le=MAX_NODE_LIMIT),
    edge_limit: int = Query(default=400, ge=1, le=MAX_EDGE_LIMIT),
    kinds: list[str] | None = Query(default=None),
    flow_view: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    root = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if root is None:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(root, user, db, project_id)
    if direction == "outgoing" and root.type in {"program", "cobol_program"}:
        root = cobol_entry_paragraph(db, root) or root
    projection = _projection(
        db, root, direction, hops, node_limit, edge_limit, _requested_kinds(kinds)
    )
    if flow_view:
        _add_entry_routines(db, root, projection, node_limit)
        _add_fall_through(db, root, projection)
        _add_implementations(db, root, projection, node_limit)
    return projection
