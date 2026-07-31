"""
backend/core/projects.py
========================
Projekt-Sichtbarkeits- und Zugriffskontroll-Helfer.
Stellt sicher, dass Benutzer nur auf Projekte zugreifen können,
in denen sie Mitglied sind, es sei denn, sie sind globale Admins.
"""

from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from models.database import Project, ProjectMembership, User, KnowledgeSource
from core.teams import is_admin

def chunk_source_label(chunk, db: Session) -> str:
    """
    Menschenlesbares Label für die Herkunft eines DocumentChunk.
    Git-geparste Chunks haben kein KnowledgeSource (source_id ist None) — project_id
    allein reicht seit dem Project-Refactor nicht mehr zur Unterscheidung, da es bei
    jedem projekt-gebundenen Chunk gesetzt ist, egal ob git oder nicht.
    """
    if chunk.source_id is None:
        return "Git"
    source_type = db.query(KnowledgeSource.type).filter(KnowledgeSource.id == chunk.source_id).scalar()
    return source_type or "Local"

def get_visible_project_ids(user: User, db: Session) -> Optional[list[int]]:
    """
    Gibt None zurück, wenn der Benutzer ein globaler Admin ist (Zugriff auf alle Projekte).
    Andernfalls wird eine Liste von project_ids zurückgegeben, für die der Benutzer Mitglied ist.
    """
    if is_admin(user):
        return None
    rows = db.query(ProjectMembership.project_id).filter(ProjectMembership.user_id == user.id).all()
    return [r[0] for r in rows]

def assert_project_visible(project_id: int, user: User, db: Session, not_found_detail: str = "Projekt nicht gefunden") -> None:
    """
    Prüft, ob das Projekt für den Benutzer sichtbar ist.
    Falls nicht, wird eine 403 Forbidden Exception ausgelöst.
    """
    visible = get_visible_project_ids(user, db)
    if visible is not None and project_id not in visible:
        # Finde den Projekt-Admin (Ersteller) heraus für die Fehlermeldung
        proj = db.query(Project).filter(Project.id == project_id).first()
        admin_info = "dem Projekt-Admin"
        if proj and proj.creator:
            admin_info = f"Projekt-Admin {proj.creator.name or proj.creator.email}"

        raise HTTPException(
            status_code=403,
            detail=f"Zugriff verweigert. Bitte wende dich an {admin_info}, um Zugriff zu erhalten."
        )

# Alle vergebbaren Projekt-Mitgliedsrollen (ProjectMembership.role).
ALLOWED_PROJECT_ROLES = {"admin", "member"}

def get_project_role(project_id: int, user: User, db: Session) -> str:
    """
    Liefert die effektive Projekt-Rolle des Benutzers, ohne eine Exception zu
    werfen — für Fälle, in denen die Rolle nur zur Steuerung von Inhalten/Ton
    gebraucht wird (z.B. Onboarding-Briefing), nicht zur Zugriffskontrolle.
    Sichtbarkeit ist an dieser Stelle bereits über assert_project_visible/
    get_visible_project_ids geprüft.

    Globale Admins gelten als "admin". Fehlt eine ProjectMembership (sollte durch
    die vorgelagerte Sichtbarkeitsprüfung eigentlich nicht vorkommen), wird
    defensiv auf die am wenigsten privilegierte Rolle "member" zurückgefallen,
    statt zu fehlern.
    """
    if is_admin(user):
        return "admin"
    membership = (
        db.query(ProjectMembership)
        .filter(ProjectMembership.project_id == project_id, ProjectMembership.user_id == user.id)
        .first()
    )
    return membership.role if membership and membership.role in ALLOWED_PROJECT_ROLES else "member"

def resolve_repository_id(project_id: int, db: Session) -> Optional[int]:
    """
    Findet die Repository-ID eines Projekts heraus, falls verknüpft.
    """
    from models.database import KnowledgeSource
    source = db.query(KnowledgeSource).filter(
        KnowledgeSource.project_id == project_id,
        KnowledgeSource.type == "Git"
    ).first()
    return source.id if source else None
