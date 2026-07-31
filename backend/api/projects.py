"""
backend/api/projects.py
=======================
Router für die Projekt-Ressourcen.
Verwaltet Projekte, Git-Verbindungen, Projekt-Mitglieder und Zugriffsanfragen.
"""

import os
import re
import shutil
import logging
import random
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import or_

import core.config as cfg
from core.db_setup import get_db
from core.auth_dependency import get_current_user
from core.teams import get_visible_team_ids, assert_team_visible, is_admin
from core.projects import assert_project_visible, get_visible_project_ids, ALLOWED_PROJECT_ROLES
from models.database import (
    Project, ProjectMembership, ProjectAccessRequest, User,
    KnowledgeSource, DocumentChunk, CodeEntity, EntityDocLink, KnowledgeLink
)
from api.schemas import (
    ProjectCreate, ProjectUpdate, ProjectMembershipCreate,
    ProjectMembershipRoleUpdate, ProjectAccessRequestUpdate, ProjectCompleteRequest
)
from api.serializers import (
    serialize_project, serialize_source, serialize_link
)
from core.config import celery_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects", tags=["projects"])

REPOS_ROOT = "/repos"  # Oder config-wert falls definiert

def _default_team_id(db: Session) -> int:
    from models.database import Team
    return db.query(Team.id).filter(Team.name == "Default Team").scalar()

def _is_project_admin(project_id: int, user: User, db: Session) -> bool:
    if is_admin(user):
        return True
    proj = db.query(Project).filter(Project.id == project_id).first()
    if proj and proj.creator_id == user.id:
        return True
    membership = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == project_id,
        ProjectMembership.user_id == user.id,
        ProjectMembership.role == "admin"
    ).first()
    return membership is not None

@router.post("", status_code=201)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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

    PROJECT_COLORS = ["#4f46e5", "#059669", "#2563eb", "#7c3aed", "#db2777", "#ea580c", "#0891b2", "#0d9488"]
    proj = Project(
        name=data.name,
        description=data.description,
        team_id=team_id,
        creator_id=user.id,
        is_archived=False,
        color=data.color or random.choice(PROJECT_COLORS)
    )
    db.add(proj)
    db.commit()
    db.refresh(proj)

    # Ersteller automatisch als Admin-Mitglied hinzufügen
    membership = ProjectMembership(
        user_id=user.id,
        project_id=proj.id,
        role="admin"
    )
    db.add(membership)
    db.commit()
    db.refresh(proj)

    return serialize_project(proj)

@router.get("")
def list_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    visible_ids = get_visible_project_ids(user, db)
    q = db.query(Project)
    if visible_ids is not None:
        q = q.filter(Project.id.in_(visible_ids))
    return [serialize_project(p) for p in q.all()]

