"""
backend/core/projects.py
========================
Projekt-Sichtbarkeits- und Zugriffskontroll-Helfer.
Stellt sicher, dass Benutzer nur auf Projekte zugreifen können,
in denen sie Mitglied sind, es sei denn, sie sind globale Admins.
"""

from typing import Optional
from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from models.database import DocumentChunk, Project, ProjectMembership, User, KnowledgeSource
from core.teams import assert_team_visible, get_visible_team_ids, is_admin

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
    team_ids = get_visible_team_ids(user, db)
    rows = (
        db.query(ProjectMembership.project_id)
        .join(Project, Project.id == ProjectMembership.project_id)
        .filter(
            ProjectMembership.user_id == user.id,
            Project.team_id.in_(team_ids or []),
        )
        .all()
    )
    return [r[0] for r in rows]

def get_globally_exposed_project_ids(db: Session) -> list[int]:
    """Projekt-IDs, deren Code-Analyse-Objekte per Opt-in (`Project.expose_code_analysis_globally`)
    außerhalb ihres eigenen Projekt-Kontexts sichtbar sind (Allgemein-Suche/-Graph-View).
    Default: leere Liste, kein Projekt ist opted-in."""
    rows = db.query(Project.id).filter(Project.expose_code_analysis_globally.is_(True)).all()
    return [r[0] for r in rows]


def is_project_code_visible_in_context(project_id: Optional[int], requesting_project_id: Optional[int], db: Session) -> bool:
    """Ob Code-Analyse-Objekte (CodeEntity/Callgraph) von `project_id` im aktuellen
    Anfrage-Kontext sichtbar sein dürfen, VORAUSGESETZT die reguläre Team-/Projekt-
    Sichtbarkeit (assert_project_visible/assert_team_visible) wurde bereits geprüft.

    `project_id=None` betrifft keine Projekt-gebundene Entity (z.B. eine eigenständige
    Git-Wissensquelle) — davon ist dieser Mechanismus nicht betroffen.
    `requesting_project_id` ist die Projekt-ID, in deren eigenem Kontext angefragt wird
    (Code-Editor, projektgebundene Panels schicken ihre aktuelle project_id mit) — stimmt
    sie mit `project_id` überein, ist der Zugriff der ursprünglich vorgesehene
    projektinterne Zugriff und immer erlaubt. Sonst (kein Kontext, z.B. "Allgemein", oder
    ein ANDERES Projekt) braucht es das explizite Opt-in `expose_code_analysis_globally`.
    """
    if project_id is None or requesting_project_id == project_id:
        return True
    proj = db.query(Project).filter(Project.id == project_id).first()
    return bool(proj and proj.expose_code_analysis_globally)


def build_document_chunk_code_gate(db: Session, exposed_project_ids: list[int]) -> Optional[ColumnElement]:
    """SQL-Filterbedingung für DocumentChunk-Bulk-Queries (Allgemein-Suche/-Graph-View):
    wendet dieselbe Opt-in-Einschränkung wie CodeEntity/Callgraph auf Chunks an, die aus
    einer Git-Wissensquelle stammen (rohe Repo-Quelldateien -- Code-Analyse-Inhalt, keine
    echte Dokumentation). Echte Doku-Quellen (Confluence/Jira/Upload) bleiben unberührt
    projektübergreifend durchsuchbar/sichtbar, siehe is_document_chunk_code_visible_in_context.

    `exposed_project_ids` wie von get_globally_exposed_project_ids geliefert (ggf. bereits
    auf die Sichtbarkeit des Nutzers eingeschränkt). Gibt None zurück, wenn es keine
    Git-Wissensquelle gibt (dann ist nichts einzuschränken -- Bedingung schlicht weglassen,
    statt sie unnötig in die Query aufzunehmen)."""
    git_source_ids = [s[0] for s in db.query(KnowledgeSource.id).filter(KnowledgeSource.type == "Git").all()]
    if not git_source_ids:
        return None
    return or_(
        ~DocumentChunk.source_id.in_(git_source_ids),
        DocumentChunk.project_id.in_(exposed_project_ids),
        DocumentChunk.project_id == None,  # noqa: E711 (SQLAlchemy-Idiom, kein `is None`)
    )


def is_document_chunk_code_visible_in_context(
    chunk: DocumentChunk, requesting_project_id: Optional[int], db: Session
) -> bool:
    """Einzelfall-Variante von build_document_chunk_code_gate für bereits geladene Chunks
    (z.B. eine Seite eines generischen KnowledgeLink, siehe api/graph.py::_is_side_visible)."""
    if chunk.source_id is None:
        return True
    is_git_source = db.query(KnowledgeSource.id).filter(
        KnowledgeSource.id == chunk.source_id, KnowledgeSource.type == "Git"
    ).first() is not None
    if not is_git_source:
        return True
    return is_project_code_visible_in_context(chunk.project_id, requesting_project_id, db)


def assert_project_code_visible_in_context(
    project_id: Optional[int], requesting_project_id: Optional[int], db: Session,
    not_found_detail: str = "Entity nicht gefunden",
) -> None:
    """Wirft 404 (statt 403 — dieselbe Nicht-gefunden-Tarnung wie bei Team-Sichtbarkeit,
    kein Hinweis, dass die Entity überhaupt existiert), wenn `project_id` im aktuellen
    Kontext nicht sichtbar sein darf. Siehe is_project_code_visible_in_context."""
    if not is_project_code_visible_in_context(project_id, requesting_project_id, db):
        raise HTTPException(status_code=404, detail=not_found_detail)


def assert_project_visible(project_id: int, user: User, db: Session, not_found_detail: str = "Projekt nicht gefunden") -> None:
    """
    Prüft, ob das Projekt für den Benutzer sichtbar ist.
    Falls nicht, wird eine 403 Forbidden Exception ausgelöst.
    """
    if not is_admin(user):
        project = db.query(Project).filter(Project.id == project_id).first()
        if project is not None:
            assert_team_visible(project.team_id, user, db, not_found_detail)

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


def assert_knowledge_source_visible(
    source: KnowledgeSource,
    user: User,
    db: Session,
    not_found_detail: str = "Wissensquelle nicht gefunden",
) -> None:
    """Prüft die effektive Sichtbarkeit einer Wissensquelle.

    Eine globale Quelle hängt nur an ihrer Team-Sichtbarkeit. Bei einer
    projektgebundenen Quelle ist zusätzlich die Projektmitgliedschaft nötig;
    die Teammitgliedschaft allein darf keinen Zugriff auf Projektinhalte
    eröffnen. Diese Regel wird von allen Source-Lese- und -Schreibpfaden
    gemeinsam verwendet.
    """
    assert_team_visible(source.team_id, user, db, not_found_detail)
    if source.project_id is not None:
        assert_project_visible(source.project_id, user, db, not_found_detail)

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
