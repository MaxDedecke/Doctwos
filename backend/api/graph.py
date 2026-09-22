"""
backend/api/graph.py
======================
Knowledge Graph: Visualization of relationships between code objects and documentation.

This module provides routes to prepare the networked data of the Doctus system as
graphs (nodes and edges) for frontend visualization (Force-Graph, Mermaid).

Endpoints:
    GET /graph              — Full graph of a project (entities + documents),
                              capped at KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES
                              nodes (O-053; highest-degree nodes kept first)
    GET /graph/focus        — 1-hop neighborhood of an entity (local focus),
                              wired up in the frontend since O-053 as the way
                              to explore a capped/truncated overview further
    GET /graph/export/neo4j — Cypher export for external graph databases (Neo4j)
    GET /graph/export       — Neutral CSV/GraphML export (analogous to /callgraph/export)
"""

import csv
import io
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from core import config as cfg
from core.db_setup import get_db
from models.database import (
    CodeEdge,
    CodeEntity,
    EntityDocLink,
    KnowledgeLink,
    Project,
    User,
    KnowledgeSource,
    DocumentChunk,
)
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids, assert_team_visible
from core.projects import (
    assert_project_visible,
    get_globally_exposed_project_ids,
    get_visible_project_ids,
    is_document_chunk_code_visible_in_context,
    is_project_code_visible_in_context,
)

router = APIRouter(prefix="/graph", tags=["graph"])


def _entity_node(entity: CodeEntity) -> dict:
    """Converts a CodeEntity instance into the graph node format for the frontend."""
    return {
        "id": f"entity:{entity.id}",
        "type": "entity",
        "label": entity.name,
        "entity_type": entity.type,
        "file_path": entity.file_path,
        "start_line": entity.start_line,
        "project_id": entity.project_id,
        "source_type": None,
        "url": None,
        "qualified_name": entity.qualified_name,
        "source_id": entity.source_id,
        "variant_key": entity.variant_key,
        "evidence": (entity.meta_json or {}).get("evidence"),
    }


def _doc_node(
    title: str,
    source_type: Optional[str],
    url: Optional[str],
    chunk: Optional[DocumentChunk] = None,
) -> dict:
    """Creates a graph node format for an external knowledge document.

    `chunk` carries the metadata_json und den echten file_path (der `#<suffix>`-Teil
    des storage_key wird hier abgeschnitten), damit das Frontend die Datei öffnen kann.
    """
    meta = (chunk.metadata_json or {}) if chunk else {}
    file_path = chunk.file_path.split("#")[0] if (chunk and chunk.file_path) else None
    return {
        "id": f"doc:{title}",
        "type": "document",
        "label": title,
        "source_type": source_type,
        "url": url,
        "entity_type": meta.get("element_type"),
        "file_path": file_path,
        "start_line": None,
        "source_id": chunk.source_id if chunk else None,
    }


def _document_locator(chunk: Optional[DocumentChunk], document_url: Optional[str]) -> dict:
    """Serialize the exact evidence location carried by an EntityDocLink."""
    if not chunk:
        return {
            "chunk_id": None,
            "document_file_path": None,
            "document_source_id": None,
            "document_start_line": None,
            "document_end_line": None,
            "document_page": None,
            "document_section": None,
            "document_url_anchor": None,
            "document_url": document_url,
        }
    metadata = chunk.metadata_json if isinstance(chunk.metadata_json, dict) else {}
    return {
        "chunk_id": chunk.id,
        "document_file_path": chunk.file_path,
        "document_source_id": chunk.source_id,
        "document_start_line": chunk.start_line,
        "document_end_line": chunk.end_line,
        "document_page": metadata.get("page"),
        "document_section": metadata.get("section"),
        "document_url_anchor": metadata.get("url_anchor") or metadata.get("anchor"),
        "document_url": document_url or metadata.get("url"),
    }


def _append_code_dependencies(
    nodes: dict[str, dict], edges: list[dict], code_edges: list[CodeEdge], entities: dict[int, CodeEntity]
) -> None:
    """Add a type-neutral, deduplicated code relationship projection.

    Code relationships retain their persisted direction.  The overview may still
    be capped, but callers must never have to infer upstream/downstream from a
    lossy, undirected projection (O-270).
    """
    for code_edge in code_edges:
        source_entity = entities.get(code_edge.src_entity_id)
        if not source_entity:
            continue
        source_id = f"entity:{source_entity.id}"
        nodes.setdefault(source_id, _entity_node(source_entity))

        target_entity = entities.get(code_edge.dst_entity_id) if code_edge.dst_entity_id else None
        if target_entity:
            target_id = f"entity:{target_entity.id}"
            nodes.setdefault(target_id, _entity_node(target_entity))
        else:
            target_id = f"unresolved:code:{code_edge.dst_name}"
            nodes.setdefault(
                target_id,
                {
                    "id": target_id,
                    "type": "external",
                    "label": code_edge.dst_name,
                    "entity_type": None,
                    "file_path": None,
                    "start_line": None,
                    "project_id": code_edge.project_id,
                    "source_type": None,
                    "url": None,
                    "source_id": code_edge.source_id,
                    "unresolved": True,
                },
            )

        edges.append(
            {
            "id": f"code-dependency:{code_edge.id}",
            "source": source_id,
            "target": target_id,
            "link_type": "code_dependency",
            "relation_type": "code_dependency",
            "direction": "directed",
            "score": None,
            "context": None,
            "meta": {"edge_count": 1, "edge_types": [code_edge.type]},
            }
        )