@router.get("/discoverable")
def list_discoverable_projects(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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

    return [
        {"id": p.id, "name": p.name, "description": p.description}
        for p in q.all()
    ]

@router.get("/{id}")
def get_project(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
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
    user: User = Depends(get_current_user)
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
        
    db.commit()
    db.refresh(proj)
    return serialize_project(proj)

@router.delete("/{id}")
def delete_project(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)
    
    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen Projekte löschen")

    # Git-Klonverzeichnis aufräumen falls vorhanden
    repo = proj.repository
    repo_id = repo.id if repo else None

    # Alle Bezüge löschen
    db.delete(proj)
    db.commit()

    if repo_id:
        repo_path = os.path.join(REPOS_ROOT, str(repo_id))
        if os.path.exists(repo_path):
            try:
                shutil.rmtree(repo_path)
            except Exception as e:
                logger.error(f"Fehler beim Löschen des Git-Klonpfads {repo_path}: {e}")

    return {"message": "Projekt erfolgreich gelöscht"}

@router.post("/{id}/complete")
def complete_project(
    id: int,
    data: ProjectCompleteRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins dürfen ein Projekt abschließen")

    promoted_ids: List[int] = []
    if data.promote_source_ids:
        sources = db.query(KnowledgeSource).filter(
            KnowledgeSource.id.in_(data.promote_source_ids),
            KnowledgeSource.project_id == id
        ).all()
        found_ids = {s.id for s in sources}
        missing = set(data.promote_source_ids) - found_ids
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Quellen gehören nicht zu diesem Projekt: {sorted(missing)}"
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

    return {
        "project": serialize_project(proj),
        "promoted_source_ids": promoted_ids
    }



# ── Projektbezogene Ressourcenauslese ───────────────────────────────────────

@router.get("/{id}/files")
def list_project_files(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    git_source = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == id,
        KnowledgeSource.type == "Git"
    ).first()
    if not git_source:
        return []

    # AP-3: Git-Quellen liegen als Worktree unter wt/ks_<id> (Bare-Mirror +
    # Worktree, siehe parser/git_utils.py), nicht mehr flach unter REPOS_ROOT.
    repo_path = os.path.join(REPOS_ROOT, "wt", f"ks_{git_source.id}")
    if not os.path.exists(repo_path):
        return []
    return [
        os.path.relpath(os.path.join(root, f), repo_path)
        for root, _, files in os.walk(repo_path)
        for f in files
    ]

@router.get("/{id}/entities")
def get_project_entities(
    id: int,
    type: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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
            "source_id": e.source_id
        }
        for e in q.all()
    ]

_EXT_LANG_MAP = {
    ".py": "Python",
    ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".c": "C", ".cpp": "C++", ".h": "C/C++ Header", ".hpp": "C/C++ Header",
    ".go": "Go", ".rs": "Rust", ".cs": "C#", ".php": "PHP", ".rb": "Ruby",
    ".html": "HTML", ".htm": "HTML", ".css": "CSS", ".sh": "Shell",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".xml": "XML", ".md": "Markdown",
}

@router.get("/{id}/stats")
def get_project_repository_stats(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)
    
    git_source = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == id,
        KnowledgeSource.type == "Git"
    ).first()
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
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)
    
    git_source = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == id,
        KnowledgeSource.type == "Git"
    ).first()
    if not git_source:
        raise HTTPException(status_code=404, detail="Kein Git-Repository an diesem Projekt konnektiert")
    
    git_source.sync_status = "pending"
    git_source.progress = 0
    git_source.progress_message = "In Warteschlange…"
    db.commit()
    celery_app.send_task("sync_source", args=[git_source.id])
    return {"message": "Synchronisierung gestartet", "repo_id": git_source.id}

