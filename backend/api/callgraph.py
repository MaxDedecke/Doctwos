"""Begrenzter COBOL-Callgraph und Export (F-066)."""
import csv
import io
import json
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.entities import _assert_entity_visible, entity_json
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from models.database import CodeEdge, CodeEntity, User

router = APIRouter(prefix="/callgraph", tags=["callgraph"])
MAX_NODES = 500
EDGE_TYPES = {"CALL", "PERFORM", "GOTO", "COPY"}


def _focus(db: Session, root_id: int, hops: int) -> dict:
    seen, frontier = {root_id}, {root_id}
    edge_rows: dict[int, CodeEdge] = {}
    for _ in range(hops):
        if not frontier or len(seen) >= MAX_NODES:
            break
        rows = db.query(CodeEdge).filter(
            CodeEdge.type.in_(EDGE_TYPES),
            or_(CodeEdge.src_entity_id.in_(frontier), CodeEdge.dst_entity_id.in_(frontier)),
        ).order_by(CodeEdge.id).all()
        next_frontier: set[int] = set()
        for edge in rows:
            edge_rows[edge.id] = edge
            for entity_id in (edge.src_entity_id, edge.dst_entity_id):
                if entity_id is not None and entity_id not in seen and len(seen) < MAX_NODES:
                    seen.add(entity_id)
                    next_frontier.add(entity_id)
        frontier = next_frontier

    # CONTAINS ist keine code_edges-Zeile, sondern wird aus CodeEntity.parent_id
    # abgeleitet (kein zusätzlicher Speicher, keine Nachauflösung nötig). Wir
    # ziehen nur Vorfahren nach (nie Kinder) — sonst würde z.B. ein per PERFORM
    # erreichter Paragraph sein Programm nie als Struktur-Kontext zeigen, während
    # ein Abstieg in alle Paragraphen/Datenfelder eines Programms den 500er-
    # Knotendeckel sprengen könnte, ohne für den Call-Graph-Fokus relevant zu sein.
    frontier_ids = set(seen)
    while frontier_ids and len(seen) < MAX_NODES:
        parent_ids = {
            pid for (pid,) in db.query(CodeEntity.parent_id)
            .filter(CodeEntity.id.in_(frontier_ids), CodeEntity.parent_id.isnot(None))
        }
        new_ids = {pid for pid in parent_ids if pid not in seen}
        if not new_ids:
            break
        allowed = set(list(new_ids)[: MAX_NODES - len(seen)])
        seen.update(allowed)
        frontier_ids = allowed

    entities = db.query(CodeEntity).filter(CodeEntity.id.in_(seen)).order_by(CodeEntity.id).all()
    nodes = [entity_json(e) for e in entities]
    edges = [{"id": e.id, "source": e.src_entity_id, "target": e.dst_entity_id,
              "target_name": e.dst_name, "type": e.type, "resolution": e.resolution,
              "start_line": e.src_start_line, "end_line": e.src_end_line}
             for e in edge_rows.values()
             if e.src_entity_id in seen and (e.dst_entity_id is None or e.dst_entity_id in seen)]
    edges += [{"id": f"contains:{e.id}", "source": e.parent_id, "target": e.id,
               "target_name": e.name, "type": "CONTAINS", "resolution": "resolved",
               "start_line": e.start_line, "end_line": e.end_line}
              for e in entities if e.parent_id in seen]
    return {"root_id": root_id, "hops": hops, "truncated": len(seen) >= MAX_NODES, "nodes": nodes, "edges": edges}


@router.get("/focus")
def focus(entity_id: int, hops: int = Query(1, ge=0, le=3),
          project_id: int | None = Query(default=None, description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus"),
          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return _focus(db, entity_id, hops)


@router.get("/export")
def export_callgraph(entity_id: int, format: str = Query("json", pattern="^(json|csv|graphml)$"),
                     hops: int = Query(3, ge=0, le=3),
                     project_id: int | None = Query(default=None, description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus"),
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    graph = _focus(db, entity_id, hops)
    if format == "json":
        return Response(json.dumps(graph, ensure_ascii=False), media_type="application/json")
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["source", "target", "target_name", "type", "resolution"])
        for edge in graph["edges"]:
            writer.writerow([edge["source"], edge["target"] or "", edge["target_name"], edge["type"], edge["resolution"]])
        return Response(out.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=callgraph.csv"})
    root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    xml_graph = SubElement(root, "graph", edgedefault="directed")
    for node in graph["nodes"]:
        xml_node = SubElement(xml_graph, "node", id=str(node["id"]))
        SubElement(xml_node, "data", key="name").text = node["name"]
        SubElement(xml_node, "data", key="type").text = node["type"]
    for edge in graph["edges"]:
        if edge["target"] is not None:
            xml_edge = SubElement(xml_graph, "edge", id=str(edge["id"]), source=str(edge["source"]), target=str(edge["target"]))
            SubElement(xml_edge, "data", key="type").text = edge["type"]
    return Response(tostring(root, encoding="unicode"), media_type="application/graphml+xml",
                    headers={"Content-Disposition": "attachment; filename=callgraph.graphml"})