def _traverse_code_dependencies(
    db: Session,
    *,
    root_id: int,
    project_id: int | None,
    direction: str,
    hops: int,
    limit: int,
) -> tuple[list[CodeEdge], bool]:
    """Return a bounded BFS over persisted directed CodeEdges.

    A visited node set makes cycles explicit in the returned edge set while
    ensuring a cycle cannot consume the hop/edge budget indefinitely.
    """
    frontier = {root_id}
    visited_nodes = {root_id}
    seen_edges: set[int] = set()
    result: list[CodeEdge] = []
    has_more = False
    for _ in range(hops):
        if not frontier or len(result) >= limit:
            has_more = bool(frontier)
            break
        clauses = []
        if direction in {"outgoing", "both"}:
            clauses.append(CodeEdge.src_entity_id.in_(frontier))
        if direction in {"incoming", "both"}:
            clauses.append(CodeEdge.dst_entity_id.in_(frontier))
        query = db.query(CodeEdge).filter(or_(*clauses))
        if project_id is not None:
            query = query.filter(CodeEdge.project_id == project_id)
        rows = query.order_by(CodeEdge.id).limit(limit - len(result) + 1).all()
        if len(rows) > limit - len(result):
            has_more = True
            rows = rows[: limit - len(result)]
        next_frontier: set[int] = set()
        for edge in rows:
            if edge.id in seen_edges:
                continue
            seen_edges.add(edge.id)
            result.append(edge)
            for node_id in (edge.src_entity_id, edge.dst_entity_id):
                if node_id is not None and node_id not in visited_nodes:
                    visited_nodes.add(node_id)
                    next_frontier.add(node_id)
        frontier = next_frontier
    return result, has_more


def _is_project_visible(
    project_id: Optional[int],
    team_ids: Optional[list[int]],
    project_ids: Optional[list[int]],
    db: Session,
) -> bool:
    if project_id is None:
        return True
    if team_ids is None:
        return True
    proj = db.query(Project).filter(Project.id == project_id).first()
    return proj is not None and proj.team_id in team_ids and project_id in (project_ids or [])


def _is_source_visible(
    source_id: Optional[int],
    team_ids: Optional[list[int]],
    project_ids: Optional[list[int]],
    db: Session,
) -> bool:
    if source_id is None:
        return True
    if team_ids is None:
        return True
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    return (
        source is not None
        and source.team_id in team_ids
        and (source.project_id is None or source.project_id in (project_ids or []))
    )


def _side_node_id(
    nodes: dict,
    db: Session,
    side_type: str,
    entity_id: Optional[int],
    chunk_id: Optional[int],
    title: str,
    source_type: Optional[str],
    url: Optional[str],
) -> Optional[str]:
    """Resolves one side of a generic KnowledgeLink ('entity' | 'document') into a graph node,
    inserting it into `nodes` if not already present, and returns its node id."""
    if side_type == "entity" and entity_id is not None:
        entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not entity:
            return None
        nid = f"entity:{entity.id}"
        nodes.setdefault(nid, _entity_node(entity))
        return nid
    chunk = (
        db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first() if chunk_id else None
    )
    nid = f"doc:{title}"
    nodes.setdefault(nid, _doc_node(title, source_type, url, chunk))
    return nid


def _is_side_visible(
    source_type: str,
    entity_id: Optional[int],
    chunk_id: Optional[int],
    team_ids: Optional[list[int]],
    project_ids: Optional[list[int]],
    db: Session,
    requesting_project_id: Optional[int] = None,
) -> bool:
    if source_type == "entity" and entity_id is not None:
        ent = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not ent:
            return False
        if requesting_project_id is not None and ent.project_id is not None and ent.project_id != requesting_project_id:
            return False
        # Team-Sichtbarkeit ist die Basis; Code-Analyse-Objekte (Entities) brauchen
        # außerhalb ihres eigenen Projekt-Kontexts zusätzlich das explizite Opt-in
        # expose_code_analysis_globally (siehe core/projects.py).
        return (
            _is_project_visible(ent.project_id, team_ids, project_ids, db)
            and _is_source_visible(ent.source_id, team_ids, project_ids, db)
            and is_project_code_visible_in_context(ent.project_id, requesting_project_id, db)
        )
    elif source_type == "document" and chunk_id is not None:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        if not chunk:
            return False
        # "Allgemein" zeigt nur wirklich globale Dokumente. Projektgebundene
        # PDFs/Confluence-/Jira-Chunks dürfen dort nicht über eine KnowledgeLink-
        # Kante wieder in den Graphen gelangen.
        if requesting_project_id is None and chunk.project_id is not None:
            return False
        if requesting_project_id is not None and chunk.project_id is not None and chunk.project_id != requesting_project_id:
            return False
        return (
            _is_project_visible(chunk.project_id, team_ids, project_ids, db)
            and _is_source_visible(chunk.source_id, team_ids, project_ids, db)
            and is_document_chunk_code_visible_in_context(chunk, requesting_project_id, db)
        )
    if team_ids is None:
        return True
    return True



