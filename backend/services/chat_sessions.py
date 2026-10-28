"""
backend/services/chat_sessions.py
=================================
Sitzungsverwaltung des Chats: Sichtbarkeit, Anlegen/Fortsetzen, Start einer
Gesprächsrunde und Serialisierung.

Zugriffsregel (O-032): Der Besitzer hat immer Zugriff; alle anderen nur, wenn
die Sitzung über „Chat teilen" freigegeben wurde (``is_public``). Teilen und
Löschen bleibt dem Besitzer vorbehalten.

Fehler kommen als ``services.chat_errors``-Ausnahmen; Team-/Projekt-Sichtbarkeit prüfen die gemeinsamen Helfer aus
``core.teams``/``core.projects``.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

from core.projects import assert_knowledge_source_visible, assert_project_visible
from core.teams import assert_team_visible, is_admin
from models.database import ChatMessage, ChatSession, KnowledgeSource, Project, User
from services.chat_errors import ChatForbidden, ChatInvalid, ChatNotFound

if TYPE_CHECKING:
    from api.schemas import ChatRequest

HISTORY_LIMIT = 6
_SESSION_NOT_FOUND = "Session nicht gefunden"


def session_accessible(session: ChatSession, user: User) -> bool:
    return session.owner_id == user.id or session.is_public


def assert_scope_visible(
    db: Session,
    user: User,
    *,
    project_id: Optional[int] = None,
    source_id: Optional[int] = None,
    pinned_source_id: Optional[int] = None,
) -> None:
    """Projekt, Wissensquelle und gepinnte Quelle einer Anfrage müssen für den Nutzer sichtbar sein."""
    if project_id:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise ChatNotFound("Projekt nicht gefunden")
        assert_team_visible(project.team_id, user, db, "Projekt nicht gefunden")
        assert_project_visible(project_id, user, db)
    if source_id:
        source = db.query(KnowledgeSource).filter(KnowledgeSource.id == source_id).first()
        if not source:
            raise ChatNotFound("Wissensquelle nicht gefunden")
        assert_knowledge_source_visible(source, user, db)
    if pinned_source_id and pinned_source_id != source_id:
        pinned = db.query(KnowledgeSource).filter(KnowledgeSource.id == pinned_source_id).first()
        if not pinned:
            raise ChatNotFound("Wissensquelle nicht gefunden")
        assert_knowledge_source_visible(pinned, user, db)
        if project_id and pinned.project_id not in (None, project_id):
            raise ChatNotFound("Wissensquelle nicht gefunden")


def get_accessible_session(
    db: Session, user: User, *, session_id: Optional[int] = None, uuid: Optional[str] = None
) -> ChatSession:
    query = db.query(ChatSession)
    query = (
        query.filter(ChatSession.uuid == uuid)
        if uuid is not None
        else query.filter(ChatSession.id == session_id)
    )
    session = query.first()
    # Eine nie geteilte Sitzung bleibt auch über ihre UUID unerreichbar.
    if not session or not session_accessible(session, user):
        raise ChatNotFound(_SESSION_NOT_FOUND)
    return session


def get_accessible_assistant_message(db: Session, user: User, message_id: int) -> ChatMessage:
    message = (
        db.query(ChatMessage)
        .filter(ChatMessage.id == message_id, ChatMessage.role == "assistant")
        .first()
    )
    if not message or not message.session or not session_accessible(message.session, user):
        raise ChatNotFound("Nachricht nicht gefunden")
    return message


def _owned_session(db: Session, user: User, session_id: int, action: str) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise ChatNotFound(_SESSION_NOT_FOUND)
    if session.owner_id != user.id:
        raise ChatForbidden(f"Nur der Besitzer kann diese Sitzung {action}")
    return session


def create_session(
    db: Session,
    user: User,
    *,
    title: str,
    project_id: Optional[int],
    source_id: Optional[int],
    snapshot: Optional[dict] = None,
) -> ChatSession:
    """Benannte Sitzung ohne Chat-Nachricht (O-038)."""
    title = (title or "").strip()
    if not title:
        raise ChatInvalid("Titel darf nicht leer sein")
    assert_scope_visible(db, user, project_id=project_id, source_id=source_id)
    session = ChatSession(
        title=title,
        project_id=project_id,
        source_id=source_id,
        owner_id=user.id,
        snapshot_json=sanitize_workspace_snapshot(snapshot, user),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def list_own_sessions(db: Session, user: User) -> list[ChatSession]:
    # Geteilte Sitzungen anderer werden nur über ihre UUID erreicht, nie gelistet.
    return (
        db.query(ChatSession)
        .filter(ChatSession.owner_id == user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


def page_own_sessions(
    db: Session,
    user: User,
    *,
    limit: int,
    before_id: Optional[int],
    project_id: Optional[int],
    general: bool,
) -> tuple[list[ChatSession], bool]:
    """Cursor-Seite (``before_id`` = kleinste bereits geladene ID), neueste zuerst.

    Cursor statt Offset, damit zwischenzeitlich angelegte oder gelöschte
    Sitzungen die folgenden Seiten nicht verschieben.
    """
    query = db.query(ChatSession).filter(ChatSession.owner_id == user.id)
    if project_id is not None:
        query = query.filter(ChatSession.project_id == project_id)
    elif general:
        query = query.filter(ChatSession.project_id.is_(None))
    if before_id is not None:
        query = query.filter(ChatSession.id < before_id)
    rows = query.order_by(ChatSession.id.desc()).limit(limit + 1).all()
    return rows[:limit], len(rows) > limit


def share_session(db: Session, user: User, session_id: int) -> ChatSession:
    session = _owned_session(db, user, session_id, "teilen")
    if not session.is_public:
        session.is_public = True
        db.commit()
    return session


def update_snapshot(db: Session, user: User, session_id: int, snapshot: Optional[dict]) -> None:
    # Ein über den Share-Link fortgesetzter Chat darf den Snapshot ohne Besitzerrechte aktualisieren.
    session = get_accessible_session(db, user, session_id=session_id)
    session.snapshot_json = sanitize_workspace_snapshot(snapshot, user)
    db.commit()


def delete_session(db: Session, user: User, session_id: int) -> None:
    db.delete(_owned_session(db, user, session_id, "löschen"))
    db.commit()


@dataclass
class ChatTurn:
    """Eine Gesprächsrunde: Nutzerfrage, ggf. zu ersetzende Antwort und Verlauf davor."""

    session: ChatSession
    user_message: ChatMessage
    replaced_answer: Optional[ChatMessage]
    history: list[ChatMessage]


def open_session_for_turn(db: Session, user: User, request: "ChatRequest") -> ChatSession:
    """Setzt die angefragte Sitzung fort oder legt eine neue mit Titel aus der Frage an."""
    session = None
    if request.session_id:
        session = db.query(ChatSession).filter(ChatSession.id == request.session_id).first()
        if session and not session_accessible(session, user):
            raise ChatNotFound("Chat-Sitzung nicht gefunden")
    if session:
        if session.project_id:
            project = db.query(Project).filter(Project.id == session.project_id).first()
            if project:
                assert_team_visible(project.team_id, user, db, "Chat-Sitzung nicht gefunden")
                assert_project_visible(session.project_id, user, db)
        if session.source_id:
            source = (
                db.query(KnowledgeSource).filter(KnowledgeSource.id == session.source_id).first()
            )
            if source:
                assert_knowledge_source_visible(source, user, db, "Chat-Sitzung nicht gefunden")
        updated = False
        if not session.project_id and request.project_id:
            session.project_id = request.project_id
            updated = True
        if not session.source_id and request.source_id:
            session.source_id = request.source_id
            updated = True
        if updated:
            db.commit()
        return session

    title = request.message[:30] + ("..." if len(request.message) > 30 else "")
    session = ChatSession(
        title=title,
        project_id=request.project_id,
        source_id=request.source_id,
        owner_id=user.id,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def begin_turn(db: Session, session: ChatSession, request: "ChatRequest") -> ChatTurn:
    """Speichert die Nutzerfrage bzw. bereitet das Ersetzen einer Antwort vor.

    Beim Wiederholen (``retry_of_message_id``) bleibt die vorangehende
    Nutzerfrage unverändert an ihrer Position; nur die Antwort wird ersetzt.
    """
    replaced = None
    if request.retry_of_message_id:
        replaced = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.id == request.retry_of_message_id,
                ChatMessage.session_id == session.id,
                ChatMessage.role == "assistant",
            )
            .first()
        )
        if not replaced:
            raise ChatNotFound("Zu wiederholende Antwort nicht gefunden")
        user_message = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session.id,
                ChatMessage.role == "user",
                ChatMessage.id < replaced.id,
            )
            .order_by(ChatMessage.id.desc())
            .first()
        )
        if not user_message:
            raise ChatNotFound("Zugehörige Nutzer-Nachricht nicht gefunden")
    else:
        user_message = ChatMessage(
            session_id=session.id,
            role="user",
            content=request.message,
            # Der Modus der ersten Nutzernachricht legt den Chat fest (Frontend: lockedChatMode).
            metadata_json={**(request.metadata or {}), "chat_mode": request.mode},
        )
        db.add(user_message)
        db.commit()

    excluded_ids = [user_message.id] + ([replaced.id] if replaced else [])
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id, ChatMessage.id.notin_(excluded_ids))
        .order_by(ChatMessage.created_at.desc())
        .limit(HISTORY_LIMIT)
        .all()
    )
    history.reverse()
    return ChatTurn(session, user_message, replaced, history)


def sanitize_workspace_snapshot(snapshot: dict | None, user: User) -> dict | None:
    """Never disclose or restore the privileged Link-Manager panel to members.

    A shared admin session can contain any panel type. The server therefore
    strips the panel and all index-aligned state before returning it to a
    non-admin; frontend filtering is only a second defensive layer.
    """
    if not isinstance(snapshot, dict) or is_admin(user):
        return snapshot
    configs = snapshot.get("panelConfigs")
    if not isinstance(configs, list) or "linkmanager" not in configs:
        return snapshot
    keep = [index for index, panel_type in enumerate(configs) if panel_type != "linkmanager"]
    sanitized = dict(snapshot)
    sanitized["panelConfigs"] = [configs[index] for index in keep] or ["chat"]
    for key in ("panelFrozen", "panelSelections", "panelFocusObject"):
        values = snapshot.get(key)
        if isinstance(values, list):
            sanitized[key] = [values[index] for index in keep if index < len(values)]
    if isinstance(sanitized.get("panelSelections"), list) and not sanitized["panelSelections"]:
        sanitized["panelSelections"] = [
            {
                "selectedFile": None,
                "selectedDoc": None,
                "selectedEntity": None,
                "selectedLine": None,
            }
        ]
    return sanitized


def serialize_session(s: ChatSession, user: User) -> dict:
    return {
        "id": s.id,
        "uuid": str(s.uuid) if s.uuid else None,
        "title": s.title,
        "project_id": s.project_id,
        "project": {
            "id": s.project.id,
            "name": s.project.name,
            "is_archived": s.project.is_archived,
            "color": s.project.color,
        }
        if s.project
        else None,
        "source_id": s.source_id,
        "source": {"id": s.source.id, "name": s.source.name, "type": s.source.type}
        if s.source
        else None,
        "snapshot_json": sanitize_workspace_snapshot(s.snapshot_json, user),
        "is_public": s.is_public,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def serialize_messages(session_id: int, db: Session) -> list[dict]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources_json": m.sources_json,
            "metadata_json": m.metadata_json,
            "feedback": m.feedback,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]
