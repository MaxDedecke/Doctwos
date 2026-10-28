"""
backend/services/index_state.py
===============================
Auf welchem Stand ist der Index einer Wissensquelle?

Der Import schreibt Datei für Datei in je einer Transaktion (Abbruchtests in
parser/tests/test_import_crash_consistency.py). Jede Datei ist deshalb in sich
konsistent, der Bestand als Ganzes aber nur nach einem vollständigen Lauf:
während eines Syncs, nach einem Absturz oder nach Dateifehlern stehen Dateien
auf verschiedenen Revisionen, und Beziehungen zu geänderten Dateien sind erst
nach der abschließenden Beziehungsauflösung wieder vollständig.

Zustände:
    current       letzter Lauf vollständig (``indexed_at`` gesetzt)
    updating      ein Sync läuft (Status ``syncing`` und Sperre in Redis aktiv)
    interrupted   Status ``syncing`` ohne aktive Sperre: Prozess abgebrochen
    incomplete    letzter Lauf mit Fehlern beendet oder abgebrochen
    not_indexed   noch kein vollständiger Lauf

Für Git ist der vollständige Stand der Commit in ``sync_cursor["last_commit"]``.
"""

import logging
from typing import Optional

import redis
from sqlalchemy.orm import Session

import core.config as cfg
from doctus_models.database import KnowledgeSource

logger = logging.getLogger(__name__)

# Muss zu parser/connectors/base.py::BaseConnector.sync passen (Sperre je Quelle).
SYNC_LOCK_KEY = "lock:sync_source:{source_id}"
_RUNNING = {"syncing", "parsing"}
_NOTES = {
    "updating": "wird gerade neu eingelesen",
    "interrupted": "Einlesen wurde abgebrochen",
    "incomplete": "letztes Einlesen endete mit Fehlern",
    "not_indexed": "ist noch nicht vollständig eingelesen",
}

_client: Optional[redis.Redis] = None


def _redis() -> Optional[redis.Redis]:
    global _client
    if _client is None:
        try:
            _client = redis.from_url(cfg.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        except Exception as exc:  # noqa: BLE001 - ohne Redis gilt ein Lauf als aktiv
            logger.warning("Redis für den Indexstand nicht erreichbar: %s", exc)
            return None
    return _client


def sync_running(source_id: int) -> Optional[bool]:
    """True/False nach der Sync-Sperre; None, wenn Redis nicht antwortet."""
    client = _redis()
    if client is None:
        return None
    try:
        return bool(client.exists(SYNC_LOCK_KEY.format(source_id=source_id)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sync-Sperre von Quelle %s nicht lesbar: %s", source_id, exc)
        return None


def index_state(source: KnowledgeSource, running: Optional[bool]) -> str:
    """``running`` None (unbekannt) wertet einen laufenden Status als aktiv."""
    status = source.sync_status or "pending"
    if status in _RUNNING:
        return "interrupted" if running is False else "updating"
    if status == "completed":
        return "current"
    if status == "pending":
        return "current" if source.indexed_at else "not_indexed"
    return "incomplete" if source.indexed_at else "not_indexed"


def describe(source: KnowledgeSource, state: str) -> dict:
    cursor = source.sync_cursor if isinstance(source.sync_cursor, dict) else {}
    entry = {
        "source_id": source.id,
        "source": source.name,
        "state": state,
        "note": f"„{source.name}“ {_NOTES[state]}",
        "indexed_at": source.indexed_at.isoformat() if source.indexed_at else None,
    }
    if cursor.get("last_commit"):
        entry["indexed_revision"] = cursor["last_commit"]
    return entry


def stale_sources(
    db: Session, *, project_id: Optional[int] = None, source_id: Optional[int] = None
) -> list[dict]:
    """Quellen im Bereich, deren Index nicht auf einem einheitlichen Stand ist."""
    query = db.query(KnowledgeSource)
    if source_id is not None:
        query = query.filter(KnowledgeSource.id == source_id)
    elif project_id is not None:
        query = query.filter(KnowledgeSource.project_id == project_id)
    else:
        return []
    stale = []
    for source in query.order_by(KnowledgeSource.id):
        running = sync_running(source.id) if (source.sync_status or "") in _RUNNING else None
        state = index_state(source, running)
        if state != "current":
            stale.append(describe(source, state))
    return stale


def answer_notice(stale: list[dict]) -> str:
    """Fester Hinweis für eine Antwort aus einem nicht einheitlichen Index."""
    if not stale:
        return ""
    parts = []
    for entry in stale:
        since = []
        if entry.get("indexed_revision"):
            since.append(f"Commit {entry['indexed_revision'][:10]}")
        if entry.get("indexed_at"):
            since.append(entry["indexed_at"][:16].replace("T", " ") + " UTC")
        parts.append(
            entry["note"] + (f" (letzter vollständiger Stand: {', '.join(since)})" if since else "")
        )
    return (
        "> Hinweis zum Indexstand: "
        + "; ".join(parts)
        + ". Fundstellen können aus unterschiedlichen Ständen stammen, und Beziehungen zu "
        "geänderten Dateien können fehlen."
    )
