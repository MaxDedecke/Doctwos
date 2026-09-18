"""Begrenzter sprachneutraler Code-Callgraph und Export (F-066)."""

import csv
import io
import json
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from api.entities import _assert_entity_visible, entity_json
from core.analysis_status import load_analysis_status
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from models.database import CodeEdge, CodeEntity, User

router = APIRouter(prefix="/callgraph", tags=["callgraph"])
MAX_NODES = 500
"""Relationship types supported by the call-graph default view.

The persisted contract deliberately keeps edge types open strings.  These
sets only define the useful default view; callers can request any persisted
type through ``types`` (including types added by a future parser).
"""
CALL_EDGE_TYPES = {"CALL", "PERFORM", "GOTO", "COPY", "CALLS", "INSTANTIATES"}
RESOURCE_EDGE_TYPES = {
    "USES_RESOURCE", "INCLUDES", "IMPORTS", "TRANSFORMS_WITH", "READS_XML",
    "SOURCES", "EXECUTES_SCRIPT", "STARTS_JAVA", "REFERENCES_RESOURCE", "LINKS_TO",
}
INHERITANCE_EDGE_TYPES = {"EXTENDS", "IMPLEMENTS"}


def _requested_edge_types(
    types: list[str] | None,
    include_inheritance: bool,
) -> set[str]:
    """Normalize repeated and comma-separated query values.

    ``types`` is intentionally not validated against a registry: entity and
    edge types are an open language-neutral contract.  An explicit request
    therefore also works for a parser type unknown to this API version.
    """
    requested = {
        item.strip().upper() for value in (types or []) for item in value.split(",") if item.strip()
    }
    if requested:
        return requested
    defaults = set(CALL_EDGE_TYPES)
    defaults.update(RESOURCE_EDGE_TYPES)
    if include_inheritance:
        defaults.update(INHERITANCE_EDGE_TYPES)
    return defaults


def _focus(
    db: Session,
    root_id: int,
    hops: int,
    edge_types: set[str] | None = None,
) -> dict:
    seen, frontier = {root_id}, {root_id}
    edge_rows: dict[int, CodeEdge] = {}
    root = db.query(CodeEntity).filter(CodeEntity.id == root_id).first()
    # Code edges are normally project-local.  Keep the focus graph local even
    # if a malformed/imported row points across projects; unprojected legacy
    # entities retain the old unrestricted behavior.
    project_id = root.project_id if root else None
    edge_types = edge_types or _requested_edge_types(None, include_inheritance=False)
    for _ in range(hops):
        if not frontier or len(seen) >= MAX_NODES:
            break
        query = db.query(CodeEdge).filter(
            CodeEdge.type.in_(edge_types),
            or_(CodeEdge.src_entity_id.in_(frontier), CodeEdge.dst_entity_id.in_(frontier)),
        )
        if project_id is not None:
            query = query.filter(CodeEdge.project_id == project_id)
        rows = query.order_by(CodeEdge.id).all()
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
            pid
            for (pid,) in db.query(CodeEntity.parent_id).filter(
                CodeEntity.id.in_(frontier_ids), CodeEntity.parent_id.isnot(None)
            )
        }
        new_ids = {pid for pid in parent_ids if pid not in seen}
        if not new_ids:
            break
        allowed = set(list(new_ids)[: MAX_NODES - len(seen)])
        seen.update(allowed)
        frontier_ids = allowed

    entities = db.query(CodeEntity).filter(CodeEntity.id.in_(seen)).order_by(CodeEntity.id).all()
    nodes = [entity_json(e) for e in entities]
    # O-120: ein Knoten aus einer nur teilweise/gar nicht strukturell
    # analysierten Datei (COBOL-Diagnosen, F-029-Textfallback) darf im Graph
    # nicht ununterscheidbar von einem uneingeschränkt analysierten Knoten
    # erscheinen. Bewusst nur auf Datei-Ebene (welche Entities/Kanten fehlen
    # oder unsicher sind, ist O-150s gemeinsamer Herkunfts-/Unsicherheits-
    # vertrag, nicht Teil dieses Punkts).
    status_by_key = load_analysis_status(
        db, {(node.get("source_id"), node.get("file_path")) for node in nodes}
    )
    for node in nodes:
        info = status_by_key.get((node.get("source_id"), node.get("file_path")))
        if info:
            node["analysis_status"] = info["status"]
            node["analysis_reasons"] = info["reasons"]
    edges = [
        {
            "id": e.id,
            "source": e.src_entity_id,
            "target": e.dst_entity_id,
            "target_name": e.dst_name,
            "type": e.type,
            "resolution": e.resolution,
            "variant_key": e.variant_key,
            "meta": e.meta_json or {},
            "start_line": e.src_start_line,
            "end_line": e.src_end_line,
        }
        for e in edge_rows.values()
        if e.src_entity_id in seen and (e.dst_entity_id is None or e.dst_entity_id in seen)
    ]
    edges += [
        {
            "id": f"contains:{e.id}",
            "source": e.parent_id,
            "target": e.id,
            "target_name": e.name,
            "type": "CONTAINS",
            "resolution": "resolved",
            "variant_key": e.variant_key,
            "meta": (e.meta_json or {}).get("evidence")
            and {"evidence": e.meta_json["evidence"]}
            or {},
            "start_line": e.start_line,
            "end_line": e.end_line,
        }
        for e in entities
        if e.parent_id in seen
    ]
    return {
        "root_id": root_id,
        "hops": hops,
        "edge_types": sorted(
            {edge.type for edge in edge_rows.values()}
            | ({"CONTAINS"} if any(entity.parent_id in seen for entity in entities) else set())
        ),
        "truncated": len(seen) >= MAX_NODES,
        "nodes": nodes,
        "edges": edges,
    }


