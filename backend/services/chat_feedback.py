"""
backend/services/chat_feedback.py
=================================
Nutzer-Feedback zu Chat-Antworten.

Ein Downvote ist mehr als ein Flag an der Nachricht: Er meldet die zitierten
Dokument-Verknüpfungen als fragwürdig (zwei Sitzungen in 30 Tagen setzen einen
bestätigten Link zurück auf „pending") und legt einen Diagnosefall an. Ein
Upvote oder Zurücknehmen nimmt beides für diese Antwort zurück, ohne einen
bereits ausgelösten Review-Status automatisch rückgängig zu machen.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, aliased

from core.teams import is_admin
from doctus_models.database import (
    ChatLinkFeedbackSignal,
    ChatMessage,
    EntityDocLink,
    KnowledgeLink,
    User,
)
from services.chat_errors import ChatForbidden, ChatInvalid
from services.chat_feedback_diagnostics import capture_downvote_case, remove_case_for_message

FEEDBACK_VALUES = (None, "up", "down")
# Obergrenze der neuesten Downvotes, die eine Textsuche durchsieht (Inhalte sind
# verschlüsselt und werden dafür in Python entschlüsselt).
FEEDBACK_SEARCH_SCAN_LIMIT = 5000


def _cited_link_targets(db: Session, sources: list[dict]) -> set[tuple[str, int]]:
    """Resolve persisted cited chunk IDs to links without filename heuristics."""
    chunk_ids = {
        source.get("chunk_id")
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("chunk_id"), int)
    }
    if not chunk_ids:
        return set()

    targets = {
        ("entity_doc", link.id)
        for link in db.query(EntityDocLink.id).filter(EntityDocLink.chunk_id.in_(chunk_ids)).all()
    }
    targets.update(
        ("knowledge", link.id)
        for link in db.query(KnowledgeLink.id)
        .filter(
            (KnowledgeLink.source_a_chunk_id.in_(chunk_ids))
            | (KnowledgeLink.source_b_chunk_id.in_(chunk_ids))
        )
        .all()
    )
    return targets


def _apply_downvote_link_signals(db: Session, message: ChatMessage, user: User) -> dict:
    """Record a downvote and move links to pending after two sessions in 30 days."""
    targets = _cited_link_targets(db, message.sources_json or [])
    now = datetime.now(timezone.utc)
    for link_type, link_id in targets:
        signal = (
            db.query(ChatLinkFeedbackSignal)
            .filter(
                ChatLinkFeedbackSignal.chat_message_id == message.id,
                ChatLinkFeedbackSignal.link_type == link_type,
                ChatLinkFeedbackSignal.link_id == link_id,
            )
            .first()
        )
        if signal:
            signal.revoked_at = None
            signal.user_id = user.id
        else:
            db.add(
                ChatLinkFeedbackSignal(
                    chat_message_id=message.id,
                    chat_session_id=message.session_id,
                    user_id=user.id,
                    link_type=link_type,
                    link_id=link_id,
                )
            )
    db.flush()

    cutoff = now - timedelta(days=30)
    marked_for_review = []
    for link_type, link_id in targets:
        signals = (
            db.query(ChatLinkFeedbackSignal.chat_session_id)
            .filter(
                ChatLinkFeedbackSignal.link_type == link_type,
                ChatLinkFeedbackSignal.link_id == link_id,
                ChatLinkFeedbackSignal.revoked_at.is_(None),
                ChatLinkFeedbackSignal.created_at >= cutoff,
            )
            .all()
        )
        # Mehrere Antworten derselben Sitzung bleiben bewusst nur ein Signal.
        if len({session_id for (session_id,) in signals}) < 2:
            continue
        model = EntityDocLink if link_type == "entity_doc" else KnowledgeLink
        link = db.query(model).filter(model.id == link_id).first()
        # Ein manueller Ablehnungsentscheid bleibt bestehen. Ein bereits auf
        # "pending" gesetzter Link wird beim späteren Rücknehmen nicht zurückgedreht.
        if link and link.status == "approved":
            link.status = "pending"
            link.reviewed_at = None
            marked_for_review.append({"type": link_type, "id": link_id})
    return {"signals_recorded": len(targets), "marked_for_review": marked_for_review}


def _revoke_downvote_link_signals(db: Session, message_id: int) -> None:
    """Deactivate only this answer's signals; prior review escalation persists."""
    db.query(ChatLinkFeedbackSignal).filter(
        ChatLinkFeedbackSignal.chat_message_id == message_id,
        ChatLinkFeedbackSignal.revoked_at.is_(None),
    ).update(
        {ChatLinkFeedbackSignal.revoked_at: datetime.now(timezone.utc)}, synchronize_session=False
    )


