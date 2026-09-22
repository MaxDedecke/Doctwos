"""COBOL-Fokusobjekte und ihre direkte Nachbarschaft (F-067)."""

from pathlib import PurePosixPath
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import (
    assert_knowledge_source_visible,
    assert_project_code_visible_in_context,
    assert_project_visible,
)
from core.teams import assert_team_visible
from models.database import (
    CodeEdge,
    CodeEntity,
    DocumentChunk,
    EntityDocLink,
    KnowledgeSource,
    Project,
    User,
)

router = APIRouter(prefix="/entities", tags=["entities"])


def _url_fragment(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return urlsplit(value).fragment or None
    except ValueError:
        return None


def _assert_entity_visible(
    entity: CodeEntity, user: User, db: Session, project_context_id: int | None = None
) -> None:
    if entity.project_id is not None:
        project = db.query(Project).filter(Project.id == entity.project_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Entity nicht gefunden")
        assert_team_visible(project.team_id, user, db, "Entity nicht gefunden")
        assert_project_visible(entity.project_id, user, db)
        # Team-/Projekt-Mitgliedschaft ist die Basis-Sichtbarkeit, reicht aber allein nicht
        # -- außerhalb des eigenen Projekt-Kontexts (kein project_context_id oder ein ANDERES
        # Projekt, z.B. "Allgemein"-Suche/-Graph-View) braucht das Projekt zusätzlich das
        # explizite Opt-in expose_code_analysis_globally. Siehe core/projects.py.
        assert_project_code_visible_in_context(
            entity.project_id, project_context_id, db, "Entity nicht gefunden"
        )
    if entity.source_id is not None:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == entity.source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Entity nicht gefunden")
        assert_knowledge_source_visible(source, user, db, "Entity nicht gefunden")


def entity_json(entity: CodeEntity) -> dict:
    return {
        "id": entity.id,
        "project_id": entity.project_id,
        "source_id": entity.source_id,
        "variant_key": entity.variant_key,
        "parent_id": entity.parent_id,
        "name": entity.name,
        "qualified_name": entity.qualified_name,
        "type": entity.type,
        "file_path": entity.file_path,
        "start_line": entity.start_line,
        "end_line": entity.end_line,
        "meta": entity.meta_json or {},
    }


def _edge_reference_json(edge: CodeEdge, source: CodeEntity | None) -> dict:
    """Return the concrete source occurrence without inventing a target.

    ``CodeEdge.dst_entity_id`` is deliberately optional for unresolved and
    dynamic references.  The source occurrence is still safe to navigate to:
    it comes from the persisted edge evidence and is independent of target
    resolution.
    """
    start_line = edge.src_start_line if edge.src_start_line and edge.src_start_line > 0 else None
    end_line = edge.src_end_line if edge.src_end_line and edge.src_end_line > 0 else None
    return {
        "entity_id": edge.src_entity_id,
        "name": source.name if source else None,
        "file_path": source.file_path if source else None,
        "source_id": source.source_id if source else edge.source_id,
        "start_line": start_line,
        "end_line": end_line,
    }


def _definition(entity: CodeEntity, db: Session) -> dict | None:
    query = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == entity.project_id,
        DocumentChunk.source_id == entity.source_id,
        DocumentChunk.file_path == entity.file_path,
    )
    if entity.start_line is not None and entity.end_line is not None:
        query = query.filter(
            DocumentChunk.start_line <= entity.end_line,
            DocumentChunk.end_line >= entity.start_line,
        )
    chunk = query.order_by(DocumentChunk.start_line, DocumentChunk.id).first()
    if not chunk:
        return None
    return {
        "chunk_id": chunk.id,
        "content": chunk.content,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
    }


def _select_file_root(file_entities: list[CodeEntity], path: str) -> CodeEntity | None:
    """Select a language-neutral file root, with legacy COBOL fallback."""
    entity = next(
        (
            candidate
            for candidate in file_entities
            if (candidate.meta_json or {}).get("is_file_root")
        ),
        None,
    )
    if entity is not None:
        return entity

    # Compatibility for entities persisted before the shared root marker was
    # introduced. New parsers should set is_file_root.
    suffix = PurePosixPath(path).suffix.lower()
    wanted_type = "copybook" if suffix in {".cpy", ".copy"} else "program"
    return next((candidate for candidate in file_entities if candidate.type == wanted_type), None)


@router.get("/resolve")
def resolve_entity(
    source_id: int,
    path: str,
    project_id: int | None = Query(
        default=None,
        description="Aktueller Projekt-Kontext des Aufrufers (z.B. Code-Editor); None im Allgemein-Modus",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Quelle nicht gefunden")
    assert_team_visible(source.team_id, user, db, "Quelle nicht gefunden")
    file_entities = (
        db.query(CodeEntity)
        .filter(
            CodeEntity.source_id == source_id,
            CodeEntity.file_path == path,
        )
        .order_by(CodeEntity.id)
        .all()
    )
    entity = _select_file_root(file_entities, path)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity nicht gefunden")
    _assert_entity_visible(entity, user, db, project_id)
    return entity_json(entity)


@router.get("/{entity_id}")
def get_entity(
    entity_id: int,
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
    return {**entity_json(entity), "definition": _definition(entity, db)}


@router.get("/{entity_id}/neighbors")
def get_neighbors(
    entity_id: int,
    types: list[str] | None = Query(default=None),
    direction: str = Query(default="both", pattern="^(in|out|both)$"),
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
    requested = {item.upper() for value in (types or []) for item in value.split(",") if item}
    clauses = []
    if direction in {"out", "both"}:
        clauses.append(CodeEdge.src_entity_id == entity_id)
    if direction in {"in", "both"}:
        clauses.append(CodeEdge.dst_entity_id == entity_id)
    query = db.query(CodeEdge).filter(or_(*clauses))
    if requested:
        query = query.filter(CodeEdge.type.in_(requested))
    groups: dict[str, list[dict]] = {}
    for edge in query.order_by(CodeEdge.type, CodeEdge.id).all():
        edge_direction = "out" if edge.src_entity_id == entity_id else "in"
        other_id = edge.dst_entity_id if edge_direction == "out" else edge.src_entity_id
        other = db.query(CodeEntity).filter(CodeEntity.id == other_id).first() if other_id else None
        source = db.query(CodeEntity).filter(CodeEntity.id == edge.src_entity_id).first()
        key = f"{edge.type}:{edge_direction}"
        groups.setdefault(key, []).append(
            {
                "edge_id": edge.id,
                "type": edge.type,
                "direction": edge_direction,
                "resolution": edge.resolution,
                "variant_key": edge.variant_key,
                "meta": edge.meta_json or {},
                "dst_name": edge.dst_name,
                "entity": entity_json(other) if other else None,
                "reference": _edge_reference_json(edge, source),
                "start_line": edge.src_start_line,
                "end_line": edge.src_end_line,
            }
        )

    # CONTAINS is derived from the bounded parent chain rather than persisted
    # as a second edge row.  We expose ancestors only: selecting a broad
    # program must not expand into every paragraph/data item in the project.
    if direction in {"in", "both"} and (not requested or "CONTAINS" in requested):
        parent_id = entity.parent_id
        contains_count = 0
        while parent_id is not None and contains_count < 32:
            parent = db.query(CodeEntity).filter(CodeEntity.id == parent_id).first()
            if not parent:
                break
            try:
                _assert_entity_visible(parent, user, db, project_id)
            except HTTPException:
                break
            groups.setdefault("CONTAINS:in", []).append(
                {
                    "edge_id": f"contains:{entity.id}:{parent.id}",
                    "type": "CONTAINS",
                    "direction": "in",
                    "resolution": "resolved",
                    "variant_key": entity.variant_key,
                    "meta": {},
                    "dst_name": parent.name,
                    "entity": entity_json(parent),
                    "reference": None,
                    "start_line": entity.start_line,
                    "end_line": entity.end_line,
                }
            )
            contains_count += 1
            parent_id = parent.parent_id

    # Dokument-Verknüpfungen dieser Entity (EntityDocLink) als eigene Gruppe --
    # CodeEdge bildet nur Code<->Code-Beziehungen ab, die Graph-View (api/graph.py)
    # zeichnet für dieselbe Entity aber zusätzlich Kanten zu verlinkten Dokumenten
    # (z.B. README.md). Ohne diese Gruppe zeigte dieser Endpunkt -- und damit der
    # "Referenzen"-Dropdown im Code-Editor -- genau diese Dokument-Kanten nicht an,
    # obwohl die Graph-View sie darstellt (siehe docs/ENTSCHEIDUNGEN.md).
    doc_links = []
    if direction in {"out", "both"} and (not requested or "DOC" in requested):
        doc_link_query = db.query(EntityDocLink).filter(
            EntityDocLink.entity_id == entity_id,
            EntityDocLink.status == "approved",
        )
        if entity.project_id is not None:
            doc_link_query = doc_link_query.filter(EntityDocLink.project_id == entity.project_id)
        doc_links = doc_link_query.all()
    chunk_ids = {lnk.chunk_id for lnk in doc_links if lnk.chunk_id is not None}
    chunks = (
        {c.id: c for c in db.query(DocumentChunk).filter(DocumentChunk.id.in_(chunk_ids)).all()}
        if chunk_ids
        else {}
    )
    source_ids = {chunk.source_id for chunk in chunks.values() if chunk.source_id is not None}
    sources = (
        {
            source.id: source
            for source in db.query(KnowledgeSource)
            .filter(KnowledgeSource.id.in_(source_ids))
            .all()
        }
        if source_ids
        else {}
    )
    for lnk in doc_links:
        chunk = chunks.get(lnk.chunk_id)
        source = sources.get(chunk.source_id) if chunk else None
        try:
            if lnk.project_id is not None:
                assert_project_visible(lnk.project_id, user, db, "Entity nicht gefunden")
            if source:
                assert_knowledge_source_visible(source, user, db, "Entity nicht gefunden")
        except HTTPException:
            # A single inaccessible linked source must not leak its metadata or
            # suppress otherwise visible neighbors for this entity.
            continue
        metadata = chunk.metadata_json if chunk and isinstance(chunk.metadata_json, dict) else {}
        document_url = lnk.doc_url or metadata.get("url")
        url_anchor = (
            metadata.get("url_anchor")
            or metadata.get("anchor")
            or _url_fragment(document_url if isinstance(document_url, str) else None)
            or _url_fragment(chunk.file_path if chunk else None)
            or None
        )
        source_spaces = source.spaces if source and isinstance(source.spaces, dict) else {}
        sync_cursor = source.sync_cursor if source and isinstance(source.sync_cursor, dict) else {}
        source_revision = (
            metadata.get("source_revision")
            or sync_cursor.get("last_commit")
            or source_spaces.get("last_commit_hash")
            or metadata.get("content_hash")
        )
        page = metadata.get("page")
        section = metadata.get("section")
        if url_anchor:
            locator_precision = "url_anchor"
        elif page is not None:
            locator_precision = "page"
        elif section:
            locator_precision = "section"
        elif chunk and (chunk.start_line is not None or chunk.end_line is not None):
            locator_precision = "line_range"
        elif chunk:
            locator_precision = "chunk"
        elif document_url:
            locator_precision = "url"
        else:
            locator_precision = "title"
        groups.setdefault("DOC:out", []).append(
            {
                "edge_id": f"edl:{lnk.id}",
                "type": "DOC",
                "direction": "out",
                "resolution": None,
                "dst_name": lnk.doc_title,
                "entity": None,
                "document": {
                    "title": lnk.doc_title,
                    # Keep the stored path byte-for-byte. Some sources carry a
                    # fragment in the path itself, and splitting on '#' here
                    # silently discarded that locator before the viewer saw it.
                    "file_path": chunk.file_path if chunk and chunk.file_path else None,
                    # source_id der Wissensquelle des Chunks -- das Frontend braucht sie, um das
                    # Dokument über ein Doku-Panel zu öffnen (siehe onDocFocus in SplitPaneWorkspace).
                    "source_id": chunk.source_id if chunk else None,
                    "chunk_id": chunk.id if chunk else lnk.chunk_id,
                    "start_line": chunk.start_line if chunk else None,
                    "end_line": chunk.end_line if chunk else None,
                    "page": page,
                    "section": section,
                    "url": document_url,
                    "url_anchor": url_anchor,
                    "source_revision": source_revision,
                    "locator_precision": locator_precision,
                    "excerpt": chunk.content[:1200] if chunk and chunk.content else None,
                    "source_type": lnk.source_type or (source.type if source else None),
                    "score": lnk.score,
                    "link_type": lnk.link_type,
                },
                "start_line": None,
                "end_line": None,
            }
        )

    return {"entity": entity_json(entity), "groups": groups}
