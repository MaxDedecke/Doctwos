"""
backend/api/projects.py
=======================
Router für die Projekt-Ressourcen.
Verwaltet Projekte, Git-Verbindungen, Projekt-Mitglieder und Zugriffsanfragen.
"""

import os
import shutil
import logging
import random
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, aliased
from sqlalchemy import and_, or_

from core.db_setup import get_db
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids, assert_team_visible, is_admin
from core.projects import assert_project_visible, get_visible_project_ids, ALLOWED_PROJECT_ROLES
from models.database import (
    Project,
    ProjectMembership,
    ProjectAccessRequest,
    User,
    TeamMembership,
    KnowledgeSource,
    SourceScanFile,
    DocumentChunk,
    CodeEdge,
    CodeEntity,
    EntityDocLink,
    KnowledgeLink,
)
from api.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectMembershipCreate,
    ProjectMembershipRoleUpdate,
    ProjectAccessRequestUpdate,
    ProjectCompleteRequest,
)
from api.serializers import serialize_project, serialize_source
from core.config import celery_app
from services.reference_search import refs_for_document, refs_for_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])

REPOS_ROOT = "/repos"  # Oder config-wert falls definiert


# Kept as private API aliases for the focused regression tests that predate the
# extraction. Route code has no dependency on the text-search implementation.
def _refs_for_document(project_id, file_path, base_name, db) -> list[dict]:
    return refs_for_document(project_id, file_path, base_name, db)


def _refs_for_file(project_id, file_path, base_name, db) -> list[dict]:
    return refs_for_file(project_id, file_path, base_name, db)


def _default_team_id(db: Session) -> int:
    from models.database import Team

    return db.query(Team.id).filter(Team.name == "Default Team").scalar()


def _is_project_admin(project_id: int, user: User, db: Session) -> bool:
    if is_admin(user):
        return True
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj and proj.creator_id == user.id:
        return True
    membership = (
        db.query(ProjectMembership)
        .filter(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user.id,
            ProjectMembership.role == "admin",
        )
        .first()
    )
    return membership is not None


