"""
backend/services/search.py
============================
Cross-type search across Project, CodeEntity, KnowledgeSource, and DocumentChunk.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from core.projects import build_document_chunk_code_gate, get_globally_exposed_project_ids
from models.database import Project, CodeEntity, DocumentChunk, KnowledgeSource

ALL_TYPES = "project,entity,document,knowledge_source"


def search_nodes(
    db: Session,
    q: str = "",
    types: str = ALL_TYPES,
    project_id: Optional[int] = None,
    source_id: Optional[int] = None,
    limit: int = 10,
    visible_team_ids: Optional[list[int]] = None,
    visible_project_ids: Optional[list[int]] = None,
):
    """
    Searches across different tables for matches with `q`.
    Returns a list of standardized node objects and hit counts per type.
    """
    wanted = set(t.strip() for t in types.split(","))
    if "repository" in wanted:
        wanted.remove("repository")
        wanted.add("project")

    results = []
    counts = {}

    # 1. Search Projects
    if "project" in wanted and not source_id:
        query = db.query(Project).filter(Project.name.ilike(f"%{q}%"))
        if project_id:
            query = query.filter(Project.id == project_id)
        if visible_team_ids is not None:
            query = query.filter(Project.team_id.in_(visible_team_ids))
        if visible_project_ids is not None:
            query = query.filter(Project.id.in_(visible_project_ids))
        counts["project"] = query.count()
        for p in query.order_by(Project.name).limit(limit).all():
            results.append({
                "node_type": "project",
                "node_id": p.id,
                "node_label": p.name,
                "node_url": None,
                "node_meta": {"is_archived": p.is_archived},
            })

    # 2. Search Code Entities (paragraphs, sections, variables)
    if "entity" in wanted and not source_id:
        query = db.query(CodeEntity).filter(or_(
            CodeEntity.name.ilike(f"%{q}%"),
            CodeEntity.file_path.ilike(f"%{q}%"),
        ))
        if project_id:
            query = query.filter(CodeEntity.project_id == project_id)
        else:
            # Kein Projekt-Kontext ("Allgemein") -- Code-Analyse-Objekte anderer Projekte
            # tauchen hier nur auf, wenn ihr Projekt explizit dafür freigegeben ist (siehe
            # core/projects.py::get_globally_exposed_project_ids), zusätzlich zur normalen
            # Team-/Projekt-Sichtbarkeit. Projektlose Entities (project_id IS NULL, z.B.
            # eigenständige Git-Wissensquellen) bleiben davon unberührt.
            exposed_project_ids = get_globally_exposed_project_ids(db)
            if visible_project_ids is not None:
                exposed_project_ids = [pid for pid in exposed_project_ids if pid in visible_project_ids]
            elif visible_team_ids is not None:
                team_project_ids = {p[0] for p in db.query(Project.id).filter(Project.team_id.in_(visible_team_ids)).all()}
                exposed_project_ids = [pid for pid in exposed_project_ids if pid in team_project_ids]
            query = query.filter(or_(
                CodeEntity.project_id.in_(exposed_project_ids),
                CodeEntity.project_id == None
            ))
        counts["entity"] = query.count()
        for e in query.order_by(CodeEntity.name).limit(limit).all():
            results.append({
                "node_type": "entity",
                "node_id": e.id,
                "node_label": e.name,
                "node_url": None,
                "node_meta": {
                    "type": e.type,
                    "file_path": e.file_path,
                    # Code-Dateien können aus einer eigenständigen Git-
                    # KnowledgeSource stammen (project_id/repo_id ist dann
                    # absichtlich NULL). Das Frontend braucht source_id, um
                    # den Worktree-Inhalt über /knowledge-sources/{id}/content
                    # statt über den alten Repository-Endpunkt zu laden.
                    "source_id": e.source_id,
                    "project_id": e.project_id,
                    "start_line": e.start_line,
                },
            })

    # 3. Search Knowledge Sources (Confluence spaces, Jira projects)
    if "knowledge_source" in wanted and not source_id:
        query = db.query(KnowledgeSource).filter(KnowledgeSource.name.ilike(f"%{q}%"))
        if project_id:
            query = query.filter(KnowledgeSource.project_id == project_id)
        if visible_project_ids is not None:
            query = query.filter(
                or_(
                    KnowledgeSource.project_id.in_(visible_project_ids),
                    KnowledgeSource.project_id == None
                )
            )
        if visible_team_ids is not None:
            query = query.filter(KnowledgeSource.team_id.in_(visible_team_ids))
        counts["knowledge_source"] = query.count()
        for s in query.order_by(KnowledgeSource.name).limit(limit).all():
            results.append({
                "node_type": "knowledge_source",
                "node_id": s.id,
                "node_label": s.name,
                "node_url": s.url,
                "node_meta": {"type": s.type, "project_id": s.project_id},
            })

    # 4. Search Document Chunks (Wiki pages, PDFs, etc.)
    if "document" in wanted and q:
        chunk_filter = db.query(DocumentChunk).filter(or_(
            DocumentChunk.file_path.ilike(f"%{q}%"),
            DocumentChunk.metadata_json['title'].as_string().ilike(f"%{q}%"),
        ))
        if project_id:
            chunk_filter = chunk_filter.filter(DocumentChunk.project_id == project_id)
        else:
            # Dieselbe Opt-in-Einschränkung wie bei CodeEntity oben, aber nur für Chunks
            # aus einer Git-Wissensquelle (rohe Repo-Quelldateien = Code-Analyse-Inhalt).
            # Echte Doku-Quellen (Confluence/Jira/Upload) bleiben unverändert projekt-
            # übergreifend durchsuchbar.
            exposed_project_ids = get_globally_exposed_project_ids(db)
            if visible_project_ids is not None:
                exposed_project_ids = [pid for pid in exposed_project_ids if pid in visible_project_ids]
            elif visible_team_ids is not None:
                team_project_ids = {p[0] for p in db.query(Project.id).filter(Project.team_id.in_(visible_team_ids)).all()}
                exposed_project_ids = [pid for pid in exposed_project_ids if pid in team_project_ids]
            gate = build_document_chunk_code_gate(db, exposed_project_ids)
            if gate is not None:
                chunk_filter = chunk_filter.filter(gate)
        if source_id:
            chunk_filter = chunk_filter.filter(DocumentChunk.source_id == source_id)
        if visible_project_ids is not None:
            chunk_filter = chunk_filter.filter(
                or_(
                    DocumentChunk.project_id.in_(visible_project_ids),
                    DocumentChunk.project_id == None
                )
            )
        elif visible_team_ids is not None:
            project_ids = [p[0] for p in db.query(Project.id).filter(Project.team_id.in_(visible_team_ids)).all()]
            chunk_filter = chunk_filter.filter(DocumentChunk.project_id.in_(project_ids))

        counts["document"] = (
            chunk_filter.with_entities(func.count(func.distinct(DocumentChunk.file_path))).scalar() or 0
        )

        min_ids = (
            chunk_filter
            .with_entities(func.min(DocumentChunk.id).label("id"))
            .group_by(DocumentChunk.file_path)
            .limit(limit)
            .subquery()
        )
        docs = db.query(DocumentChunk).filter(DocumentChunk.id.in_(min_ids)).all()
        for d in docs:
            meta = d.metadata_json or {}
            title = meta.get("title") or d.file_path
            results.append({
                "node_type": "document",
                "node_id": d.id,
                "node_label": title,
                "node_url": meta.get("url"),
                "node_meta": {
                    "source_type": meta.get("source_type"),
                    "file_path": d.file_path,
                    "source_id": d.source_id,
                    "project_id": d.project_id,
                },
            })

    return results, counts
