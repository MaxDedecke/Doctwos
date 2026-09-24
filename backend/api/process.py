"""Bounded, evidence-backed Process View projection (O-292)."""

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
from models.database import CodeEdge, CodeEntity, KnowledgeSource, User
from services.provenance import build_provenance

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
    "USES_RESOURCE": "data_access",
    "TRANSFORMS_WITH": "data_access",
}
KNOWN_PROCESS_KINDS = frozenset(set(EDGE_KIND.values()) | {"external_call"})


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


def _edge_locator(edge: CodeEdge, source: CodeEntity, provenance: dict | None = None) -> ProcessLocator:
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


def _node_kind(entity: CodeEntity, root: CodeEntity) -> str:
    if entity.id == root.id:
        return "entry"
    if _language(entity).lower() == "cobol" and entity.type in {
        "sql_block", "sql_table", "file_fd", "data_item",
    }:
        return "data_access"
    if _language(entity).lower() == "jcl" and entity.type == "jcl_dataset":
        return "data_access"
    return "step"


def _certainty(edge: CodeEdge, source: CodeEntity) -> str:
    if edge.resolution == "dynamic":
        return "possible"
    if edge.resolution != "resolved":
        return "unresolved"
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
    requested = {item.strip().lower() for raw in kinds or [] for item in raw.split(",") if item.strip()}
    unknown = requested - KNOWN_PROCESS_KINDS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unbekannte Prozessarten: {', '.join(sorted(unknown))}")
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

    def provenance_for(entity: CodeEntity, start_line: int, end_line: int | None, *, certainty: str | None = None, origin: str | None = None) -> dict:
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
                if source else "Quellenmetadaten sind für diesen Codebeleg nicht verfügbar."
            ),
            locator={"file_path": entity.file_path, "start_line": start_line, "end_line": end_line},
            certainty=certainty,
            origin=origin,
        )

    frontier = {root.id}
    transitions: list[ProcessTransition] = []
    seen_edge_ids: set[int] = set()
    reasons: set[str] = set()
    omitted_nodes = 0
    omitted_transitions = 0
    process_edge_types = [edge_type for edge_type, kind in EDGE_KIND.items() if kind in requested_kinds]
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

        next_frontier: set[int] = set()
        for edge in rows:
            if edge.id in seen_edge_ids:
                continue
            kind = _edge_kind(edge)
            if kind not in requested_kinds:
                continue
            source = entities.get(edge.src_entity_id)
            if source is None:
                source = db.query(CodeEntity).filter(CodeEntity.id == edge.src_entity_id).first()
                if source is None:
                    continue
                if len(entities) >= node_limit:
                    reasons.add("node_limit")
                    omitted_nodes += 1
                    omitted_transitions += 1
                    continue
                entities[source.id] = source

            if edge.dst_entity_id is None:
                if len(entities) + sum(
                    item.target.startswith("external:edge:") for item in transitions
                ) >= node_limit:
                    reasons.add("node_limit")
                    omitted_nodes += 1
                    omitted_transitions += 1
                    continue
                target_id = f"external:edge:{edge.id}"
            else:
                target = entities.get(edge.dst_entity_id)
                if target is None:
                    target = db.query(CodeEntity).filter(CodeEntity.id == edge.dst_entity_id).first()
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
                            edge.src_start_line if edge.src_start_line >= 1 else source.start_line or 1,
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
                    condition=(edge.meta_json or {}).get("condition")
                    if isinstance((edge.meta_json or {}).get("condition"), str)
                    else None,
                    meta={
                        key: value
                        for key, value in (edge.meta_json or {}).items()
                        if key in {
                            "thru", "thru_resolution", "thru_target_qualified_name",
                            "statement_type", "cursor_name",
                            "invocation_kind", "dispatch_scope", "resolution_reason",
                        }
                    },
                )
            )
            seen_edge_ids.add(edge.id)
        frontier = next_frontier

    _annotate_semantics(transitions)

    nodes: list[ProcessNode] = []
    for entity in entities.values():
        nodes.append(
            ProcessNode(
                id=_node_id(entity.id),
                kind=_node_kind(entity, root),
                label=entity.name,
                language=_language(entity),
                locator=_entity_locator(
                    entity,
                    provenance_for(entity, entity.start_line or 1, entity.end_line, origin="CodeEntity"),
                ),
                entity_id=entity.id,
            )
        )
    # Unresolved nodes use the transition locator; their target has no own file.
    unresolved = [transition for transition in transitions if transition.target.startswith("external:edge:")]
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

    identity = "|".join(
        [str(root.project_id), str(root.id), direction, str(hops), str(node_limit), str(edge_limit)]
        + sorted(requested_kinds)
        + [str(transition.code_edge_ids[0]) for transition in transitions]
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


@router.get("/focus", response_model=ProcessProjection)
def focus_process(
    entity_id: int,
    project_id: int | None = Query(default=None),
    direction: str = Query(default="outgoing", pattern="^(outgoing|incoming|both)$"),
    hops: int = Query(default=1, ge=0, le=5),
    node_limit: int = Query(default=200, ge=1, le=MAX_NODE_LIMIT),
    edge_limit: int = Query(default=400, ge=1, le=MAX_EDGE_LIMIT),
    kinds: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    root = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if root is None:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(root, user, db, project_id)
    return _projection(
        db, root, direction, hops, node_limit, edge_limit, _requested_kinds(kinds)
    )
