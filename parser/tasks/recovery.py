"""Abgebrochene Syncs erkennen und sichtbar beenden.

Stirbt der Worker mitten im Sync (Speicherlimit, Neustart, hartes Zeitlimit), bleibt ``sync_status`` auf
``syncing``: Die Oberfläche zeigt einen Lauf, der nicht mehr existiert, und sperrt den Sync-Knopf; bei Quellen
mit „nur manuell“ heilt das nie. Ein laufender Sync hält immer seine Redis-Sperre mit Herzschlag
(``core/sync_lock.py``). ``syncing`` ohne Sperre ist deshalb ein abgebrochener Lauf und wird als Fehler mit
Hinweis beendet. Läuft beim Worker-Start und bei jedem Beat-Scan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from core import sync_lock
from db import SessionLocal
from doctus_models.database import KnowledgeSource

logger = logging.getLogger(__name__)

INTERRUPTED_MESSAGE = (
    "Sync wurde unterbrochen (Worker beendet, z. B. Neustart, Speicher- oder Zeitlimit). "
    "Bereits verarbeitete Dateien bleiben erhalten; ein neuer Sync setzt dort fort."
)


def recover_interrupted_syncs() -> list[int]:
    db = SessionLocal()
    recovered: list[int] = []
    try:
        for source in db.query(KnowledgeSource).filter(KnowledgeSource.sync_status == "syncing"):
            if sync_lock.is_held(source.id):
                continue
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            source.sync_status = "error"
            source.last_error = INTERRUPTED_MESSAGE
            source.progress_message = None
            source.sync_log = (source.sync_log or "") + f"[{timestamp}] {INTERRUPTED_MESSAGE}\n"
            recovered.append(source.id)
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("Abgebrochene Syncs konnten nicht geprüft werden", exc_info=True)
    finally:
        db.close()
    if recovered:
        logger.warning("Abgebrochene Syncs beendet: Quellen %s", recovered)
    return recovered


def end_interrupted_sync(source_id: int, message: str) -> None:
    """Beendet einen einzelnen Lauf mit Fehlerstatus, falls er noch als laufend gilt (Zeitlimit)."""
    db = SessionLocal()
    try:
        source = db.get(KnowledgeSource, source_id)
        if source is not None and source.sync_status in ("syncing", "pending"):
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            source.sync_status = "error"
            source.last_error = message
            source.progress_message = None
            source.sync_log = (source.sync_log or "") + f"[{timestamp}] {message}\n"
            db.commit()
    except Exception:
        db.rollback()
        logger.warning("Zeitlimit für Quelle %s nicht vermerkt", source_id, exc_info=True)
    finally:
        db.close()