def set_message_feedback(
    db: Session, message: ChatMessage, feedback: Optional[str], user: User
) -> dict:
    """Setzt das Feedback einer Assistenten-Antwort samt Folgesignalen und committet."""
    if feedback not in FEEDBACK_VALUES:
        raise ChatInvalid("feedback muss 'up', 'down' oder null sein")
    message.feedback = feedback
    if feedback == "down":
        link_feedback = _apply_downvote_link_signals(db, message, user)
        capture_downvote_case(db, message)
    else:
        _revoke_downvote_link_signals(db, message.id)
        remove_case_for_message(db, message.id)
        link_feedback = {"signals_recorded": 0, "marked_for_review": []}
    db.commit()
    return link_feedback


def list_negative_feedback(
    db: Session, user: User, *, limit: int, offset: int, q: Optional[str]
) -> dict:
    """Downvotes mit vorangehender Nutzerfrage, seitenweise und optional gefiltert.

    Wer die Sitzung geführt hat, wird bewusst nicht ausgegeben: jede Zeile trägt
    nur ein ``session_label`` (Rang der Sitzung nach ihrem jüngsten Downvote,
    über alle Downvotes berechnet), das Einträge desselben Gesprächs erkennbar
    macht, aber keinen Rückschluss auf Sitzung oder Inhaber erlaubt. Die
    Textsuche sieht höchstens FEEDBACK_SEARCH_SCAN_LIMIT Downvotes durch.
    """
    if not is_admin(user):
        raise ChatForbidden("Nur für Administratoren")
    downvoted = (ChatMessage.role == "assistant", ChatMessage.feedback == "down")

    session_rows = (
        db.query(ChatMessage.session_id)
        .filter(*downvoted)
        .group_by(ChatMessage.session_id)
        .order_by(func.max(ChatMessage.created_at).desc(), func.max(ChatMessage.id).desc())
        .all()
    )
    session_labels = {row[0]: index + 1 for index, row in enumerate(session_rows)}

    earlier_user_message = aliased(ChatMessage)
    question_sql = (
        db.query(earlier_user_message.content)
        .filter(
            earlier_user_message.session_id == ChatMessage.session_id,
            earlier_user_message.role == "user",
            earlier_user_message.id < ChatMessage.id,
        )
        .order_by(earlier_user_message.id.desc())
        .limit(1)
        .correlate(ChatMessage)
        .scalar_subquery()
    )

    ordering = (ChatMessage.created_at.desc(), ChatMessage.id.desc())
    needle = (q or "").strip().casefold()
    search_truncated = False
    if needle:
        # Nachrichteninhalte sind at-rest verschlüsselt (siehe doctus_models.database) und
        # lassen sich deshalb nicht per SQL-LIKE durchsuchen. Die Suche läuft daher
        # gestreamt auf den entschlüsselten Werten und hält nur die Treffer-IDs im
        # Speicher; nur die angeforderte Seite wird danach vollständig geladen.
        matching_sessions = {sid for sid, label in session_labels.items() if str(label) == needle}
        scan = (
            db.query(ChatMessage, question_sql.label("question"))
            .filter(*downvoted)
            .order_by(*ordering)
            .limit(FEEDBACK_SEARCH_SCAN_LIMIT + 1)
            .yield_per(200)
        )
        matching_ids: list[int] = []
        scanned = 0
        for message, question in scan:
            scanned += 1
            if scanned > FEEDBACK_SEARCH_SCAN_LIMIT:
                search_truncated = True
                break
            if (
                message.session_id in matching_sessions
                or needle in (message.content or "").casefold()
                or needle in (question or "").casefold()
            ):
                matching_ids.append(message.id)
        total = len(matching_ids)
        page_ids = matching_ids[offset : offset + limit]
        rows = (
            db.query(ChatMessage, question_sql.label("question"))
            .filter(ChatMessage.id.in_(page_ids))
            .order_by(*ordering)
            .all()
            if page_ids
            else []
        )
    else:
        total = db.query(func.count(ChatMessage.id)).filter(*downvoted).scalar() or 0
        rows = (
            db.query(ChatMessage, question_sql.label("question"))
            .filter(*downvoted)
            .order_by(*ordering)
            .offset(offset)
            .limit(limit)
            .all()
        )
    entries = [
        {
            "message_id": message.id,
            "session_label": session_labels.get(message.session_id, len(session_labels) + 1),
            "question": question,
            "answer": message.content,
            "sources_json": message.sources_json or [],
            "metadata_json": message.metadata_json or {},
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        for message, question in rows
    ]
    return {
        "entries": entries,
        "total": total,
        "offset": offset,
        "limit": limit,
        "search_truncated": search_truncated,
    }