def _sample_representative_code_edges(
    db: Session,
    project_id: Optional[int],
    exposed_project_ids: list[int],
    documented_entity_ids: set[int],
    limit: int,
) -> tuple[list[CodeEdge], bool]:
    """O-298: Repräsentative Auswahl von Code-Beziehungen statt reinem ID-Scan.

    Priorisiert:
    1. Direkte Beziehungen dokumentierter Entities (damit Doku-Links angebunden sind).
    2. Strukturelle und übergeordnete Architektur-Kanten (EXTENDS, IMPLEMENTS, CALLS,
       COPY, CALL, PERFORM, INSTANTIATES, etc.) quer über Komponenten.
    3. Allgemeine Beziehungen zur Auffüllung des verbleibenden Budgets.
    """
    base_query = db.query(CodeEdge)
    if project_id:
        base_query = base_query.filter(CodeEdge.project_id == project_id)
    else:
        if exposed_project_ids:
            base_query = base_query.filter(
                or_(CodeEdge.project_id.in_(exposed_project_ids), CodeEdge.project_id.is_(None))
            )
        else:
            base_query = base_query.filter(CodeEdge.project_id.is_(None))

    selected_edges: list[CodeEdge] = []
    seen_edge_ids: set[int] = set()

    # 1. Prioritize edges connected to documented entities
    if documented_entity_ids:
      doc_edges = (
          base_query.filter(
              or_(
                  CodeEdge.src_entity_id.in_(documented_entity_ids),
                  CodeEdge.dst_entity_id.in_(documented_entity_ids),
              )
          )
          .order_by(CodeEdge.id)
          .limit(min(limit, 500))
          .all()
      )
      for edge in doc_edges:
        if edge.id not in seen_edge_ids:
          seen_edge_ids.add(edge.id)
          selected_edges.append(edge)

    # 2. Structural/architectural relationship types
    structural_types = [
        "EXTENDS",
        "IMPLEMENTS",
        "DEPENDS_ON",
        "CONTAINS_MODULE",
        "DECLARES_SOURCE_ROOT",
        "CALLS",
        "COPY",
        "CALL",
        "PERFORM",
        "INSTANTIATES",
    ]
    remaining = limit - len(selected_edges)
    if remaining > 0:
      struct_query = base_query.filter(CodeEdge.type.in_(structural_types))
      if seen_edge_ids:
        struct_query = struct_query.filter(~CodeEdge.id.in_(seen_edge_ids))
      struct_edges = (
          struct_query.order_by(CodeEdge.id).limit(remaining + 1).all()
      )
      for edge in struct_edges[:remaining]:
        if edge.id not in seen_edge_ids:
          seen_edge_ids.add(edge.id)
          selected_edges.append(edge)

    # 3. Fill with general edges if quota remains
    remaining = limit - len(selected_edges)
    has_more = False
    if remaining > 0:
      general_query = base_query
      if seen_edge_ids:
        general_query = general_query.filter(~CodeEdge.id.in_(seen_edge_ids))
      general_edges = (
          general_query.order_by(CodeEdge.id).limit(remaining + 1).all()
      )
      if len(general_edges) > remaining:
        has_more = True
      for edge in general_edges[:remaining]:
        if edge.id not in seen_edge_ids:
          seen_edge_ids.add(edge.id)
          selected_edges.append(edge)
    else:
      check_more = base_query.filter(~CodeEdge.id.in_(seen_edge_ids)).first()
      has_more = check_more is not None

    return selected_edges, has_more


