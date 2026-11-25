"""
backend/api/chat.py
====================
HTTP-Schicht des Chats: Eingabeprüfung, Aufruf der Chat-Dienste, Übersetzung
fachlicher Fehler in HTTP-Status und SSE-Transport.

Die Fachlogik liegt in eigenen Modulen:
    services/chat_turn.py         — Antwortablauf einer Runde (Retrieval, Agent/RAG, Persistenz)
    services/chat_sources.py      — Quellenprüfung und „Referenzierte Quellen"
    services/chat_sessions.py     — Sitzungen, Sichtbarkeit, Start einer Runde
    services/chat_feedback.py     — Up-/Downvotes und Admin-Auswertung
    services/chat_view_actions.py — vom Agenten angebotene UI-Aktionen
    services/chat_start.py        — Inhalte der leeren Startansicht
"""

import asyncio
import json
import logging
from contextlib import contextmanager
from time import monotonic
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from api.schemas import (
    ChatFollowUpRequest,
    ChatMessageFeedbackUpdate,
    ChatMessageViewActionUpdate,
    ChatRequest,
    ChatSessionCreate,
    ChatSessionUpdate,
    ChatSnapshotUpdate,
)
from core.auth_dependency import get_current_user
from core.db_setup import get_db
from core.projects import assert_project_visible
from codena_models.database import User
from services import chat_sessions as sessions
from services.chat_errors import ChatForbidden, ChatInvalid, ChatNotFound
from services.chat_export import export_filename, export_markdown
from services.chat_followups import follow_up_suggestions
from services.chat_feedback import list_negative_feedback, set_message_feedback
from services.chat_start import generate_typing_statement, project_pulse
from services.chat_turn import run_chat_turn, select_chat_profile
from services.chat_view_actions import update_view_action_status

logger = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_HEARTBEAT_SECONDS = 15.0
# Abgebrochene Runden, die noch aufräumen; die Referenz hält ihre Tasks bis zum Ende am Leben.
_finishing: set[asyncio.Future] = set()


def _finish_in_background(task: asyncio.Future) -> None:
    _finishing.add(task)
    task.add_done_callback(_finished)


def _finished(task: asyncio.Future) -> None:
    _finishing.discard(task)
    error = None if task.cancelled() else task.exception()
    if error is not None and not isinstance(error, StopAsyncIteration):
        logger.warning("Abgebrochene Chat-Runde endete mit %s", type(error).__name__)


@contextmanager
def _http_errors():
    try:
        yield
    except ChatNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ChatForbidden as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ChatInvalid as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _sse(events: AsyncIterator[dict]) -> AsyncIterator[str]:
    """Serialisiert Ereignisse als SSE und hält die Verbindung mit Kommentar-Pings offen.

    Auf das nächste Ereignis wird per Task gewartet statt per wait_for, damit ein
    Heartbeat-Timeout den laufenden Modellaufruf nicht abbricht.

    Trennt der Client die Verbindung, bricht der Server die Runde ab, statt sie verwaist weiterlaufen zu
    lassen: Der wartende Task (meist ein Modellaufruf mit belegtem Inferenzplatz) wird abgebrochen und die
    Runde geschlossen, damit ihre Aufräumarbeit (MCP-Clients, Streams) sofort läuft. Gespeichert wird dann
    nichts; die Nutzerfrage bleibt ohne Antwort stehen.
    """
    task = None
    try:
        while True:
            task = asyncio.ensure_future(events.__anext__())
            try:
                while True:
                    done, _ = await asyncio.wait({task}, timeout=_HEARTBEAT_SECONDS)
                    if done:
                        break
                    yield ": ping\n\n"
                event = task.result()
            except StopAsyncIteration:
                return
            except Exception as exc:
                logger.exception("Chat-Runde abgebrochen")
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"
                return
            yield f"data: {json.dumps(event)}\n\n"
    finally:
        # Hier nicht warten: Nach einem Verbindungsabbruch ist der Abbruchbereich des Servers aktiv und
        # würde jedes await sofort wieder abbrechen. Die Runde räumt deshalb in einem eigenen Task auf.
        if task is not None and not task.done():
            task.cancel()
            _finish_in_background(task)
        else:
            _finish_in_background(asyncio.ensure_future(events.aclose()))


