"""
backend/services/search.py
============================
Cross-type search across Project, CodeEntity, KnowledgeSource, and DocumentChunk.
"""

import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, case, false

from core.projects import build_document_chunk_code_gate, get_globally_exposed_project_ids
from models.database import Project, CodeEntity, DocumentChunk, KnowledgeSource

ALL_TYPES = "project,entity,document,knowledge_source"

# Entities, die eine ganze Datei vertreten. Nur sie dürfen über den Dateinamen gefunden werden;
# sonst passte jede Entity einer Datei (209 bei COPAUA0C) allein wegen des Pfads.
ROOT_ENTITY_TYPES = (
    "program", "copybook", "compilation_unit", "jcl_file", "jcl_job", "xml_document", "xslt_stylesheet",
    "html_document", "jsp_page", "shell_script", "properties_file", "groovy_file", "javascript_file",
    "sql_script", "maven_project", "asciidoc_document",
)
_TOKEN_SPLIT = re.compile(r"[\s.#]+|::")
_MAX_TOKENS = 6
_MAX_TOKEN_LENGTH = 80


def _search_tokens(q: str) -> list[str]:
    """Suchbegriff in Teilbegriffe zerlegen: Leerzeichen sowie `.`, `#`, `::` trennen (`Klasse.methode`)."""
    tokens = [t for t in _TOKEN_SPLIT.split(q or "") if t]
    if len((q or "").split()) <= 1:
        # Ein einzelner qualifizierter Name (`a.b.c.Klasse#methode(Typ)`): das Ende ist der spezifische Teil.
        return [t[:_MAX_TOKEN_LENGTH] for t in tokens[-_MAX_TOKENS:]]
    return [t[:_MAX_TOKEN_LENGTH] for t in tokens[:_MAX_TOKENS]]


def _contains(column, token: str):
    """Teilstring-Suche; `%`, `_` und `\\` aus der Eingabe sind keine Platzhalter."""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _starts_with(column, text: str):
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"{escaped}%", escape="\\")


def _tail(column):
    """Letzter Pfadabschnitt (Dateiname); Ordnernamen zählen bei der Suche nicht."""
    return func.regexp_replace(column, "^.*/", "")


def _project_is_visible(
    db: Session,
    project_id: int,
    visible_team_ids: Optional[list[int]],
    visible_project_ids: Optional[list[int]],
) -> bool:
    """None bedeutet „keine Einschränkung“ (Administratoren)."""
    if visible_project_ids is not None and project_id not in visible_project_ids:
        return False
    if visible_team_ids is not None:
        team_id = db.query(Project.team_id).filter(Project.id == project_id).scalar()
        return team_id in visible_team_ids
    return True