@router.get("")
def get_graph(
    project_id: Optional[int] = None,
    status: str = "approved",
    include_isolated: bool = Query(
        False, description="Whether to include degree-0 isolated nodes in the graph overview"
    ),
    limit: Optional[int] = Query(None, description="Optional custom node cap for the overview"),
    cursor: Optional[str] = Query(None, description="Optional cursor for overview pagination"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns the global knowledge graph.
    Nodes are either code entities or document chunks.
    Code edges are projected as type-neutral dependencies. Documentation edges keep
    their semantic link type and evidence location.
    """
    if not isinstance(limit, int):
        limit = None
    if not isinstance(cursor, str):
        cursor = None
    if not isinstance(include_isolated, bool):
        include_isolated = False
    if not isinstance(status, str):
        status = "approved"

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    visible_project_ids = get_visible_project_ids(user, db)

    # Validate project visibility
    if project_id:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
        assert_project_visible(project_id, user, db)

    team_ids = get_visible_team_ids(user, db)

    exposed_project_ids: list[int] = []
    if not project_id:
        exposed_project_ids = get_globally_exposed_project_ids(db)
        if visible_project_ids is not None:
            exposed_project_ids = [pid for pid in exposed_project_ids if pid in visible_project_ids]

    if include_isolated:
        entity_query = db.query(CodeEntity)
        if project_id:
            entity_query = entity_query.filter(CodeEntity.project_id == project_id)
        else:
            entity_query = entity_query.filter(
                or_(CodeEntity.project_id.in_(exposed_project_ids), CodeEntity.project_id.is_(None))
            )
        for entity in entity_query.order_by(CodeEntity.id).all():
            nodes[f"entity:{entity.id}"] = _entity_node(entity)

        doc_query = db.query(DocumentChunk)
        if project_id:
            doc_query = doc_query.filter(DocumentChunk.project_id == project_id)
        else:
            doc_query = doc_query.filter(DocumentChunk.project_id.is_(None))

        min_ids_subquery = (
            doc_query.with_entities(func.min(DocumentChunk.id))
            .group_by(DocumentChunk.file_path)
            .subquery()
        )
        distinct_docs = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.id.in_(min_ids_subquery))
            .order_by(DocumentChunk.id)
            .all()
        )
        for chunk in distinct_docs:
            meta = chunk.metadata_json or {}
            title = meta.get("title") or chunk.file_path
            did = f"doc:{title}"
            nodes.setdefault(did, _doc_node(title, meta.get("source_type"), meta.get("url"), chunk))

    # ── Entity → Document links ──────────────────────────────────────────────
    eq = db.query(EntityDocLink).filter(EntityDocLink.status == status)
    if project_id:
        eq = eq.filter(EntityDocLink.project_id == project_id)
    else:
        eq = eq.filter(EntityDocLink.project_id.in_(exposed_project_ids))
        eq = eq.filter(EntityDocLink.chunk_id.is_(None))
    entity_links = eq.all()

    preserved_node_ids: set[str] = set()
    documented_entity_ids: set[int] = set()

    if entity_links:
        documented_entity_ids = {lnk.entity_id for lnk in entity_links}
        entity_ids = {lnk.entity_id for lnk in entity_links}
        entities = {
            e.id: e for e in db.query(CodeEntity).filter(CodeEntity.id.in_(entity_ids)).all()
        }
        chunk_ids = {lnk.chunk_id for lnk in entity_links if lnk.chunk_id is not None}
        chunks = (
            {c.id: c for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()}
            if chunk_ids
            else {}
        )
        for lnk in entity_links:
            entity = entities.get(lnk.entity_id)
            if not entity:
                continue
            eid = f"entity:{entity.id}"
            nodes.setdefault(eid, _entity_node(entity))
            did = f"doc:{lnk.doc_title}"
            nodes.setdefault(
                did,
                _doc_node(lnk.doc_title, lnk.source_type, lnk.doc_url, chunks.get(lnk.chunk_id)),
            )
            preserved_node_ids.add(eid)
            preserved_node_ids.add(did)
            edges.append(
                {
                    "id": f"edl:{lnk.id}",
                    "source": eid,
                    "target": did,
                    "link_type": lnk.link_type,
                    "relation_type": "documented",
                    "direction": "directed",
                    "score": lnk.score,
                    "context": lnk.context,
                    **_document_locator(chunks.get(lnk.chunk_id), lnk.doc_url),
                }
            )

    # ── Cross-object knowledge links ─────────────────────────────────────────
    for klink in db.query(KnowledgeLink).filter(KnowledgeLink.status == status).all():
        if not (
            _is_side_visible(
                klink.source_a_type,
                klink.source_a_entity_id,
                klink.source_a_chunk_id,
                team_ids,
                visible_project_ids,
                db,
                project_id,
            )
            and _is_side_visible(
                klink.source_b_type,
                klink.source_b_entity_id,
                klink.source_b_chunk_id,
                team_ids,
                visible_project_ids,
                db,
                project_id,
            )
        ):
            continue
        src_id = _side_node_id(
            nodes,
            db,
            klink.source_a_type,
            klink.source_a_entity_id,
            klink.source_a_chunk_id,
            klink.source_a_title,
            klink.source_a_source_type,
            klink.source_a_url,
        )
        tgt_id = _side_node_id(
            nodes,
            db,
            klink.source_b_type,
            klink.source_b_entity_id,
            klink.source_b_chunk_id,
            klink.source_b_title,
            klink.source_b_source_type,
            klink.source_b_url,
        )
        if not src_id or not tgt_id:
            continue
        preserved_node_ids.add(src_id)
        preserved_node_ids.add(tgt_id)
        edges.append(
            {
                "id": f"kl:{klink.id}",
                "source": src_id,
                "target": tgt_id,
                "link_type": klink.link_type,
                "direction": getattr(klink, "direction", None) or "undirected",
                "score": klink.score,
                "context": klink.context,
            }
        )

    # ── Code dependencies (representative sampling across files & components) ─
    code_edge_limit = (limit or cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES) * 2
    sampled_code_edges, code_edges_truncated = _sample_representative_code_edges(
        db=db,
        project_id=project_id,
        exposed_project_ids=exposed_project_ids,
        documented_entity_ids=documented_entity_ids,
        limit=code_edge_limit,
    )
    code_entity_ids = {
        entity_id
        for edge in sampled_code_edges
        for entity_id in (edge.src_entity_id, edge.dst_entity_id)
        if entity_id is not None
    }
    code_entities = {
        entity.id: entity
        for entity in db.query(CodeEntity).filter(CodeEntity.id.in_(code_entity_ids)).all()
    } if code_entity_ids else {}
    _append_code_dependencies(nodes, edges, sampled_code_edges, code_entities)

    result = _capped_overview(
        nodes, edges, include_isolated=include_isolated, preserved_node_ids=preserved_node_ids, limit=limit
    )
    if code_edges_truncated:
        result["truncated"] = True
    result["graph_revision"] = f"proj:{project_id or 'global'}:overview"
    result["has_more"] = result.get("truncated", False)
    result["next_cursor"] = None
    return result


@router.get("/overview")
def get_graph_overview(
    project_id: Optional[int] = None,
    status: str = "approved",
    group_by: Optional[str] = Query(None),
    limit: Optional[int] = Query(None),
    cursor: Optional[str] = Query(None),
    include_isolated: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Alias for GET /graph with explicit overview query parameters (O-298)."""
    return get_graph(
        project_id=project_id,
        status=status,
        include_isolated=include_isolated,
        limit=limit,
        cursor=cursor,
        db=db,
        user=user,
    )


def _capped_overview(
    nodes: dict[str, dict],
    edges: list[dict],
    include_isolated: bool = False,
    preserved_node_ids: Optional[set[str]] = None,
    limit: Optional[int] = None,
) -> dict:
    """O-053 / O-285 / O-298: Harter Deckel für die Übersicht mit Erhalt aller Beziehungsklassen.
    O-285: Isolierte Knoten (Grad 0) werden standardmäßig vor dem Capping gefiltert
    (include_isolated=False), sodass das KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES-Budget
    ausschließlich für das vernetzte Beziehungsgeflecht genutzt wird.
    O-298: Dokumentierte Entities und Knowledge-Link-Endpunkte werden vor beliebigen
    Code-Knoten geschützt, damit keine Beziehungsklassen durch Capping verloren gehen.
    """
    degree: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in edges:
        src = edge["source"] if isinstance(edge["source"], str) else edge["source"]["id"]
        tgt = edge["target"] if isinstance(edge["target"], str) else edge["target"]["id"]
        if src in degree:
            degree[src] += 1
        if tgt in degree:
            degree[tgt] += 1

    if not include_isolated:
        nodes = {nid: node for nid, node in nodes.items() if degree[nid] > 0}

    total_nodes = len(nodes)
    total_edges = len(edges)
    max_nodes = limit or cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES
    if total_nodes <= max_nodes:
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "truncated": False,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    ranked_ids = sorted(nodes.keys(), key=lambda nid: (-degree[nid], nid))

    representative_ids: list[str] = []
    if preserved_node_ids:
        for nid in ranked_ids:
            if nid in preserved_node_ids and nid not in representative_ids:
                representative_ids.append(nid)

    represented_sources: set[object] = set()
    for nid in ranked_ids:
        node = nodes[nid]
        source_id = node.get("source_id")
        if node.get("type") != "document" or source_id is None or source_id in represented_sources:
            continue
        represented_sources.add(source_id)
        if nid not in representative_ids:
            representative_ids.append(nid)

    kept_order = representative_ids[:max_nodes]
    kept_order.extend(nid for nid in ranked_ids if nid not in kept_order)
    kept_ids = set(kept_order[:max_nodes])
    kept_nodes = [n for nid, n in nodes.items() if nid in kept_ids]
    kept_edges = [
        e
        for e in edges
        if (e["source"] if isinstance(e["source"], str) else e["source"]["id"]) in kept_ids
        and (e["target"] if isinstance(e["target"], str) else e["target"]["id"]) in kept_ids
    ]
    return {
        "nodes": kept_nodes,
        "edges": kept_edges,
        "truncated": True,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }


@router.get("/neighborhood")
def get_graph_neighborhood(
    node_id: str = Query(..., description="Graph node ID (e.g. 'entity:123', '123', or 'doc:Runbook.md')"),
    project_id: Optional[int] = Query(None, description="Project ID"),
    relationships: Optional[str] = Query(None, description="Comma-separated relationship types: code_dependency, documented, manual"),
    status: str = Query("approved"),
    direction: str = Query("both", pattern="^(incoming|outgoing|both)$"),
    hops: int = Query(1, ge=1, le=5),
    limit: int = Query(150, ge=1, le=500),
    cursor: Optional[str] = Query(None, description="Pagination cursor for neighborhood expansion"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """O-298: Cursorbasierte Ein-Hop-Nachbarschaft für Code-Entities und Dokumentknoten.
    Erlaubt die schrittweise Erweiterung (has_more, next_cursor) ohne Vollmaterialisierung.
    """
    if not isinstance(limit, int):
        limit = 150
    if direction not in {"incoming", "outgoing", "both"}:
        direction = "both"
    if not isinstance(hops, int):
        hops = 1
    if not isinstance(cursor, str):
        cursor = None
    if not isinstance(relationships, str):
        relationships = None
    if not isinstance(status, str):
        status = "approved"

    visible_project_ids = get_visible_project_ids(user, db)
    team_ids = get_visible_team_ids(user, db)
    offset = int(cursor) if (cursor and cursor.isdigit()) else 0
    allowed_rels = (
        {r.strip() for r in relationships.split(",") if r.strip()}
        if relationships
        else {"code_dependency", "documented", "manual"}
    )

    # Fall 1: Dokument-Knoten (doc:...)
    if node_id.startswith("doc:") or node_id.startswith("document:"):
        doc_title = node_id[len("doc:"):] if node_id.startswith("doc:") else node_id[len("document:"):]
        focus_id = f"doc:{doc_title}"

        chunk_query = db.query(DocumentChunk).filter(
            or_(DocumentChunk.file_path == doc_title, DocumentChunk.file_path.like(f"%{doc_title}%"))
        )
        if project_id:
            chunk_query = chunk_query.filter(DocumentChunk.project_id == project_id)
        chunk = chunk_query.first()
        if chunk and chunk.project_id:
            assert_team_visible(chunk.project_id, user, db, "Dokument nicht gefunden")
            assert_project_visible(chunk.project_id, user, db)

        meta = (chunk.metadata_json or {}) if chunk else {}
        nodes: dict[str, dict] = {
            focus_id: _doc_node(
                doc_title,
                meta.get("source_type"),
                meta.get("url"),
                chunk,
            )
        }
        edges: list[dict] = []
        has_more = False

        if "documented" in allowed_rels:
            eq = db.query(EntityDocLink).filter(
                EntityDocLink.doc_title == doc_title,
                EntityDocLink.status == status,
            )
            if project_id:
                eq = eq.filter(EntityDocLink.project_id == project_id)
            doc_links = eq.order_by(EntityDocLink.id).offset(offset).limit(limit + 1).all()
            if len(doc_links) > limit:
                has_more = True
                doc_links = doc_links[:limit]

            ent_ids = {lnk.entity_id for lnk in doc_links}
            ents = {
                e.id: e for e in db.query(CodeEntity).filter(CodeEntity.id.in_(ent_ids)).all()
            } if ent_ids else {}
            chunk_ids = {lnk.chunk_id for lnk in doc_links if lnk.chunk_id is not None}
            chunks_map = {
                c.id: c for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()
            } if chunk_ids else {}

            for lnk in doc_links:
                ent = ents.get(lnk.entity_id)
                if not ent:
                    continue
                eid = f"entity:{ent.id}"
                nodes.setdefault(eid, _entity_node(ent))
                edges.append({
                    "id": f"edl:{lnk.id}",
                    "source": eid,
                    "target": focus_id,
                    "link_type": lnk.link_type,
                    "relation_type": "documented",
                    "direction": "directed",
                    "score": lnk.score,
                    "context": lnk.context,
                    **_document_locator(chunks_map.get(lnk.chunk_id), lnk.doc_url),
                })

        if "manual" in allowed_rels:
            klinks = db.query(KnowledgeLink).filter(
                KnowledgeLink.status == status,
                or_(
                    (KnowledgeLink.source_a_type == "document") & (KnowledgeLink.source_a_title == doc_title),
                    (KnowledgeLink.source_b_type == "document") & (KnowledgeLink.source_b_title == doc_title),
                ),
            ).all()
            for klink in klinks:
                is_a = klink.source_a_type == "document" and klink.source_a_title == doc_title
                klink_dir = getattr(klink, "direction", None) or "undirected"
                other_type, other_entity_id, other_chunk_id, other_title, other_source_type, other_url = (
                    (klink.source_b_type, klink.source_b_entity_id, klink.source_b_chunk_id, klink.source_b_title, klink.source_b_source_type, klink.source_b_url)
                    if is_a
                    else (klink.source_a_type, klink.source_a_entity_id, klink.source_a_chunk_id, klink.source_a_title, klink.source_a_source_type, klink.source_a_url)
                )
                other_id = _side_node_id(nodes, db, other_type, other_entity_id, other_chunk_id, other_title, other_source_type, other_url)
                if not other_id:
                    continue
                if klink_dir == "directed" and not is_a:
                    edge_src, edge_tgt = other_id, focus_id
                else:
                    edge_src, edge_tgt = focus_id, other_id
                edges.append({
                    "id": f"kl:{klink.id}",
                    "source": edge_src,
                    "target": edge_tgt,
                    "link_type": klink.link_type,
                    "direction": klink_dir,
                    "score": klink.score,
                    "context": klink.context,
                })

        next_cursor = str(offset + limit) if has_more else None
        return {
            "focus_id": focus_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "has_more": has_more,
            "next_cursor": next_cursor,
            "graph_revision": f"doc:{doc_title}:rev",
            "relationships": list(allowed_rels),
            "total_edges": len(edges),
            "truncated": {"incoming": has_more, "outgoing": has_more},
        }

    # Fall 2: Entity-Knoten
    ent_id = None
    if node_id.startswith("entity:"):
        try:
            ent_id = int(node_id[len("entity:"):])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Ungültige entity ID in {node_id}")
    elif node_id.isdigit():
        ent_id = int(node_id)
    else:
        raise HTTPException(status_code=400, detail=f"Ungültige node_id: {node_id}")

    entity_query = db.query(CodeEntity).filter(CodeEntity.id == ent_id)
    if project_id:
        entity_query = entity_query.filter(CodeEntity.project_id == project_id)
    entity = entity_query.first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")

    proj_id = entity.project_id
    if proj_id:
        proj = db.query(Project).filter(Project.id == proj_id).first()
        if not proj:
            raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
        assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
        assert_project_visible(proj_id, user, db)

    nodes = {}
    edges = []
    focus_id = f"entity:{entity.id}"
    nodes[focus_id] = _entity_node(entity)

    has_more = False
    if "code_dependency" in allowed_rels:
        # Cursor pagination remains the one-hop compatibility path.  Directed
        # traversal deliberately starts at the selected entity and never mixes
        # cursor pages with a changing multi-hop frontier.
        if cursor and hops == 1:
            clauses = []
            if direction in {"outgoing", "both"}:
                clauses.append(CodeEdge.src_entity_id == entity.id)
            if direction in {"incoming", "both"}:
                clauses.append(CodeEdge.dst_entity_id == entity.id)
            code_edges = (
                db.query(CodeEdge)
                .filter(CodeEdge.project_id == proj_id, or_(*clauses))
                .order_by(CodeEdge.id)
                .offset(offset)
                .limit(limit + 1)
                .all()
            )
            if len(code_edges) > limit:
                has_more = True
                code_edges = code_edges[:limit]
        else:
            code_edges, has_more = _traverse_code_dependencies(
                db,
                root_id=entity.id,
                project_id=proj_id,
                direction=direction,
                hops=hops,
                limit=limit,
            )

        neighbor_ids = {
            e_id
            for edge in code_edges
            for e_id in (edge.src_entity_id, edge.dst_entity_id)
            if e_id is not None
        }
        neighbor_entities = {
            neighbor.id: neighbor
            for neighbor in db.query(CodeEntity).filter(
                CodeEntity.id.in_(neighbor_ids), CodeEntity.project_id == proj_id
            ).all()
        } if neighbor_ids else {}
        _append_code_dependencies(nodes, edges, code_edges, neighbor_entities)

    if "documented" in allowed_rels:
        doc_links = (
            db.query(EntityDocLink)
            .filter(
                EntityDocLink.project_id == proj_id,
                EntityDocLink.entity_id == entity.id,
                EntityDocLink.status == status,
            )
            .all()
        )
        chunk_ids = {lnk.chunk_id for lnk in doc_links if lnk.chunk_id is not None}
        chunks = (
            {c.id: c for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()}
            if chunk_ids
            else {}
        )
        for lnk in doc_links:
            did = f"doc:{lnk.doc_title}"
            nodes.setdefault(
                did, _doc_node(lnk.doc_title, lnk.source_type, lnk.doc_url, chunks.get(lnk.chunk_id))
            )
            edges.append(
                {
                    "id": f"edl:{lnk.id}",
                    "source": focus_id,
                    "target": did,
                    "link_type": lnk.link_type,
                    "relation_type": "documented",
                    "direction": "directed",
                    "score": lnk.score,
                    "context": lnk.context,
                    **_document_locator(chunks.get(lnk.chunk_id), lnk.doc_url),
                }
            )

    if "manual" in allowed_rels:
        klinks = (
            db.query(KnowledgeLink)
            .filter(
                KnowledgeLink.status == status,
                or_(
                    (KnowledgeLink.source_a_type == "entity")
                    & (KnowledgeLink.source_a_entity_id == entity.id),
                    (KnowledgeLink.source_b_type == "entity")
                    & (KnowledgeLink.source_b_entity_id == entity.id),
                ),
            )
            .all()
        )
        for klink in klinks:
            is_a = klink.source_a_type == "entity" and klink.source_a_entity_id == entity.id
            klink_dir = getattr(klink, "direction", None) or "undirected"
            other_type, other_entity_id, other_chunk_id, other_title, other_source_type, other_url = (
                (
                    klink.source_b_type,
                    klink.source_b_entity_id,
                    klink.source_b_chunk_id,
                    klink.source_b_title,
                    klink.source_b_source_type,
                    klink.source_b_url,
                )
                if is_a
                else (
                    klink.source_a_type,
                    klink.source_a_entity_id,
                    klink.source_a_chunk_id,
                    klink.source_a_title,
                    klink.source_a_source_type,
                    klink.source_a_url,
                )
            )
            other_id = _side_node_id(
                nodes,
                db,
                other_type,
                other_entity_id,
                other_chunk_id,
                other_title,
                other_source_type,
                other_url,
            )
            if not other_id:
                continue
            if klink_dir == "directed" and not is_a:
                edge_src, edge_tgt = other_id, focus_id
            else:
                edge_src, edge_tgt = focus_id, other_id

            edges.append(
                {
                    "id": f"kl:{klink.id}",
                    "source": edge_src,
                    "target": edge_tgt,
                    "link_type": klink.link_type,
                    "direction": klink_dir,
                    "score": klink.score,
                    "context": klink.context,
                }
            )

    next_cursor = str(offset + limit) if has_more else None
    return {
        "focus_id": focus_id,
        "nodes": list(nodes.values()),
        "edges": edges,
        "has_more": has_more,
        "next_cursor": next_cursor,
        "graph_revision": f"proj:{proj_id}:entity-{entity.id}",
        "relationships": list(allowed_rels),
        "direction": direction,
        "hops": hops,
        "total_edges": len(edges),
        "truncated": {"incoming": has_more, "outgoing": has_more},
    }


@router.get("/focus")
def get_graph_focus(
    project_id: int,
    entity_id: int,
    status: str = "approved",
    direction: str = Query("both", pattern="^(incoming|outgoing|both)$"),
    hops: int = Query(1, ge=1, le=5),
    limit: int = Query(500, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ein-Hop-Nachbarschaft inklusive neutral projizierter Codeabhängigkeiten."""
    if not isinstance(limit, int):
        limit = 500
    if not isinstance(cursor, str):
        cursor = None
    if not isinstance(status, str):
        status = "approved"
    return get_graph_neighborhood(
        node_id=f"entity:{entity_id}",
        project_id=project_id,
        status=status,
        direction=direction,
        hops=hops,
        limit=limit,
        cursor=cursor,
        db=db,
        user=user,
    )


@router.get("/export")
def export_graph(
    format: str = Query(..., pattern="^(csv|graphml)$"),
    project_id: Optional[int] = None,
    status: str = "approved",
    include_isolated: bool = Query(
        False, description="Whether to include degree-0 isolated nodes in the export"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Neutraler CSV-/GraphML-Export des Wissensgraphen (O-034), analog zu
    /callgraph/export -- anders als /export/neo4j (Cypher, an Neo4j gebunden)
    ist das Ergebnis in jedem generischen Graph-Werkzeug importierbar."""
    graph = get_graph(
        project_id=project_id,
        status=status,
        include_isolated=include_isolated,
        db=db,
        user=user,
    )
    nodes = graph["nodes"]
    edges = graph["edges"]

    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["source", "target", "link_type", "score", "context", "direction"])
        for edge in edges:
            writer.writerow(
                [
                    edge["source"],
                    edge["target"],
                    edge["link_type"],
                    edge["score"] if edge.get("score") is not None else "",
                    edge.get("context") or "",
                    edge.get("direction") or "undirected",
                ]
            )
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=knowledge_graph.csv"},
        )

    root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    xml_graph = SubElement(root, "graph", edgedefault="directed")
    for node in nodes:
        xml_node = SubElement(xml_graph, "node", id=str(node["id"]))
        SubElement(xml_node, "data", key="label").text = node["label"]
        SubElement(xml_node, "data", key="type").text = node["type"]
        if node.get("entity_type"):
            SubElement(xml_node, "data", key="entity_type").text = node["entity_type"]
    for edge in edges:
        is_directed = (edge.get("direction") or "undirected") in ("directed", "bidirectional")
        xml_edge = SubElement(
            xml_graph,
            "edge",
            id=str(edge["id"]),
            source=str(edge["source"]),
            target=str(edge["target"]),
            directed="true" if is_directed else "false",
        )
        SubElement(xml_edge, "data", key="link_type").text = edge["link_type"]
        if edge.get("score") is not None:
            SubElement(xml_edge, "data", key="score").text = str(edge["score"])
        SubElement(xml_edge, "data", key="direction").text = edge.get("direction") or "undirected"
    return Response(
        tostring(root, encoding="unicode"),
        media_type="application/graphml+xml",
        headers={"Content-Disposition": "attachment; filename=knowledge_graph.graphml"},
    )


@router.get("/export/neo4j")
def export_neo4j_cypher(
    project_id: Optional[int] = None,
    status: str = "approved",
    include_isolated: bool = Query(
        False, description="Whether to include degree-0 isolated nodes in the export"
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    graph = get_graph(
        project_id=project_id,
        status=status,
        include_isolated=include_isolated,
        db=db,
        user=user,
    )
    nodes = graph["nodes"]
    edges = graph["edges"]

    lines: list[str] = [
        "// Doctus Knowledge Graph — Neo4j Cypher import",
        f"// Nodes: {len(nodes)}  Edges: {len(edges)}",
        "// Run in Neo4j Browser or cypher-shell",
        "",
    ]

    for n in nodes:
        label = "Entity" if n["type"] == "entity" else "Document"
        props: dict = {"id": n["id"], "label": n["label"]}
        if n.get("source_type"):
            props["source_type"] = n["source_type"]
        if n.get("entity_type"):
            props["entity_type"] = n["entity_type"]
        if n.get("file_path"):
            props["file_path"] = n["file_path"]
        if n.get("url"):
            props["url"] = n["url"]
        prop_str = ", ".join(f"{k}: {repr(v)}" for k, v in props.items())
        lines.append(f"MERGE (n_{_safe_id(n['id'])}:{label} {{{prop_str}}});")

    lines.append("")

    for e in edges:
        src_id = e["source"] if isinstance(e["source"], str) else e["source"]["id"]
        tgt_id = e["target"] if isinstance(e["target"], str) else e["target"]["id"]
        rel = e["link_type"].upper().replace("-", "_")
        score_prop = f" {{score: {round(e['score'], 4)}}}" if e.get("score") is not None else ""
        direction = e.get("direction") or "undirected"
        if direction in ("undirected", "bidirectional"):
            lines.append(
                f"MATCH (a {{id: {repr(src_id)}}}), (b {{id: {repr(tgt_id)}}})"
                f" MERGE (a)-[:{rel}{score_prop}]->(b)"
                f" MERGE (b)-[:{rel}{score_prop}]->(a);"
            )
        else:
            lines.append(
                f"MATCH (a {{id: {repr(src_id)}}}), (b {{id: {repr(tgt_id)}}})"
                f" MERGE (a)-[:{rel}{score_prop}]->(b);"
            )

    return {"cypher": "\n".join(lines), "node_count": len(nodes), "edge_count": len(edges)}


def _safe_id(raw: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in raw)