@router.get("/{id}/knowledge-sources")
def get_project_knowledge_sources(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    # Lese projektspezifische Quellen und globale Quellen (project_id IS NULL)
    q = db.query(KnowledgeSource).filter(
        or_(
            KnowledgeSource.project_id == id,
            KnowledgeSource.project_id.is_(None)
        ),
        KnowledgeSource.team_id == proj.team_id
    )
    return [serialize_source(s) for s in q.all()]

@router.get("/{id}/references")
def get_project_references(
    id: int,
    file_path: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    assert_project_visible(id, user, db)

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    
    references = []
    seen = set()

    # 1. EntityDocLink targets matching the file_path (document -> entity references)
    ed_targets = db.query(EntityDocLink).join(DocumentChunk, EntityDocLink.chunk_id == DocumentChunk.id).filter(
        EntityDocLink.project_id == id,
        EntityDocLink.status == "approved",
        DocumentChunk.file_path == file_path
    ).all()
    
    # Also find by doc_title matching basename or file_path if chunk is null
    ed_targets_title = db.query(EntityDocLink).filter(
        EntityDocLink.project_id == id,
        EntityDocLink.status == "approved",
        EntityDocLink.chunk_id.is_(None),
        or_(
            EntityDocLink.doc_title.ilike(f"%{base_name}%"),
            EntityDocLink.doc_title.ilike(f"%{file_path}%")
        )
    ).all()

    for lnk in ed_targets + ed_targets_title:
        if lnk.entity:
            key = ("entity", lnk.entity.id)
            if key not in seen:
                seen.add(key)
                references.append({
                    "id": f"entity:{lnk.entity.id}",
                    "node_type": "entity",
                    "name": lnk.entity.name,
                    "title": lnk.entity.name,
                    "file_path": lnk.entity.file_path,
                    "line": lnk.entity.start_line,
                    "source_id": lnk.entity.source_id,
                    "source": "Git",
                    "preview": lnk.context or f"Code-Objekt ({lnk.entity.type}) verknüpft mit Dokument",
                    "score": lnk.score,
                    "link_type": lnk.link_type
                })

    # 2. EntityDocLink sources matching the file_path (entity -> document references)
    ed_sources = db.query(EntityDocLink).join(CodeEntity, EntityDocLink.entity_id == CodeEntity.id).filter(
        EntityDocLink.project_id == id,
        EntityDocLink.status == "approved",
        CodeEntity.file_path == file_path
    ).all()

    for lnk in ed_sources:
        target_path = lnk.chunk.file_path if lnk.chunk else file_path
        key = ("document", lnk.doc_title)
        if key not in seen:
            seen.add(key)
            references.append({
                "id": f"doc:{lnk.doc_title}",
                "node_type": "document",
                "name": lnk.doc_title,
                "title": lnk.doc_title,
                "file_path": target_path,
                "url": lnk.doc_url,
                "source": lnk.source_type or "Local",
                "preview": lnk.context or f"Dokument verknüpft mit Code-Objekt in {base_name}",
                "score": lnk.score,
                "link_type": lnk.link_type
            })

    # 3. KnowledgeLink matching the file_path
    k_links = db.query(KnowledgeLink).filter(
        KnowledgeLink.status == "approved"
    ).all()

    for kl in k_links:
        match_a = False
        match_b = False
        
        # Check side A
        if kl.source_a_type == "document" and kl.source_a_chunk:
            if kl.source_a_chunk.project_id == id and kl.source_a_chunk.file_path == file_path:
                match_a = True
        elif kl.source_a_type == "entity" and kl.source_a_entity:
            if kl.source_a_entity.project_id == id and kl.source_a_entity.file_path == file_path:
                match_a = True
                
        # Check side B
        if kl.source_b_type == "document" and kl.source_b_chunk:
            if kl.source_b_chunk.project_id == id and kl.source_b_chunk.file_path == file_path:
                match_b = True
        elif kl.source_b_type == "entity" and kl.source_b_entity:
            if kl.source_b_entity.project_id == id and kl.source_b_entity.file_path == file_path:
                match_b = True
                
        if match_a or match_b:
            ref_side = "b" if match_a else "a"
            
            if ref_side == "b":
                ref_id = f"entity:{kl.source_b_entity_id}" if kl.source_b_type == "entity" else f"doc:{kl.source_b_title}"
                key = (kl.source_b_type, ref_id)
                if key not in seen:
                    seen.add(key)
                    references.append({
                        "id": ref_id,
                        "node_type": kl.source_b_type,
                        "name": kl.source_b_title,
                        "title": kl.source_b_title,
                        "file_path": kl.source_b_chunk.file_path if kl.source_b_chunk else (kl.source_b_entity.file_path if kl.source_b_entity else kl.source_b_title),
                        "line": kl.source_b_entity.start_line if kl.source_b_entity else None,
                        "source_id": kl.source_b_entity.source_id if kl.source_b_entity else (kl.source_b_chunk.source_id if kl.source_b_chunk else None),
                        "url": kl.source_b_url,
                        "source": kl.source_b_source_type or ("Git" if kl.source_b_type == "entity" else "Local"),
                        "preview": kl.context or f"Verknüpfter Knoten",
                        "score": kl.score,
                        "link_type": kl.link_type
                    })
            else:
                ref_id = f"entity:{kl.source_a_entity_id}" if kl.source_a_type == "entity" else f"doc:{kl.source_a_title}"
                key = (kl.source_a_type, ref_id)
                if key not in seen:
                    seen.add(key)
                    references.append({
                        "id": ref_id,
                        "node_type": kl.source_a_type,
                        "name": kl.source_a_title,
                        "title": kl.source_a_title,
                        "file_path": kl.source_a_chunk.file_path if kl.source_a_chunk else (kl.source_a_entity.file_path if kl.source_a_entity else kl.source_a_title),
                        "line": kl.source_a_entity.start_line if kl.source_a_entity else None,
                        "source_id": kl.source_a_entity.source_id if kl.source_a_entity else (kl.source_a_chunk.source_id if kl.source_a_chunk else None),
                        "url": kl.source_a_url,
                        "source": kl.source_a_source_type or ("Git" if kl.source_a_type == "entity" else "Local"),
                        "preview": kl.context or f"Verknüpfter Knoten",
                        "score": kl.score,
                        "link_type": kl.link_type
                    })

    return references

# ── Zugriffsrechte & Anfragen ───────────────────────────────────────────────

@router.post("/{id}/request-access", status_code=201)
def request_access(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    assert_team_visible(proj.team_id, user, db, "Projekt nicht gefunden")

    # Überprüfe, ob bereits Mitglied
    membership = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == id,
        ProjectMembership.user_id == user.id
    ).first()
    if membership:
        return {"message": "Du bist bereits Mitglied dieses Projekts", "status": "approved"}

    # Überprüfe auf bestehende Anfrage
    existing = db.query(ProjectAccessRequest).filter(
        ProjectAccessRequest.project_id == id,
        ProjectAccessRequest.user_id == user.id
    ).first()

    if existing:
        return {"message": "Eine Anfrage ist bereits ausstehend", "status": existing.status}

    req = ProjectAccessRequest(
        project_id=id,
        user_id=user.id,
        status="pending"
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    return {"message": "Anfrage erfolgreich an Projekt-Admin gesendet", "status": "pending"}

@router.get("/{id}/access-requests")
def list_access_requests(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    
    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Zugriffsanfragen einsehen")

    requests = db.query(ProjectAccessRequest).filter(
        ProjectAccessRequest.project_id == id,
        ProjectAccessRequest.status == "pending"
    ).all()

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": r.user.name or r.user.email,
            "user_email": r.user.email,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in requests
    ]

@router.post("/{id}/access-requests/{request_id}/resolve")
def resolve_access_request(
    id: int,
    request_id: int,
    data: ProjectAccessRequestUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    
    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Zugriffsanfragen auflösen")

    req = db.query(ProjectAccessRequest).filter(
        ProjectAccessRequest.id == request_id,
        ProjectAccessRequest.project_id == id
    ).first()
    
    if not req:
        raise HTTPException(status_code=404, detail="Zugriffsanfrage nicht gefunden")

    req.status = data.status

    if data.status == "approved":
        # Zu Mitgliedern hinzufügen
        existing = db.query(ProjectMembership).filter(
            ProjectMembership.project_id == id,
            ProjectMembership.user_id == req.user_id
        ).first()
        if not existing:
            membership = ProjectMembership(
                user_id=req.user_id,
                project_id=id,
                role="member"
            )
            db.add(membership)
            
    db.commit()
    return {"message": f"Anfrage wurde {data.status}"}

# ── Projektmitglieder-Verwaltung ──────────────────────────────────────────

@router.get("/{id}/members")
def list_project_members(
    id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
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
            "created_at": m.created_at.isoformat() if m.created_at else None
        }
        for m in memberships
    ]

@router.post("/{id}/members")
def add_project_member(
    id: int,
    data: ProjectMembershipCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    
    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Mitglieder hinzufügen")

    if data.role not in ALLOWED_PROJECT_ROLES:
        raise HTTPException(status_code=400, detail=f"Ungültige Rolle. Erlaubt: {', '.join(sorted(ALLOWED_PROJECT_ROLES))}")

    target_user = db.query(User).filter(User.id == data.user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

    existing = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == id,
        ProjectMembership.user_id == data.user_id
    ).first()
    
    if existing:
        raise HTTPException(status_code=409, detail="Benutzer ist bereits Mitglied")

    membership = ProjectMembership(
        user_id=data.user_id,
        project_id=id,
        role=data.role
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)

    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "user_name": target_user.name or target_user.email,
        "role": membership.role
    }

@router.patch("/{id}/members/{user_id}")
def update_project_member_role(
    id: int,
    user_id: int,
    data: ProjectMembershipRoleUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")

    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Rollen ändern")

    if data.role not in ALLOWED_PROJECT_ROLES:
        raise HTTPException(status_code=400, detail=f"Ungültige Rolle. Erlaubt: {', '.join(sorted(ALLOWED_PROJECT_ROLES))}")

    membership = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == id,
        ProjectMembership.user_id == user_id
    ).first()

    if not membership:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")

    membership.role = data.role
    db.commit()
    db.refresh(membership)

    return {
        "id": membership.id,
        "user_id": membership.user_id,
        "role": membership.role
    }

@router.delete("/{id}/members/{user_id}")
def remove_project_member(
    id: int,
    user_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    proj = db.query(Project).filter(Project.id == id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Projekt nicht gefunden")
    
    if not _is_project_admin(id, user, db):
        raise HTTPException(status_code=403, detail="Nur Projekt-Admins können Mitglieder entfernen")

    if proj.creator_id == user_id:
        raise HTTPException(status_code=400, detail="Der Projekt-Ersteller kann nicht aus dem Projekt entfernt werden")

    membership = db.query(ProjectMembership).filter(
        ProjectMembership.project_id == id,
        ProjectMembership.user_id == user_id
    ).first()

    if not membership:
        raise HTTPException(status_code=404, detail="Mitgliedschaft nicht gefunden")

    db.delete(membership)
    db.commit()

    return {"message": "Mitglied erfolgreich entfernt"}

# ── Interne Referenz-Such-Helfer ──────────────────────────────────────────────

def _ilike_to_regex(pattern: str) -> "re.Pattern":
    """Übersetzt ein SQL-ILIKE-'%...%'-Pattern in eine gleichwertige case-insensitive Regex.
    Nötig weil DocumentChunk.content jetzt at rest Fernet-verschlüsselt ist (EncryptedString)
    und sich nicht mehr per SQL ILIKE filtern lässt -- der Match läuft stattdessen in Python
    nach dem Entschlüsseln."""
    return re.compile(".*".join(re.escape(part) for part in pattern.split("%")), re.IGNORECASE | re.DOTALL)


def _refs_for_document(project_id, file_path, base_name, db) -> list[dict]:
    """Findet Code-Stellen, die ein Dokument (PDF, Word, ...) erwähnen."""
    patterns = [_ilike_to_regex(f"%{base_name}%"), _ilike_to_regex(f"%{file_path}%")]
    candidates = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.source_id == None,
    ).all()
    results = [c for c in candidates if any(p.search(c.content or "") for p in patterns)]
    return _extract_line_refs(results, lambda line: base_name.upper() in line.upper() or file_path.upper() in line.upper())


def _refs_for_file(project_id, file_path, base_name, db) -> list[dict]:
    """Findet alle Stellen, die per Text-Grep (import/from/require/COPY-Muster) auf diese Datei verweisen."""
    ref_list: list[dict] = []
    seen: set = set()

    patterns = [
        _ilike_to_regex(p) for p in (
            f'%COPY%"{base_name}"%',
            f"%COPY%'{base_name}'%",
            f"%COPY% {base_name}%",
            f"%import %{base_name}%",
            f"%from %{base_name}%",
            f'%from %"{base_name}"%',
            f"%from %'{base_name}'%",
            f'%require(%"{base_name}"%',
            f"%require(%'{base_name}'%",
        )
    ]
    candidates = db.query(DocumentChunk).filter(
        DocumentChunk.project_id == project_id,
        DocumentChunk.file_path != file_path,
    ).all()
    results = [c for c in candidates if any(p.search(c.content or "") for p in patterns)]
    for ref in _extract_line_refs(
        results,
        lambda line: base_name.upper() in line.upper() and any(
            x in line.upper() for x in ["COPY", "IMPORT", "FROM", "REQUIRE"]
        )
    ):
        key = (ref["file_path"], ref["line"])
        if key not in seen:
            seen.add(key)
            ref_list.append(ref)

    return ref_list


def _extract_line_refs(chunks, line_predicate) -> list[dict]:
    result = []
    seen = set()
    for chunk in chunks:
        lines = chunk.content.splitlines()
        matching = [
            chunk.start_line + i for i, line in enumerate(lines) if line_predicate(line)
        ]
        for line_num in (matching or [chunk.start_line]):
            key = (chunk.file_path, line_num)
            if key not in seen:
                seen.add(key)
                idx = line_num - chunk.start_line
                preview = lines[idx].strip() if 0 <= idx < len(lines) else chunk.content[:60].strip()
                result.append({"file_path": chunk.file_path, "line": line_num, "preview": preview})
    return result
