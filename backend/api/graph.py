"""
backend/api/graph.py
======================
Knowledge Graph: Visualization of relationships between code objects and documentation.

This module provides routes to prepare the networked data of the Doctus system as
graphs (nodes and edges) for frontend visualization (Force-Graph, Mermaid).

Endpoints:
    GET /graph           — Full graph of a project (entities + documents)
    GET /graph/focus     — 1-hop neighborhood of an entity (local focus)
    GET /graph/export    — Cypher export for external graph databases (Neo4j)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from core.db_setup import get_db
from models.database import CodeEntity, EntityDocLink, KnowledgeLink, Project, Team, User, KnowledgeSource, DocumentChunk
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids, assert_team_visible
from core.projects import assert_project_visible

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
    }


def _doc_node(title: str, source_type: Optional[str], url: Optional[str], chunk: Optional[DocumentChunk] = None) -> dict:
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


def _is_project_visible(project_id: Optional[int], team_ids: Optional[list[int]], db: Session) -> bool:
    if project_id is None:
        return True
    if team_ids is None:
        return True
    proj = db.query(Project).filter(Project.id == project_id).first()
    return proj is not None and proj.team_id in team_ids


def _is_source_visible(source_id: Optional[int], team_ids: Optional[list[int]], db: Session) -> bool:
    if source_id is None:
        return True
    if team_ids is None:
        return True
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    return source is not None and source.team_id in team_ids


def _side_node_id(nodes: dict, db: Session, side_type: str, entity_id: Optional[int], chunk_id: Optional[int],
                   title: str, source_type: Optional[str], url: Optional[str]) -> Optional[str]:
    """Resolves one side of a generic KnowledgeLink ('entity' | 'document') into a graph node,
    inserting it into `nodes` if not already present, and returns its node id."""
    if side_type == "entity" and entity_id is not None:
        entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not entity:
            return None
        nid = f"entity:{entity.id}"
        nodes.setdefault(nid, _entity_node(entity))
        return nid
    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first() if chunk_id else None
    nid = f"doc:{title}"
    nodes.setdefault(nid, _doc_node(title, source_type, url, chunk))
    return nid


def _is_side_visible(source_type: str, entity_id: Optional[int], chunk_id: Optional[int], team_ids: Optional[list[int]], db: Session) -> bool:
    if team_ids is None:
        return True
    if source_type == 'entity' and entity_id is not None:
        ent = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
        if not ent:
            return False
        return _is_project_visible(ent.project_id, team_ids, db) and _is_source_visible(ent.source_id, team_ids, db)
    elif source_type == 'document' and chunk_id is not None:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
        if not chunk:
            return False
        return _is_project_visible(chunk.project_id, team_ids, db) and _is_source_visible(chunk.source_id, team_ids, db)
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
    elif team_ids is not None:
        project_ids = [p[0] for p in db.query(Project.id).filter(Project.team_id.in_(team_ids)).all()]
        entity_query = entity_query.filter(or_(
            CodeEntity.project_id.in_(project_ids),
            CodeEntity.project_id == None
        ))
    
    for entity in entity_query.all():
        eid = f"entity:{entity.id}"
        nodes[eid] = _entity_node(entity)

    # 2. Fetch all visible Documents (unique file_paths) and add them as nodes
    doc_query = db.query(DocumentChunk)
    if project_id:
        doc_query = doc_query.filter(DocumentChunk.project_id == project_id)
    elif team_ids is not None:
        project_ids = [p[0] for p in db.query(Project.id).filter(Project.team_id.in_(team_ids)).all()]
        doc_query = doc_query.filter(or_(
            DocumentChunk.project_id.in_(project_ids),
            DocumentChunk.project_id == None
        ))
    
    min_ids_subquery = doc_query.with_entities(func.min(DocumentChunk.id)).group_by(DocumentChunk.file_path).subquery()
    distinct_docs = db.query(DocumentChunk).filter(DocumentChunk.id.in_(min_ids_subquery)).all()
    for chunk in distinct_docs:
        meta = chunk.metadata_json or {}
        title = meta.get("title") or chunk.file_path
        did = f"doc:{title}"
        nodes.setdefault(did, _doc_node(title, meta.get("source_type"), meta.get("url"), chunk))

    # ── Entity → Document links ──────────────────────────────────────────────
    eq = db.query(EntityDocLink).filter(EntityDocLink.status == status)
    if project_id:
        eq = eq.filter(EntityDocLink.project_id == project_id)
    elif team_ids is not None:
        eq = eq.join(Project).filter(Project.team_id.in_(team_ids))
    entity_links = eq.all()

    if entity_links:
        entity_ids = {lnk.entity_id for lnk in entity_links}
        entities = {
            e.id: e
            for e in db.query(CodeEntity).filter(CodeEntity.id.in_(entity_ids)).all()
        }
        chunk_ids = {lnk.chunk_id for lnk in entity_links if lnk.chunk_id is not None}
        chunks = {
            c.id: c
            for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()
        } if chunk_ids else {}
        for lnk in entity_links:
            entity = entities.get(lnk.entity_id)
            if not entity:
                continue
            eid = f"entity:{entity.id}"
            nodes.setdefault(eid, _entity_node(entity))
            did = f"doc:{lnk.doc_title}"
            nodes.setdefault(did, _doc_node(lnk.doc_title, lnk.source_type, lnk.doc_url, chunks.get(lnk.chunk_id)))
            edges.append({
                "id": f"edl:{lnk.id}",
                "source": eid,
                "target": did,
                "link_type": lnk.link_type,
                "score": lnk.score,
                "context": None,
            })

    # ── Cross-object knowledge links (auto doc↔doc + manual entity/document pairs) ──
    # KnowledgeLink.source_{a,b}_type is generic ('entity' | 'document'), but until now
    # only doc↔doc rows were ever populated (auto cross-source computation) or rendered
    # here. Manual links created from the graph UI (see /knowledge-links) can connect
    # any two nodes, so both sides are resolved generically.
    for klink in db.query(KnowledgeLink).filter(KnowledgeLink.status == status).all():
        if not (_is_side_visible(klink.source_a_type, klink.source_a_entity_id, klink.source_a_chunk_id, team_ids, db) and
                _is_side_visible(klink.source_b_type, klink.source_b_entity_id, klink.source_b_chunk_id, team_ids, db)):
            continue
        src_id = _side_node_id(nodes, db, klink.source_a_type, klink.source_a_entity_id, klink.source_a_chunk_id,
                                klink.source_a_title, klink.source_a_source_type, klink.source_a_url)
        tgt_id = _side_node_id(nodes, db, klink.source_b_type, klink.source_b_entity_id, klink.source_b_chunk_id,
                                klink.source_b_title, klink.source_b_source_type, klink.source_b_url)
        if not src_id or not tgt_id:
            continue
        edges.append({
            "id": f"kl:{klink.id}",
            "source": src_id,
            "target": tgt_id,
            "link_type": klink.link_type,
            "score": klink.score,
            "context": klink.context,
        })

    return {"nodes": list(nodes.values()), "edges": edges}


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

    entity = db.query(CodeEntity).filter(
        CodeEntity.id == entity_id, CodeEntity.project_id == project_id
    ).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")

    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    focus_id = f"entity:{entity.id}"
    nodes[focus_id] = _entity_node(entity)
    # Code-Referenz-Fanout (CALL/PERFORM/GOTO/COPY/USE) entfernt zusammen mit dem
    # nie produktiv befüllten CodeReference-Modell (siehe TECH_DEBT_CLEANUP_PLAN.md
    # §1) — always-false, damit das Frontend-Truncation-Banner unverändert bleibt.
    truncated = {"incoming": False, "outgoing": False}

    # Dokument-Links dieser Entity
    doc_links = db.query(EntityDocLink).filter(
        EntityDocLink.project_id == project_id,
        EntityDocLink.entity_id == entity.id,
        EntityDocLink.status == status,
    ).all()
    chunk_ids = {lnk.chunk_id for lnk in doc_links if lnk.chunk_id is not None}
    chunks = {
        c.id: c
        for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()
    } if chunk_ids else {}
    for lnk in doc_links:
        did = f"doc:{lnk.doc_title}"
        nodes.setdefault(did, _doc_node(lnk.doc_title, lnk.source_type, lnk.doc_url, chunks.get(lnk.chunk_id)))
        edges.append({
            "id": f"edl:{lnk.id}", "source": focus_id, "target": did,
            "link_type": lnk.link_type, "score": lnk.score, "context": None,
        })

    # KnowledgeLinks der Entity (v.a. manuell über die Graph-UI erstellte Entity↔Entity-
    # Verknüpfungen, siehe /knowledge-links) — ohne das bleibt jeder Fokus-Graph rein
    # dokument-zentriert und "Verbindungen erweitern" hat nie eine Nachbar-Entity, auf
    # die es angewendet werden könnte.
    klinks = db.query(KnowledgeLink).filter(
        KnowledgeLink.status == status,
        or_(
            (KnowledgeLink.source_a_type == "entity") & (KnowledgeLink.source_a_entity_id == entity.id),
            (KnowledgeLink.source_b_type == "entity") & (KnowledgeLink.source_b_entity_id == entity.id),
        ),
    ).all()
    for klink in klinks:
        is_a = klink.source_a_type == "entity" and klink.source_a_entity_id == entity.id
        other_type, other_entity_id, other_chunk_id, other_title, other_source_type, other_url = (
            (klink.source_b_type, klink.source_b_entity_id, klink.source_b_chunk_id,
             klink.source_b_title, klink.source_b_source_type, klink.source_b_url)
            if is_a else
            (klink.source_a_type, klink.source_a_entity_id, klink.source_a_chunk_id,
             klink.source_a_title, klink.source_a_source_type, klink.source_a_url)
        )
        other_id = _side_node_id(nodes, db, other_type, other_entity_id, other_chunk_id,
                                  other_title, other_source_type, other_url)
        if not other_id:
            continue
        edges.append({
            "id": f"kl:{klink.id}", "source": focus_id, "target": other_id,
            "link_type": klink.link_type, "score": klink.score, "context": klink.context,
        })

    return {"focus_id": focus_id, "nodes": list(nodes.values()), "edges": edges, "truncated": truncated}


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
        lines.append(
            f"MATCH (a {{id: {repr(src_id)}}}), (b {{id: {repr(tgt_id)}}})"
            f" MERGE (a)-[:{rel}{score_prop}]->(b);"
        )

    return {"cypher": "\n".join(lines), "node_count": len(nodes), "edge_count": len(edges)}


def _safe_id(raw: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in raw)
