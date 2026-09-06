"""Local, opt-in capture of minimal support diagnostics from chat downvotes."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.database import (
    ChatFeedbackDiagnosticCase,
    ChatFeedbackDiagnosticSettings,
    ChatMessage,
    ChatSession,
)


def get_settings(db: Session) -> ChatFeedbackDiagnosticSettings:
    settings = db.query(ChatFeedbackDiagnosticSettings).order_by(ChatFeedbackDiagnosticSettings.id).first()
    if settings is None:
        settings = ChatFeedbackDiagnosticSettings()
        db.add(settings)
        db.flush()
    return settings


def purge_expired_cases(db: Session, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    return (
        db.query(ChatFeedbackDiagnosticCase)
        .filter(ChatFeedbackDiagnosticCase.created_at < cutoff)
        .delete(synchronize_session=False)
    )


def capture_downvote_case(db: Session, message: ChatMessage) -> None:
    """Persist exactly one minimized case when the customer enabled collection."""
    settings = get_settings(db)
    purge_expired_cases(db, settings.retention_days)
    if not settings.collection_enabled:
        return
    if db.query(ChatFeedbackDiagnosticCase.id).filter(
        ChatFeedbackDiagnosticCase.chat_message_id == message.id
    ).first():
        return

    session = db.query(ChatSession).filter(ChatSession.id == message.session_id).first()
    question = None
    if session:
        previous = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.session_id == session.id,
                ChatMessage.role == "user",
                ChatMessage.id < message.id,
            )
            .order_by(ChatMessage.id.desc())
            .first()
        )
        question = previous.content if previous else None

    metadata = message.metadata_json or {}
    db.add(
        ChatFeedbackDiagnosticCase(
            chat_message_id=message.id,
            project_id=session.project_id if session else None,
            source_id=session.source_id if session else None,
            question=question,
            answer=message.content,
            sources_json=message.sources_json or [],
            # agent_steps deliberately excluded: tool results can be much more
            # sensitive than the answer and are not required for first-line triage.
            model=metadata.get("model"),
            provider=metadata.get("provider"),
        )
    )


def remove_case_for_message(db: Session, message_id: int) -> None:
    """A withdrawn downvote must not remain in the opt-in diagnostic dataset."""
    db.query(ChatFeedbackDiagnosticCase).filter(
        ChatFeedbackDiagnosticCase.chat_message_id == message_id
    ).delete(synchronize_session=False)
