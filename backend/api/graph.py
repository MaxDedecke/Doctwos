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
    # This context rule also applies to administrators. Admin visibility may
    # bypass team/project membership checks, but it must not turn a project
    # scoped document into a global document in the "Allgemein" graph.
    if source_type == "document" and chunk_id is not None and requesting_project_id is None:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        if not chunk or chunk.project_id is not None:
            return False
    if team_ids is None:
        return True
    if source_type == "entity" and entity_id is not None:
        ent = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not ent:
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
        return (
            _is_project_visible(chunk.project_id, team_ids, project_ids, db)
            and _is_source_visible(chunk.source_id, team_ids, project_ids, db)
            and is_document_chunk_code_visible_in_context(chunk, requesting_project_id, db)
        )
    return True


@router.get("")
def get_graph(
    project_id: Optional[int] = None,
    status: str = "approved",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns the global knowledge graph.
    Nodes are either code entities or document chunks.
    Edges are approved links (EntityDocLink) or document cross-references (KnowledgeLink).
    """
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

    # 1. Fetch all visible Code Entities and add them as nodes
    entity_query = db.query(CodeEntity)
    if project_id:
        entity_query = entity_query.filter(CodeEntity.project_id == project_id)
    else:
        # Kein Projekt-Kontext ("Allgemein") -- Team-/Projekt-Mitgliedschaft allein reicht
        # hier NICHT (das wäre "jedes Team-Projekt sichtbar", zu weit). Code-Analyse-
        # Objekte sind projektspezifisch und tauchen außerhalb ihres eigenen Projekt-
        # Kontexts nur auf, wenn das Projekt explizit dafür freigegeben ist. Default:
        # kein Projekt freigegeben, also zeigt "Allgemein" nur projektlose Entities
        # (z.B. eigenständige Git-Wissensquellen).
        exposed_project_ids = get_globally_exposed_project_ids(db)
        if visible_project_ids is not None:
            exposed_project_ids = [pid for pid in exposed_project_ids if pid in visible_project_ids]
        entity_query = entity_query.filter(
            or_(CodeEntity.project_id.in_(exposed_project_ids), CodeEntity.project_id.is_(None))
        )

    # Deterministische Reihenfolge -- Voraussetzung dafür, dass ein Kappen unten
    # (O-053) bei wiederholten Aufrufen dieselbe Auswahl trifft statt bei jedem
    # Laden andere Knoten zufällig zu verlieren.
    for entity in entity_query.order_by(CodeEntity.id).all():
        eid = f"entity:{entity.id}"
        nodes[eid] = _entity_node(entity)

    # 1b. Fetch language-neutral code relationships.  ``CodeEdge.type`` is an
    # open string, so this deliberately does not use a COBOL-specific allowlist
    # (Java currently contributes CALLS, EXTENDS, IMPLEMENTS, USES_TYPE,
    # INSTANTIATES, READS and WRITES).
    code_edge_query = db.query(CodeEdge)
    if project_id:
        code_edge_query = code_edge_query.filter(CodeEdge.project_id == project_id)
    elif visible_project_ids is not None:
        code_edge_query = code_edge_query.filter(
            or_(CodeEdge.project_id.in_(exposed_project_ids), CodeEdge.project_id.is_(None))
        )
    for code_edge in code_edge_query.order_by(CodeEdge.id).all():
        source_id = f"entity:{code_edge.src_entity_id}"
        if source_id not in nodes:
            continue
        if code_edge.dst_entity_id is None:
            target_id = f"unresolved:code:{code_edge.id}"
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
        else:
            target_id = f"entity:{code_edge.dst_entity_id}"
            if target_id not in nodes:
                continue
        edges.append(
            {
                "id": f"code:{code_edge.id}",
                "source": source_id,
                "target": target_id,
                "link_type": code_edge.type,
                "type": code_edge.type,
                "direction": "directed",
                "score": None,
                "context": None,
                "resolution": code_edge.resolution,
                "meta": code_edge.meta_json or {},
                "start_line": code_edge.src_start_line,
                "end_line": code_edge.src_end_line,
            }
        )

    # 2. Fetch all visible Documents (unique file_paths) and add them as nodes
    doc_query = db.query(DocumentChunk)
    if project_id:
        doc_query = doc_query.filter(DocumentChunk.project_id == project_id)
    else:
        # Der Allgemein-Graph ist ein globaler Quellenkontext, kein Sammelgraph
        # aller Projekte des Benutzers. Projektgebundene Dokumente (insbesondere
        # Uploads/PDFs) bleiben deshalb im jeweiligen Projektkontext und werden
        # hier auch für Administratoren nicht geladen.
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
        # Dieselbe Opt-in-Einschränkung wie beim Entity-Node-Fetch oben -- sonst würde
        # dieser Zweig unfreigegebene Projekt-Entities über den Doc-Link-Pfad wieder
        # als Node in den Graphen zurückholen.
        eq = eq.filter(EntityDocLink.project_id.in_(exposed_project_ids))
        # Auch wenn ein Projekt seine Code-Analyse global freigibt, dürfen
        # projektgebundene Dokumentziele nicht über EntityDocLink in den
        # Allgemein-Graphen zurückgelangen.
        eq = eq.filter(EntityDocLink.chunk_id.is_(None))
    entity_links = eq.all()

    if entity_links:
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
                }
            )

    # ── Cross-object knowledge links (auto doc↔doc + manual entity/document pairs) ──
    # KnowledgeLink.source_{a,b}_type is generic ('entity' | 'document'), but until now
    # only doc↔doc rows were ever populated (auto cross-source computation) or rendered
    # here. Manual links created from the graph UI (see /knowledge-links) can connect
    # any two nodes, so both sides are resolved generically.
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

    return _capped_overview(nodes, edges)


def _capped_overview(nodes: dict[str, dict], edges: list[dict]) -> dict:
    """O-053: harter Deckel für die Übersicht -- ohne den würde ein großer Bestand
    unbegrenzt viele Knoten an eine Kraftsimulation im Browser-Hauptthread
    übergeben (Server-Antwortgröße, Rechenzeit im Tab, am Ende ein unlesbarer
    "Wollknäuel"). Bevorzugt beim Kappen die am dichtesten verlinkten Knoten --
    die Übersicht zeigt bewusst auch unverlinkte Entities (Inventarcharakter),
    aber die sind beim Kappen der uninteressanteste Teil. `/graph/focus` bleibt
    der Weg, um gezielt in einen bestimmten Bereich hineinzuzoomen, sobald
    gekappt wurde.
    """
    total_nodes = len(nodes)
    total_edges = len(edges)
    limit = cfg.KNOWLEDGE_GRAPH_OVERVIEW_MAX_NODES
    if total_nodes <= limit:
        return {
            "nodes": list(nodes.values()),
            "edges": edges,
            "truncated": False,
            "total_nodes": total_nodes,
            "total_edges": total_edges,
        }

    degree: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in edges:
        if edge["source"] in degree:
            degree[edge["source"]] += 1
        if edge["target"] in degree:
            degree[edge["target"]] += 1

    ranked_ids = sorted(nodes.keys(), key=lambda nid: (-degree[nid], nid))

    # Keep one representative file node per source even when it has no link.
    # A large code repository can otherwise consume the whole cap with highly
    # connected code nodes and silently hide an indexed PDF/handbook. The graph
    # deliberately represents a file by one node (chunks remain the retrieval
    # units), so this small source-diversity reservation is enough to make the
    # document source discoverable without removing the cap.
    representative_ids: list[str] = []
    represented_sources: set[object] = set()
    for nid in ranked_ids:
        node = nodes[nid]
        source_id = node.get("source_id")
        if node.get("type") != "document" or source_id is None or source_id in represented_sources:
            continue
        represented_sources.add(source_id)
        representative_ids.append(nid)

    kept_order = representative_ids[:limit]
    kept_order.extend(nid for nid in ranked_ids if nid not in kept_order)
    kept_ids = set(kept_order[:limit])
    kept_nodes = [n for nid, n in nodes.items() if nid in kept_ids]
    kept_edges = [e for e in edges if e["source"] in kept_ids and e["target"] in kept_ids]
    return {
        "nodes": kept_nodes,
        "edges": kept_edges,
        "truncated": True,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
    }


@router.get("/focus")
def get_graph_focus(
    project_id: int,
    entity_id: int,
    status: str = "approved",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Ein-Hop-Nachbarschaft einer Code-Entity: Dokument-Links (EntityDocLink) plus Code-Beziehungen."""
    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")
    assert_project_visible(project_id, user, db)

    entity = (
        db.query(CodeEntity)
        .filter(CodeEntity.id == entity_id, CodeEntity.project_id == project_id)
        .first()
    )
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    focus_id = f"entity:{entity.id}"
    nodes[focus_id] = _entity_node(entity)
    # Code relationships are part of the same language-neutral graph as
    # document links.  A focus request gets the direct incoming/outgoing
    # neighborhood regardless of the parser that produced the edge.
    code_edges = (
        db.query(CodeEdge)
        .filter(
            CodeEdge.project_id == project_id,
            or_(CodeEdge.src_entity_id == entity.id, CodeEdge.dst_entity_id == entity.id),
        )
        .order_by(CodeEdge.id)
        .all()
    )
    for code_edge in code_edges:
        source_id = f"entity:{code_edge.src_entity_id}"
        if code_edge.src_entity_id == entity.id:
            nodes.setdefault(source_id, _entity_node(entity))
        else:
            source_entity = (
                db.query(CodeEntity).filter(CodeEntity.id == code_edge.src_entity_id).first()
            )
            if not source_entity or source_entity.project_id != project_id:
                continue
            nodes.setdefault(source_id, _entity_node(source_entity))
        if code_edge.dst_entity_id is None:
            target_id = f"unresolved:code:{code_edge.id}"
            nodes.setdefault(
                target_id,
                {
                    "id": target_id,
                    "type": "external",
                    "label": code_edge.dst_name,
                    "entity_type": None,
                    "file_path": None,
                    "start_line": None,
                    "project_id": project_id,
                    "source_type": None,
                    "url": None,
                    "source_id": code_edge.source_id,
                    "unresolved": True,
                },
            )
        else:
            target_entity = (
                db.query(CodeEntity).filter(CodeEntity.id == code_edge.dst_entity_id).first()
            )
            if not target_entity or target_entity.project_id != project_id:
                continue
            target_id = f"entity:{target_entity.id}"
            nodes.setdefault(target_id, _entity_node(target_entity))
        edges.append(
            {
                "id": f"code:{code_edge.id}",
                "source": source_id,
                "target": target_id,
                "link_type": code_edge.type,
                "type": code_edge.type,
                "direction": "directed",
                "score": None,
                "context": None,
                "resolution": code_edge.resolution,
                "meta": code_edge.meta_json or {},
                "start_line": code_edge.src_start_line,
                "end_line": code_edge.src_end_line,
            }
        )
    # Code-Referenz-Fanout (CALL/PERFORM/GOTO/COPY/USE) entfernt zusammen mit dem
    # nie produktiv befüllten CodeReference-Modell (siehe TECH_DEBT_CLEANUP_PLAN.md
    # §1) — always-false, damit das Frontend-Truncation-Banner unverändert bleibt.
    truncated = {"incoming": False, "outgoing": False}

    # Dokument-Links dieser Entity
    doc_links = (
        db.query(EntityDocLink)
        .filter(
            EntityDocLink.project_id == project_id,
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
            }
        )

    # KnowledgeLinks der Entity (v.a. manuell über die Graph-UI erstellte Entity↔Entity-
    # Verknüpfungen, siehe /knowledge-links) — ohne das bleibt jeder Fokus-Graph rein
    # dokument-zentriert und "Verbindungen erweitern" hat nie eine Nachbar-Entity, auf
    # die es angewendet werden könnte.
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

    return {
        "focus_id": focus_id,
        "nodes": list(nodes.values()),
        "edges": edges,
        "truncated": truncated,
    }


@router.get("/export")
def export_graph(
    format: str = Query(..., pattern="^(csv|graphml)$"),
    project_id: Optional[int] = None,
    status: str = "approved",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Neutraler CSV-/GraphML-Export des Wissensgraphen (O-034), analog zu
    /callgraph/export -- anders als /export/neo4j (Cypher, an Neo4j gebunden)
    ist das Ergebnis in jedem generischen Graph-Werkzeug importierbar."""
    graph = get_graph(project_id=project_id, status=status, db=db, user=user)
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
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    graph = get_graph(project_id=project_id, status=status, db=db, user=user)
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