def search_nodes(
    db: Session,
    q: str = "",
    types: str = ALL_TYPES,
    project_id: Optional[int] = None,
    source_id: Optional[int] = None,
    limit: int = 10,
    visible_team_ids: Optional[list[int]] = None,
    visible_project_ids: Optional[list[int]] = None,
    count_total: bool = True,
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
            results.append(
                {
                    "node_type": "project",
                    "node_id": p.id,
                    "node_label": p.name,
                    "node_url": None,
                    "node_meta": {"is_archived": p.is_archived},
                }
            )

    # 2. Search Code Entities (paragraphs, sections, variables)
    if "entity" in wanted:
        tokens = _search_tokens(q)
        qualified_tail = _tail(CodeEntity.qualified_name)
        file_name = _tail(CodeEntity.file_path)
        query = db.query(CodeEntity)
        for token in tokens:
            # Treffer über Name, Qualified Name ohne Pfadanteil oder (nur Datei-Entities) Dateiname.
            query = query.filter(or_(
                _contains(CodeEntity.name, token),
                _contains(qualified_tail, token),
                and_(CodeEntity.type.in_(ROOT_ENTITY_TYPES), _contains(file_name, token)),
            ))
        if source_id:
            query = query.filter(CodeEntity.source_id == source_id)
        if project_id:
            query = query.filter(CodeEntity.project_id == project_id)
            # Ein explizit genanntes Projekt darf nicht an der Sichtbarkeit vorbei
            # durchsucht werden (Nicht-Admins sahen sonst fremde Code-Entities).
            if not _project_is_visible(db, project_id, visible_team_ids, visible_project_ids):
                query = query.filter(false())
        else:
            # Kein Projekt-Kontext ("Allgemein") -- Code-Analyse-Objekte anderer Projekte
            # tauchen hier nur auf, wenn ihr Projekt explizit dafür freigegeben ist (siehe
            # core/projects.py::get_globally_exposed_project_ids), zusätzlich zur normalen
            # Team-/Projekt-Sichtbarkeit. Projektlose Entities (project_id IS NULL, z.B.
            # eigenständige Git-Wissensquellen) bleiben davon unberührt.
            exposed_project_ids = get_globally_exposed_project_ids(db)
            if visible_project_ids is not None:
                exposed_project_ids = [
                    pid for pid in exposed_project_ids if pid in visible_project_ids
                ]
            elif visible_team_ids is not None:
                team_project_ids = {
                    p[0]
                    for p in db.query(Project.id)
                    .filter(Project.team_id.in_(visible_team_ids))
                    .all()
                }
                exposed_project_ids = [
                    pid for pid in exposed_project_ids if pid in team_project_ids
                ]
            query = query.filter(
                or_(CodeEntity.project_id.in_(exposed_project_ids), CodeEntity.project_id.is_(None))
            )
        if count_total:
            counts["entity"] = query.count()
        if tokens:
            phrase = q.strip()
            match_score = case(
                (func.lower(CodeEntity.name) == func.lower(phrase), 0),
                (_starts_with(CodeEntity.name, phrase), 1),
                (and_(*[_contains(CodeEntity.name, token) for token in tokens]), 2),
                (and_(*[_contains(qualified_tail, token) for token in tokens]), 3),
                else_=4,
            )
            type_score = case(
                (
                    CodeEntity.type.in_(
                        [
                            "program",
                            "class",
                            "interface",
                            "copybook",
                            "compilation_unit",
                            "shell_script",
                            "maven_project",
                            "maven_module",
                            "package",
                        ]
                    ),
                    0,
                ),
                (
                    CodeEntity.type.in_(
                        [
                            "section",
                            "paragraph",
                            "method",
                            "constructor",
                            "sql_block",
                            "sql_table",
                        ]
                    ),
                    1,
                ),
                else_=2,
            )
            entity_ordering = (
                match_score,
                type_score,
                func.length(CodeEntity.name),
                CodeEntity.name,
            )
        else:
            entity_ordering = (CodeEntity.name,)
        for e in query.order_by(*entity_ordering).limit(limit).all():
            results.append(
                {
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
                }
            )

    # 3. Search Knowledge Sources (Confluence spaces, Jira projects)
    if "knowledge_source" in wanted and not source_id:
        query = db.query(KnowledgeSource).filter(KnowledgeSource.name.ilike(f"%{q}%"))
        if project_id:
            query = query.filter(KnowledgeSource.project_id == project_id)
        if visible_project_ids is not None:
            query = query.filter(
                or_(
                    KnowledgeSource.project_id.in_(visible_project_ids),
                    KnowledgeSource.project_id.is_(None),
                )
            )
        if visible_team_ids is not None:
            query = query.filter(KnowledgeSource.team_id.in_(visible_team_ids))
        counts["knowledge_source"] = query.count()
        for s in query.order_by(KnowledgeSource.name).limit(limit).all():
            results.append(
                {
                    "node_type": "knowledge_source",
                    "node_id": s.id,
                    "node_label": s.name,
                    "node_url": s.url,
                    "node_meta": {"type": s.type, "project_id": s.project_id},
                }
            )

    # 4. Search Document Chunks (Wiki pages, PDFs, etc.)
    if "document" in wanted and _search_tokens(q):
        doc_tokens = _search_tokens(q)
        doc_title = DocumentChunk.metadata_json["title"].as_string()
        doc_file_name = _tail(DocumentChunk.file_path)
        chunk_filter = db.query(DocumentChunk)
        for token in doc_tokens:
            # Titel oder Dateiname; ein Ordnername allein macht ein Dokument nicht zum Treffer.
            chunk_filter = chunk_filter.filter(or_(_contains(doc_title, token), _contains(doc_file_name, token)))
        if project_id:
            chunk_filter = chunk_filter.filter(DocumentChunk.project_id == project_id)
        else:
            # Dieselbe Opt-in-Einschränkung wie bei CodeEntity oben, aber nur für Chunks
            # aus einer Git-Wissensquelle (rohe Repo-Quelldateien = Code-Analyse-Inhalt).
            # Echte Doku-Quellen (Confluence/Jira/Upload) bleiben unverändert projekt-
            # übergreifend durchsuchbar.
            exposed_project_ids = get_globally_exposed_project_ids(db)
            if visible_project_ids is not None:
                exposed_project_ids = [
                    pid for pid in exposed_project_ids if pid in visible_project_ids
                ]
            elif visible_team_ids is not None:
                team_project_ids = {
                    p[0]
                    for p in db.query(Project.id)
                    .filter(Project.team_id.in_(visible_team_ids))
                    .all()
                }
                exposed_project_ids = [
                    pid for pid in exposed_project_ids if pid in team_project_ids
                ]
            gate = build_document_chunk_code_gate(db, exposed_project_ids)
            if gate is not None:
                chunk_filter = chunk_filter.filter(gate)
        if source_id:
            chunk_filter = chunk_filter.filter(DocumentChunk.source_id == source_id)
        if visible_project_ids is not None:
            chunk_filter = chunk_filter.filter(
                or_(
                    DocumentChunk.project_id.in_(visible_project_ids),
                    DocumentChunk.project_id.is_(None),
                )
            )
        elif visible_team_ids is not None:
            project_ids = [
                p[0]
                for p in db.query(Project.id).filter(Project.team_id.in_(visible_team_ids)).all()
            ]
            chunk_filter = chunk_filter.filter(DocumentChunk.project_id.in_(project_ids))

        counts["document"] = (
            chunk_filter.with_entities(func.count(func.distinct(DocumentChunk.file_path))).scalar()
            or 0
        )

        doc_phrase = q.strip()
        doc_rank = case(
            (func.lower(doc_title) == func.lower(doc_phrase), 0),
            (_starts_with(doc_title, doc_phrase), 1),
            (and_(*[_contains(doc_title, token) for token in doc_tokens]), 2),
            (func.lower(doc_file_name) == func.lower(doc_phrase), 3),
            else_=4,
        )
        # Je Datei der beste Rang und der erste Chunk; erst dann begrenzen, damit die
        # Seite die besten Treffer enthält und nicht eine beliebige Auswahl.
        ranked = (
            chunk_filter.with_entities(
                func.min(DocumentChunk.id).label("id"),
                func.min(doc_rank).label("rank"),
                DocumentChunk.file_path.label("file_path"),
            )
            .group_by(DocumentChunk.file_path)
            .order_by("rank", "file_path")
            .limit(limit)
            .subquery()
        )
        docs = (
            db.query(DocumentChunk)
            .join(ranked, DocumentChunk.id == ranked.c.id)
            .order_by(ranked.c.rank, ranked.c.file_path)
            .all()
        )
        for d in docs:
            meta = d.metadata_json or {}
            title = meta.get("title") or d.file_path
            results.append(
                {
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
                }
            )

    return results, counts