@router.get("/focus")
def focus(
    entity_id: int,
    hops: int = Query(1, ge=0, le=5),
    types: list[str] | None = Query(
        default=None,
        description=(
            "Kantentypen, wiederholt oder kommasepariert. Offen für neue Parser-Typen; "
            "ohne Angabe werden Aufrufkanten verwendet."
        ),
    ),
    include_inheritance: bool = Query(
        default=False,
        description="EXTENDS/IMPLEMENTS zusätzlich zur Aufrufansicht einblenden",
    ),
    project_id: int | None = Query(
        default=None,
        description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return _focus(
        db,
        entity_id,
        hops,
        _requested_edge_types(types, include_inheritance),
    )


@router.get("/export")
def export_callgraph(
    entity_id: int,
    format: str = Query("json", pattern="^(json|csv|graphml)$"),
    hops: int = Query(3, ge=0, le=5),
    types: list[str] | None = Query(default=None),
    include_inheritance: bool = Query(default=False),
    project_id: int | None = Query(
        default=None,
        description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entity = db.query(CodeEntity).filter(CodeEntity.id == entity_id).first()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    graph = _focus(
        db,
        entity_id,
        hops,
        _requested_edge_types(types, include_inheritance),
    )
    if format == "json":
        return Response(json.dumps(graph, ensure_ascii=False), media_type="application/json")
    if format == "csv":
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(
            [
                "source",
                "target",
                "target_name",
                "type",
                "resolution",
                "variant_key",
                "evidence",
                "condition",
            ]
        )
        for edge in graph["edges"]:
            writer.writerow(
                [
                    edge["source"],
                    edge["target"] or "",
                    edge["target_name"],
                    edge["type"],
                    edge["resolution"],
                    edge.get("variant_key", ""),
                    json.dumps((edge.get("meta") or {}).get("evidence"), ensure_ascii=False),
                    json.dumps((edge.get("meta") or {}).get("condition"), ensure_ascii=False),
                ]
            )
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=callgraph.csv"},
        )
    root = Element("graphml", xmlns="http://graphml.graphdrawing.org/xmlns")
    xml_graph = SubElement(root, "graph", edgedefault="directed")
    for node in graph["nodes"]:
        xml_node = SubElement(xml_graph, "node", id=str(node["id"]))
        SubElement(xml_node, "data", key="name").text = node["name"]
        SubElement(xml_node, "data", key="type").text = node["type"]
    for edge in graph["edges"]:
        if edge["target"] is not None:
            xml_edge = SubElement(
                xml_graph,
                "edge",
                id=str(edge["id"]),
                source=str(edge["source"]),
                target=str(edge["target"]),
            )
            SubElement(xml_edge, "data", key="type").text = edge["type"]
            SubElement(xml_edge, "data", key="resolution").text = edge["resolution"]
            SubElement(xml_edge, "data", key="variant_key").text = edge.get("variant_key", "")
            SubElement(xml_edge, "data", key="evidence").text = json.dumps(
                (edge.get("meta") or {}).get("evidence"), ensure_ascii=False
            )
    return Response(
        tostring(root, encoding="unicode"),
        media_type="application/graphml+xml",
        headers={"Content-Disposition": "attachment; filename=callgraph.graphml"},
    )