@router.post("", status_code=201)
def create_project(
    data: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    team_ids = get_visible_team_ids(user, db)
    if data.team_id is not None:
        if team_ids is not None and data.team_id not in team_ids:
            raise HTTPException(status_code=403, detail="Kein Zugriff auf dieses Team")
        team_id = data.team_id
    else:
        if is_admin(user):
            team_id = _default_team_id(db)
        else:
            if team_ids and len(team_ids) == 1:
                team_id = team_ids[0]
            else:
                raise HTTPException(status_code=403, detail="Team-Auswahl erforderlich")

    PROJECT_COLORS = [
        "#4f46e5",
        "#059669",
        "#2563eb",
        "#7c3aed",
        "#db2777",
        "#ea580c",
        "#0891b2",
        "#0d9488",
    ]
    proj = Project(
        name=data.name,
        description=data.description,
        team_id=team_id,
        creator_id=user.id,
        is_archived=False,
        color=data.color or random.choice(PROJECT_COLORS),
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Ersteller automatisch als Admin-Mitglied hinzufügen
    membership = ProjectMembership(user_id=user.id, project_id=proj.id, role="admin")
    db.add(membership)
    db.commit()
    db.refresh(proj)

    return serialize_project(proj)


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    visible_ids = get_visible_project_ids(user, db)
    q = db.query(Project)
    if visible_ids is not None:
        q = q.filter(Project.id.in_(visible_ids))
    return [serialize_project(p) for p in q.all()]


@router.get("/discoverable")
def list_discoverable_projects(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Projects in the user's own team(s) that they aren't a member of yet —
    i.e. what a user can request access to. Distinct from GET /projects,
    which only lists projects the user is already a member of. Must be
    registered before GET /{id} or FastAPI's int path converter would 422
    on the literal "discoverable" segment instead of matching this route."""
    team_ids = get_visible_team_ids(user, db)
    member_project_ids = db.query(ProjectMembership.project_id).filter(
        ProjectMembership.user_id == user.id
    )

    q = db.query(Project).filter(~Project.id.in_(member_project_ids))
    if team_ids is not None:
        q = q.filter(Project.team_id.in_(team_ids))

    return [{"id": p.id, "name": p.name, "description": p.description} for p in q.all()]


@router.get("/{id}/member-candidates")
def list_project_member_candidates(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """List active users from the project's team that can be added.

    Project membership is deliberately layered on top of team membership. A
    project admin therefore gets a scoped candidate list instead of the
    global, superuser-only /users endpoint.
    """
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins können Mitglieder hinzufügen"
        )

    member_ids = db.query(ProjectMembership.user_id).filter(ProjectMembership.project_id == id)
    candidates = (
        db.query(User)
        .join(TeamMembership, TeamMembership.user_id == User.id)
        .filter(
            TeamMembership.team_id == proj.team_id,
            User.is_active.is_(True),
            ~User.id.in_(member_ids),
        )
        .order_by(User.name, User.username)
        .all()
    )
    return [
        {
            "id": candidate.id,
            "name": candidate.name or candidate.email or candidate.username,
            "email": candidate.email,
            "username": candidate.username,
        }
        for candidate in candidates
    ]


@router.get("/{id}")
def get_project(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)
    return serialize_project(proj)


@router.patch("/{id}")
def update_project(
    id: int,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen Projekte bearbeiten")

    if data.name is not None:
        proj.name = data.name
    if data.description is not None:
        proj.description = data.description
    if data.is_archived is not None:
        proj.is_archived = data.is_archived
    if data.color is not None:
        proj.color = data.color
    if data.expose_code_analysis_globally is not None:
        proj.expose_code_analysis_globally = data.expose_code_analysis_globally

    db.commit()
    db.refresh(proj)
    return serialize_project(proj)


@router.delete("/{id}")
def delete_project(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen Projekte löschen")

    # Worktree-Verzeichnisse der Git-Quellen dieses Projekts merken, bevor die
    # KnowledgeSource-Zeilen per ON DELETE CASCADE mitgelöscht werden (AP-3:
    # Bare-Mirror + Worktree unter wt/ks_<source_id>, siehe list_project_files()/
    # get_project_repository_stats() oben — `Project.repository` existiert nicht,
    # ein Projekt kann mehrere Git-Quellen haben).
    git_source_ids = [
        s.id
        for s in db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == id, KnowledgeSource.type == "Git")
        .all()
    ]

    # Alle Bezüge löschen
    db.delete(proj)
    db.commit()

    for source_id in git_source_ids:
        repo_path = os.path.join(REPOS_ROOT, "wt", f"ks_{source_id}")
        if os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
            except Exception as e:
                logger.error(f"Fehler beim Löschen des Worktree-Pfads {repo_path}: {e}")

    return {"message": "Projekt erfolgreich gelöscht"}


@router.post("/{id}/complete")
def complete_project(
    id: int,
    data: ProjectCompleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Closes out a project and decides where the knowledge it produced goes.
    Sources in promote_source_ids become global (project_id=None) so they
    stay reachable from every future project's chat context (see the null
    merge in services/search.py and api/chat.py) as well as from the
    general/non-project context. Everything not promoted stays attached to
    this now-archived project and drops out of both — matching the rule
    that project knowledge isn't implicitly global, only the reverse."""
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins dürfen ein Projekt abschließen"
        )

    promoted_ids: List[int] = []
    if data.promote_source_ids:
        sources = (
            db.query(KnowledgeSource)
            .filter(
                KnowledgeSource.id.in_(data.promote_source_ids), KnowledgeSource.project_id == id
            )
            .all()
        )
        found_ids = {s.id for s in sources}
        missing = set(data.promote_source_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Quellen gehören nicht zu diesem Projekt: {sorted(missing)}",
            )

        for source in sources:
            source.project_id = None

        # DocumentChunk/CodeEntity carry their own denormalized project_id
        # (see models/database.py) — retrieval filters on that column
        # directly, not via a join to knowledge_sources, so it must be
        # cleared too or promoted docs would stay invisible outside the project.
        db.query(DocumentChunk).filter(DocumentChunk.source_id.in_(found_ids)).update(
            {DocumentChunk.project_id: None}, synchronize_session=False
        )
        db.query(CodeEntity).filter(CodeEntity.source_id.in_(found_ids)).update(
            {CodeEntity.project_id: None}, synchronize_session=False
        )
        promoted_ids = sorted(found_ids)

    proj.is_archived = True
    db.commit()
    db.refresh(proj)

    return {"project": serialize_project(proj), "promoted_source_ids": promoted_ids}


# ── Projektbezogene Ressourcenauslese ───────────────────────────────────────


@router.get("/{id}/files")
def list_project_files(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    git_source = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == id, KnowledgeSource.type == "Git")
        .first()
    )
    if not git_source:
        return []

    # The scan journal is authoritative after an import: it also contains
    # skipped/partial files which have no DocumentChunk and would otherwise
    # disappear from the project tree.  This keeps the project listing aligned
    # with GET /knowledge-sources/{id}/files.
    journal_paths = {
        row.file_path.split("#", 1)[0]
        for row in db.query(SourceScanFile.file_path)
        .filter(SourceScanFile.source_id == git_source.id)
        .all()
        if row.file_path
    }
    if journal_paths:
        return sorted(journal_paths)

    # AP-3: Git-Quellen liegen als Worktree unter wt/ks_<id> (Bare-Mirror +
    # Worktree, siehe parser/git_utils.py), nicht mehr flach unter REPOS_ROOT.
    # During the first scan no journal exists yet, so retain a complete,
    # deterministic fallback without Git/build artefacts.
    repo_path = os.path.join(REPOS_ROOT, "wt", f"ks_{git_source.id}")
    if not os.path.exists(repo_path):
        return []
    ignored_dirs = {".git", "node_modules", "__pycache__", ".next", "dist", "build"}
    files = []
    for root, dirs, names in os.walk(repo_path):
        dirs[:] = [directory for directory in dirs if directory not in ignored_dirs]
        files.extend(os.path.relpath(os.path.join(root, name), repo_path) for name in names)
    return sorted(files)


@router.get("/{id}/entities")
def get_project_entities(
    id: int,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    q = db.query(CodeEntity).filter(CodeEntity.project_id == id)
    if type:
        q = q.filter(CodeEntity.type == type)

    return [
        {
            "id": e.id,
            "name": e.name,
            "type": e.type,
            "file_path": e.file_path,
            "start_line": e.start_line,
            "end_line": e.end_line,
            "project_id": e.project_id,
            "source_id": e.source_id,
            "variant_key": e.variant_key,
        }
        for e in q.all()
    ]


# Strukturelle Kanten gehören zum Aufbau der Objekte, nicht zu einer Verwendung im Text.
_NON_USAGE_EDGE_TYPES = {"CONTAINS", "DEFINES", "DECLARES_SOURCE_ROOT", "CONTAINS_MODULE"}
_MAX_FILE_REFERENCES = 6000


@router.get("/{id}/file-references")
def get_file_references(
    id: int,
    file_path: str,
    source_id: Optional[int] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Verwendungen in einer Datei: Stellen im Text (Aufruf, Typname, Import, COPY, Feldzugriff …),
    die auf ein bereits aufgelöstes Objekt des Projekts zeigen. Der Editor macht sie klickbar.

    Java-Kanten tragen Spalten (`src_start_column`/`src_end_column`, 0-basiert), COBOL/JCL-Kanten
    nur Zeilen; dort sucht der Editor den Namen in der Zeile. Kanten, deren Beleg in einer anderen
    Datei liegt (z. B. aus einem eingebundenen Copybook), gehören nicht zu dieser Datei.
    """
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    src = aliased(CodeEntity)
    dst = aliased(CodeEntity)
    query = (
        db.query(CodeEdge, dst)
        .join(src, src.id == CodeEdge.src_entity_id)
        .join(dst, dst.id == CodeEdge.dst_entity_id)
        .filter(
            src.project_id == id,
            dst.project_id == id,
            src.file_path == file_path,
            CodeEdge.src_start_line > 0,
            CodeEdge.type.notin_(_NON_USAGE_EDGE_TYPES),
        )
    )
    if source_id is not None:
        query = query.filter(src.source_id == source_id)
    rows = query.order_by(CodeEdge.src_start_line, CodeEdge.id).limit(_MAX_FILE_REFERENCES + 1).all()

    references = []
    for edge, target in rows[:_MAX_FILE_REFERENCES]:
        meta = edge.meta_json or {}
        evidence_file = ((meta.get("evidence") or {}).get("source") or {}).get("file_path")
        if evidence_file and evidence_file != file_path:
            continue
        references.append(
            {
                "edge_id": edge.id,
                "type": edge.type,
                "dst_name": edge.dst_name,
                "resolution": edge.resolution,
                "line": edge.src_start_line,
                "end_line": edge.src_end_line,
                "start_column": meta.get("src_start_column"),
                "end_column": meta.get("src_end_column"),
                "target": {
                    "id": target.id,
                    "name": target.name,
                    "type": target.type,
                    "file_path": target.file_path,
                    "start_line": target.start_line,
                    "end_line": target.end_line,
                    "project_id": target.project_id,
                    "source_id": target.source_id,
                    "variant_key": target.variant_key,
                },
            }
        )
    return {"references": references, "truncated": len(rows) > _MAX_FILE_REFERENCES}


_EXT_LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".hpp": "C/C++ Header",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".html": "HTML",
    ".htm": "HTML",
    ".css": "CSS",
    ".sh": "Shell",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".xml": "XML",
    ".md": "Markdown",
}


@router.get("/{id}/stats")
def get_project_repository_stats(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    git_source = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == id, KnowledgeSource.type == "Git")
        .first()
    )
    if not git_source:
        return {"total_files": 0, "total_lines": 0, "languages": []}

    # AP-3: Git-Quellen liegen als Worktree unter wt/ks_<id>, siehe list_project_files() oben.
    repo_path = os.path.join(REPOS_ROOT, "wt", f"ks_{git_source.id}")
    if not os.path.exists(repo_path):
        return {"total_files": 0, "total_lines": 0, "languages": []}

    total_files = 0
    total_lines = 0
    language_counts: dict[str, int] = {}

    for root, dirs, files in os.walk(repo_path):
        if ".git" in dirs:
            dirs.remove(".git")
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.islink(file_path):
                continue
            total_files += 1
            lang = _EXT_LANG_MAP.get(os.path.splitext(file)[1].lower(), "Other")
            try:
                with open(file_path, "r", errors="ignore") as f:
                    lines = sum(1 for _ in f)
                total_lines += lines
                language_counts[lang] = language_counts.get(lang, 0) + lines
            except Exception:
                pass

    languages = []
    if total_lines > 0:
        for lang, lines in language_counts.items():
            pct = round((lines / total_lines) * 100, 1)
            if pct > 0:
                languages.append({"name": lang, "lines": lines, "percentage": pct})
        languages.sort(key=lambda x: x["percentage"], reverse=True)

    return {"total_files": total_files, "total_lines": total_lines, "languages": languages}


@router.post("/{id}/sync")
def sync_project_repository(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    git_source = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.project_id == id, KnowledgeSource.type == "Git")
        .first()
    )
    if not git_source:
        raise HTTPException(
            status_code=404, detail="Kein Git-Repository an diesem Projekt konnektiert"
        )

    git_source.sync_status = "pending"
    git_source.progress = 0
    git_source.progress_message = "In Warteschlange…"
    db.commit()
    celery_app.send_task("sync_source", args=[git_source.id])
    return {"message": "Synchronisierung gestartet", "repo_id": git_source.id}


@router.get("/{id}/knowledge-sources")
def get_project_knowledge_sources(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    # Lese projektspezifische Quellen und globale Quellen (project_id IS NULL)
    q = db.query(KnowledgeSource).filter(
        or_(KnowledgeSource.project_id == id, KnowledgeSource.project_id.is_(None)),
        KnowledgeSource.team_id == proj.team_id,
    )
    return [serialize_source(s) for s in q.all()]


def _collect_project_references(
    db: Session, id: int, file_path: str, entity_name: Optional[str]
) -> list[dict]:
    """Alle Referenzen einer Datei (Doku-Verknüpfungen und Wissensverknüpfungen), dedupliziert und in
    stabiler Reihenfolge; Grundlage für den vollständigen und den seitenweisen Endpunkt."""
    base_name = os.path.splitext(os.path.basename(file_path))[0]

    references = []
    seen = set()

    # 1. EntityDocLink targets matching the file_path (document -> entity references)
    ed_targets = (
        db.query(EntityDocLink)
        .join(DocumentChunk, EntityDocLink.chunk_id == DocumentChunk.id)
        .filter(
            EntityDocLink.project_id == id,
            EntityDocLink.status == "approved",
            DocumentChunk.file_path == file_path,
        )
        .order_by(EntityDocLink.id)
        .all()
    )

    # Also find by doc_title matching basename or file_path if chunk is null
    ed_targets_title = (
        db.query(EntityDocLink)
        .filter(
            EntityDocLink.project_id == id,
            EntityDocLink.status == "approved",
            EntityDocLink.chunk_id.is_(None),
            or_(
                EntityDocLink.doc_title.ilike(f"%{base_name}%"),
                EntityDocLink.doc_title.ilike(f"%{file_path}%"),
            ),
        )
        .order_by(EntityDocLink.id)
        .all()
    )

    for lnk in ed_targets + ed_targets_title:
        if lnk.entity and (not entity_name or lnk.entity.name == entity_name):
            key = ("entity", lnk.entity.id)
            if key not in seen:
                seen.add(key)
                references.append(
                    {
                        "id": f"entity:{lnk.entity.id}",
                        "node_type": "entity",
                        "name": lnk.entity.name,
                        "title": lnk.entity.name,
                        "file_path": lnk.entity.file_path,
                        "line": lnk.entity.start_line,
                        "source_id": lnk.entity.source_id,
                        "source": "Git",
                        "preview": lnk.context
                        or f"Code-Objekt ({lnk.entity.type}) verknüpft mit Dokument",
                        "score": lnk.score,
                        "link_type": lnk.link_type,
                    }
                )

    # 2. EntityDocLink sources matching the file_path (entity -> document references)
    #    entity_name narrows this to the clicked code object — without it every
    #    entity in the file would report the same reference set.
    ed_sources_q = (
        db.query(EntityDocLink)
        .join(CodeEntity, EntityDocLink.entity_id == CodeEntity.id)
        .filter(
            EntityDocLink.project_id == id,
            EntityDocLink.status == "approved",
            CodeEntity.file_path == file_path,
        )
    )
    if entity_name:
        ed_sources_q = ed_sources_q.filter(CodeEntity.name == entity_name)
    ed_sources = ed_sources_q.order_by(EntityDocLink.id).all()

    for lnk in ed_sources:
        target_path = lnk.chunk.file_path if lnk.chunk else file_path
        key = ("document", lnk.doc_title)
        if key not in seen:
            seen.add(key)
            references.append(
                {
                    "id": f"doc:{lnk.doc_title}",
                    "node_type": "document",
                    "name": lnk.doc_title,
                    "title": lnk.doc_title,
                    "file_path": target_path,
                    "url": lnk.doc_url,
                    "source": lnk.source_type or "Local",
                    "preview": lnk.context or f"Dokument verknüpft mit Code-Objekt in {base_name}",
                    "score": lnk.score,
                    "link_type": lnk.link_type,
                }
            )

    # 3. KnowledgeLink matching the file_path
    # Nur Verknüpfungen laden, die eine Seite dieser Datei berühren (in der Datenbank vorgefiltert):
    # früher wurden ALLE freigegebenen Wissensverknüpfungen geladen und in Python durchsucht.
    chunk_a, chunk_b = aliased(DocumentChunk), aliased(DocumentChunk)
    entity_a, entity_b = aliased(CodeEntity), aliased(CodeEntity)

    def _touches_file(kind_column, chunk, entity):
        entity_conditions = [kind_column == "entity", entity.project_id == id, entity.file_path == file_path]
        if entity_name:
            entity_conditions.append(entity.name == entity_name)
        return or_(
            and_(kind_column == "document", chunk.project_id == id, chunk.file_path == file_path),
            and_(*entity_conditions),
        )

    k_links = (
        db.query(KnowledgeLink)
        .outerjoin(chunk_a, KnowledgeLink.source_a_chunk_id == chunk_a.id)
        .outerjoin(chunk_b, KnowledgeLink.source_b_chunk_id == chunk_b.id)
        .outerjoin(entity_a, KnowledgeLink.source_a_entity_id == entity_a.id)
        .outerjoin(entity_b, KnowledgeLink.source_b_entity_id == entity_b.id)
        .filter(
            KnowledgeLink.status == "approved",
            or_(
                _touches_file(KnowledgeLink.source_a_type, chunk_a, entity_a),
                _touches_file(KnowledgeLink.source_b_type, chunk_b, entity_b),
            ),
        )
        .order_by(KnowledgeLink.id)
        .all()
    )

    for kl in k_links:
        match_a = False
        match_b = False

        # Check side A
        if kl.source_a_type == "document" and kl.source_a_chunk:
            if kl.source_a_chunk.project_id == id and kl.source_a_chunk.file_path == file_path:
                match_a = True
        elif kl.source_a_type == "entity" and kl.source_a_entity:
            if kl.source_a_entity.project_id == id and kl.source_a_entity.file_path == file_path:
                if not entity_name or kl.source_a_entity.name == entity_name:
                    match_a = True

        # Check side B
        if kl.source_b_type == "document" and kl.source_b_chunk:
            if kl.source_b_chunk.project_id == id and kl.source_b_chunk.file_path == file_path:
                match_b = True
        elif kl.source_b_type == "entity" and kl.source_b_entity:
            if kl.source_b_entity.project_id == id and kl.source_b_entity.file_path == file_path:
                if not entity_name or kl.source_b_entity.name == entity_name:
                    match_b = True

        if match_a or match_b:
            ref_side = "b" if match_a else "a"

            if ref_side == "b":
                ref_id = (
                    f"entity:{kl.source_b_entity_id}"
                    if kl.source_b_type == "entity"
                    else f"doc:{kl.source_b_title}"
                )
                key = (kl.source_b_type, ref_id)
                if key not in seen:
                    seen.add(key)
                    references.append(
                        {
                            "id": ref_id,
                            "node_type": kl.source_b_type,
                            "name": kl.source_b_title,
                            "title": kl.source_b_title,
                            "file_path": kl.source_b_chunk.file_path
                            if kl.source_b_chunk
                            else (
                                kl.source_b_entity.file_path
                                if kl.source_b_entity
                                else kl.source_b_title
                            ),
                            "line": kl.source_b_entity.start_line if kl.source_b_entity else None,
                            "source_id": kl.source_b_entity.source_id
                            if kl.source_b_entity
                            else (kl.source_b_chunk.source_id if kl.source_b_chunk else None),
                            "url": kl.source_b_url,
                            "source": kl.source_b_source_type
                            or ("Git" if kl.source_b_type == "entity" else "Local"),
                            "preview": kl.context or "Verknüpfter Knoten",
                            "score": kl.score,
                            "link_type": kl.link_type,
                        }
                    )
            else:
                ref_id = (
                    f"entity:{kl.source_a_entity_id}"
                    if kl.source_a_type == "entity"
                    else f"doc:{kl.source_a_title}"
                )
                key = (kl.source_a_type, ref_id)
                if key not in seen:
                    seen.add(key)
                    references.append(
                        {
                            "id": ref_id,
                            "node_type": kl.source_a_type,
                            "name": kl.source_a_title,
                            "title": kl.source_a_title,
                            "file_path": kl.source_a_chunk.file_path
                            if kl.source_a_chunk
                            else (
                                kl.source_a_entity.file_path
                                if kl.source_a_entity
                                else kl.source_a_title
                            ),
                            "line": kl.source_a_entity.start_line if kl.source_a_entity else None,
                            "source_id": kl.source_a_entity.source_id
                            if kl.source_a_entity
                            else (kl.source_a_chunk.source_id if kl.source_a_chunk else None),
                            "url": kl.source_a_url,
                            "source": kl.source_a_source_type
                            or ("Git" if kl.source_a_type == "entity" else "Local"),
                            "preview": kl.context or "Verknüpfter Knoten",
                            "score": kl.score,
                            "link_type": kl.link_type,
                        }
                    )

    return references


def _assert_project_for_references(db: Session, id: int, user: User) -> None:
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)


@router.get("/{id}/references")
def get_project_references(
    id: int,
    file_path: str,
    entity_name: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _assert_project_for_references(db, id, user)
    return _collect_project_references(db, id, file_path, entity_name)


@router.get("/{id}/references/page")
def get_project_references_page(
    id: int,
    file_path: str,
    entity_name: Optional[str] = None,
    limit: int = Query(default=15, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Referenzen einer Datei seitenweise (für das Referenzen-Menü): ``total`` ist die Gesamtzahl,
    ``has_more`` sagt, ob nach dieser Seite weitere folgen."""
    _assert_project_for_references(db, id, user)
    references = _collect_project_references(db, id, file_path, entity_name)
    page = references[offset : offset + limit]
    return {
        "references": page,
        "total": len(references),
        "has_more": offset + len(page) < len(references),
        "offset": offset,
        "limit": limit,
    }


# ── Zugriffsrechte & Anfragen ───────────────────────────────────────────────


@router.post("/{id}/request-access", status_code=201)
def request_access(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")

    # Überprüfe, ob bereits Mitglied
    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == id, ProjectMembership.user_id == user.id)
        .first()
    )
    if membership:
        return {"message": "Du bist bereits Mitglied dieses Projekts", "status": "approved"}

    # Überprüfe auf bestehende Anfrage
    existing = (
        db.query(ProjectAccessRequest)
        .filter(ProjectAccessRequest.project_id == id, ProjectAccessRequest.user_id == user.id)
        .first()
    )

    if existing:
        return {"message": "Eine Anfrage ist bereits ausstehend", "status": existing.status}

    req = ProjectAccessRequest(project_id=id, user_id=user.id, status="pending")
    db.add(req)
    db.commit()
    db.refresh(req)

    return {"message": "Anfrage erfolgreich an Projekt-Admin gesendet", "status": "pending"}


@router.get("/{id}/access-requests")
def list_access_requests(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins können Zugriffsanfragen einsehen"
        )

    requests = (
        db.query(ProjectAccessRequest)
        .filter(ProjectAccessRequest.project_id == id, ProjectAccessRequest.status == "pending")
        .all()
    )

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": r.user.name or r.user.email,
            "user_email": r.user.email,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in requests
    ]


@router.post("/{id}/access-requests/{request_id}/resolve")
def resolve_access_request(
    id: int,
    request_id: int,
    data: ProjectAccessRequestUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins können Zugriffsanfragen auflösen"
        )

    req = (
        db.query(ProjectAccessRequest)
        .filter(ProjectAccessRequest.id == request_id, ProjectAccessRequest.project_id == id)
        .first()
    )

    if not req:
        raise HTTPException(status_code=404, detail="Zugriffsanfrage nicht gefunden")

    req.status = data.status

    if data.status == "approved":
        # Zu Mitgliedern hinzufügen
        existing = (
            db.query(ProjectMembership)
            .filter(ProjectMembership.project_id == id, ProjectMembership.user_id == req.user_id)
            .first()
        )
        if not existing:
            membership = ProjectMembership(user_id=req.user_id, project_id=id, role="member")
            db.add(membership)

    db.commit()
    return {"message": f"Anfrage wurde {data.status}"}


# ── Projektmitglieder-Verwaltung ──────────────────────────────────────────


@router.get("/{id}/members")
def list_project_members(
    id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    memberships = db.query(ProjectMembership).filter(ProjectMembership.project_id == id).all()
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "user_name": m.user.name or m.user.email,
            "user_email": m.user.email,
            "role": m.role,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in memberships
    ]


@router.post("/{id}/members")
def add_project_member(
    id: int,
    data: ProjectMembershipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins können Mitglieder hinzufügen"
        )

    if data.role not in ALLOWED_PROJECT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Rolle. Erlaubt: {', '.join(sorted(ALLOWED_PROJECT_ROLES))}",
        )

    target_user = db.query(User).filter(User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    team_membership = (
        db.query(TeamMembership)
        .filter(
            TeamMembership.team_id == proj.team_id,
            TeamMembership.user_id == data.user_id,
        )
        .first()
    )
    if not team_membership:
        raise HTTPException(
            status_code=403, detail="Benutzer muss zuerst Mitglied des Projektteams sein"
        )

    existing = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == id, ProjectMembership.user_id == data.user_id)
        .first()
    )

    if existing:
        raise HTTPException(status_code=409, detail="Benutzer ist bereits Mitglied")

    membership = ProjectMembership(user_id=data.user_id, project_id=id, role=data.role)
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "user_name": target_user.name or target_user.email,
        "role": membership.role,
    }


@router.patch("/{id}/members/{user_id}")
def update_project_member_role(
    id: int,
    user_id: int,
    data: ProjectMembershipRoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Rollen ändern")

    if data.role not in ALLOWED_PROJECT_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültige Rolle. Erlaubt: {', '.join(sorted(ALLOWED_PROJECT_ROLES))}",
        )

    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == id, ProjectMembership.user_id == user_id)
        .first()
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")

    membership.role = data.role
    db.commit()
    db.refresh(membership)

    return {"id": membership.id, "user_id": membership.user_id, "role": membership.role}


@router.delete("/{id}/members/{user_id}")
def remove_project_member(
    id: int, user_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(
            status_code=403, detail="Nur Projekt-Admins können Mitglieder entfernen"
        )

    if proj.creator_id == user_id:
        raise HTTPException(
            status_code=400,
            detail="Der Projekt-Ersteller kann nicht aus dem Projekt entfernt werden",
        )

    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == id, ProjectMembership.user_id == user_id)
        .first()
    )

    if not membership:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")

    db.delete(membership)
    db.commit()

    return {"message": "Mitglied erfolgreich entfernt"}