@router.post("/chat")
async def chat(
    request: ChatRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Run one authenticated chat turn and return its SSE event stream.

    The stream starts with session metadata, forwards model/tool events and ends
    with resolved sources plus the persisted assistant-message identifier.
    """
    started_at = monotonic()
    with _http_errors():
        profile = select_chat_profile(db, request.llm_profile_id)
        sessions.assert_scope_visible(
            db,
            user,
            project_id=request.project_id,
            source_id=request.source_id,
            pinned_source_id=request.pinned_source_id,
        )
        session = sessions.open_session_for_turn(db, user, request)
        turn = sessions.begin_turn(db, session, request)
    return StreamingResponse(
        _sse(run_chat_turn(db, user, request, profile, turn, started_at)),
        media_type="text/event-stream",
    )


@router.post("/chat/sessions")
def create_chat_session(
    body: ChatSessionCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Legt eine Sitzung ohne Chat-Nachricht an (O-038) -- z.B. wenn ein Befund
    nur über mehrere Views (Graph + Code) entsteht, ohne dass der Chat je
    benutzt wurde. Braucht deshalb einen vom Nutzer vergebenen Titel; POST
    /chat oben leitet den Titel stattdessen aus der ersten Nachricht ab."""
    with _http_errors():
        session = sessions.create_session(
            db,
            user,
            title=body.title,
            project_id=body.project_id,
            source_id=body.source_id,
            snapshot=body.snapshot,
        )
    return sessions.serialize_session(session, user)


@router.get("/chat/sessions")
def get_chat_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return [sessions.serialize_session(s, user) for s in sessions.list_own_sessions(db, user)]


@router.get("/chat/sessions/page")
def get_chat_sessions_page(
    limit: int = Query(default=30, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    project_id: int | None = Query(default=None, ge=1),
    general: bool = Query(default=False),
    q: str | None = Query(default=None, max_length=200),
    pinned: bool | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Eigene Sessions seitenweise, neueste zuerst (für den Verlauf in der Seitenleiste).

    `before_id` ist die kleinste bereits geladene ID. `general=true` liefert nur
    Sessions ohne Projekt, `project_id` nur die eines Projekts. `has_more` sagt,
    ob es ältere Einträge gibt.
    """
    rows, has_more = sessions.page_own_sessions(
        db,
        user,
        limit=limit,
        before_id=before_id,
        project_id=project_id,
        general=general,
        q=q,
        pinned=pinned,
    )
    return {
        "sessions": [sessions.serialize_session(s, user) for s in rows],
        "has_more": has_more,
        "limit": limit,
    }


@router.get("/chat/sessions/by-uuid/{session_uuid}")
def get_chat_session_by_uuid(
    session_uuid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    with _http_errors():
        session = sessions.get_accessible_session(db, user, uuid=session_uuid)
    return sessions.serialize_session(session, user)


@router.get("/chat/sessions/by-uuid/{session_uuid}/messages")
def get_chat_messages_by_uuid(
    session_uuid: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    with _http_errors():
        session = sessions.get_accessible_session(db, user, uuid=session_uuid)
    return sessions.serialize_messages(session.id, db)


@router.get("/chat/sessions/{session_id}/messages")
def get_chat_messages(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    with _http_errors():
        sessions.get_accessible_session(db, user, session_id=session_id)
    return sessions.serialize_messages(session_id, db)


@router.get("/chat/sessions/{session_id}/messages/page")
def get_chat_messages_page(
    session_id: int,
    limit: int = Query(default=40, ge=2, le=200),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Nachrichten seitenweise, jüngste zuerst geladen (lange Chats).

    `before_id` ist die kleinste bereits geladene Nachrichten-ID; `has_more` sagt, ob ältere folgen.
    """
    with _http_errors():
        sessions.get_accessible_session(db, user, session_id=session_id)
    messages, has_more = sessions.page_messages(db, session_id, limit=limit, before_id=before_id)
    return {"messages": messages, "has_more": has_more}


@router.patch("/chat/sessions/{session_id}")
def update_chat_session(
    session_id: int,
    body: ChatSessionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Umbenennen und Anheften (nur der Besitzer)."""
    with _http_errors():
        session = sessions.update_session(
            db, user, session_id, title=body.title, is_pinned=body.is_pinned
        )
    return sessions.serialize_session(session, user)


@router.get("/chat/sessions/{session_id}/export")
def export_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Die Sitzung als Markdown-Datei (Fragen, Antworten, Quellen)."""
    with _http_errors():
        session = sessions.get_accessible_session(db, user, session_id=session_id)
    return Response(
        content=export_markdown(db, session),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export_filename(session)}"'},
    )


@router.post("/chat/sessions/{session_id}/share")
def share_chat_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """Macht eine Sitzung explizit öffentlich (is_public) und damit über ihre UUID
    für andere angemeldete Nutzer erreichbar — Voraussetzung für den 'Chat teilen'-
    Link im Frontend. Siehe O-032 / DOC-F-070."""
    with _http_errors():
        session = sessions.share_session(db, user, session_id)
    return sessions.serialize_session(session, user)


@router.patch("/chat/sessions/{session_id}/snapshot")
def update_chat_session_snapshot(
    session_id: int,
    body: ChatSnapshotUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    with _http_errors():
        sessions.update_snapshot(db, user, session_id, body.snapshot)
    return {"message": "Snapshot gespeichert"}


@router.delete("/chat/sessions/{session_id}")
def delete_chat_session(
    session_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    with _http_errors():
        sessions.delete_session(db, user, session_id)
    return {"message": "Session gelöscht"}


@router.post("/chat/messages/{message_id}/suggestions")
async def chat_message_suggestions(
    message_id: int,
    body: ChatFollowUpRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Drei Anschlussfragen zur Antwort (einmal erzeugt, danach gespeichert)."""
    with _http_errors():
        message = sessions.get_accessible_assistant_message(db, user, message_id)
        profile = select_chat_profile(db, body.llm_profile_id)
    return {"suggestions": await follow_up_suggestions(db, message, profile)}


@router.patch("/chat/messages/{message_id}/feedback")
def update_chat_message_feedback(
    message_id: int,
    body: ChatMessageFeedbackUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    with _http_errors():
        message = sessions.get_accessible_assistant_message(db, user, message_id)
        link_feedback = set_message_feedback(
            db, message, body.feedback, user, reason=body.reason, comment=body.comment
        )
    return {"id": message.id, "feedback": message.feedback, "link_feedback": link_feedback}


@router.patch("/chat/messages/{message_id}/view-actions/{action_id}")
def update_chat_message_view_action(
    message_id: int,
    action_id: str,
    body: ChatMessageViewActionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist the client-observed result without presenting it as a model result."""
    with _http_errors():
        message = sessions.get_accessible_assistant_message(db, user, message_id)
        update_view_action_status(db, message, action_id, body.status, user)
    return {"id": message.id, "action_id": action_id, "status": body.status}


@router.get("/admin/chat-feedback")
def get_negative_chat_feedback(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Admin-Auswertung für O-086: nur Downvotes, je mit der vorangehenden
    Nutzerfrage, seitenweise und per `q` filterbar; ohne Rückschluss auf den
    Sitzungsinhaber (Details: services.chat_feedback.list_negative_feedback)."""
    with _http_errors():
        return list_negative_feedback(db, user, limit=limit, offset=offset, q=q)


@router.get("/chat/typing-statement")
async def get_typing_statement():
    return {"statement": await generate_typing_statement()}


@router.get("/chat/project-pulse")
def get_project_pulse(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Zähler und Zufallsstichprobe echter Objektnamen für den leeren Chat."""
    assert_project_visible(project_id, user, db)
    counts, samples = project_pulse(db, project_id)
    return {"project_id": project_id, "counts": counts, "samples": samples}
