"""Zustand einer Wissensquelle für Admins: was ist los, seit wann, was ist zu tun.

Die Fehlerart schreibt der Parser (``parser/connectors/errors.py``); hier wird sie in einen Handlungshinweis
übersetzt und um zwei abgeleitete Angaben ergänzt: ob der automatische Sync pausiert und ob der Index älter ist,
als das Sync-Intervall erwarten lässt. Muss zu ``parser/worker.py::_auto_sync_due`` passen.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from doctus_models.database import KnowledgeSource

PAUSE_AFTER_FAILURES = 3
NEEDS_ACTION = {"auth", "config", "not_found"}
# Quellen ohne automatischen Sync gelten nach so vielen Stunden als veraltet; 0 schaltet das ab.
MANUAL_MAX_AGE_HOURS = max(0, int(os.getenv("SOURCE_MANUAL_MAX_AGE_HOURS", "0") or 0))

HINTS = {
    "auth": "Zugangsdaten abgelehnt (401/403). Token oder Passwort der Quelle erneuern bzw. Rechte des "
    "Dienstkontos prüfen, dann manuell synchronisieren.",
    "network": "Quelle nicht erreichbar (Netzwerk, DNS, Zertifikat oder Serverfehler). Erreichbarkeit vom "
    "Codena-Host prüfen; der automatische Sync versucht es mit wachsendem Abstand erneut.",
    "not_found": "Adresse, Projekt, Bereich oder Branch existiert nicht (mehr). Konfiguration der Quelle prüfen.",
    "config": "Konfiguration der Quelle ist ungültig. Einstellungen der Quelle prüfen.",
    "source_content": "Einzelne Inhalte konnten nicht verarbeitet werden oder die Quelle lieferte deutlich weniger "
    "als zuvor. Sync-Log prüfen; der vorhandene Index bleibt erhalten.",
    "embedding": "Embedding-Dienst nicht erreichbar oder nicht eingerichtet. Embedding-Profil unter "
    "Einstellungen > KI prüfen; der nächste Sync holt die fehlenden Dokumente nach.",
    "internal": "Unerwarteter Fehler. Sync-Log und Diagnosepaket prüfen.",
}


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    return (
        value.replace(tzinfo=timezone.utc) if value is not None and value.tzinfo is None else value
    )


def auto_sync_paused(source: KnowledgeSource) -> bool:
    return (source.error_kind or "") in NEEDS_ACTION and (
        source.failure_count or 0
    ) >= PAUSE_AFTER_FAILURES


def is_overdue(source: KnowledgeSource, now: Optional[datetime] = None) -> bool:
    """Index älter, als Intervall (bzw. Höchstalter manueller Quellen) erlaubt."""
    indexed = _aware(source.indexed_at)
    if indexed is None:
        return False
    now = now or datetime.now(timezone.utc)
    interval = source.sync_interval_minutes or 0
    if interval > 0:
        allowed = max(timedelta(minutes=3 * interval), timedelta(minutes=interval + 60))
    elif MANUAL_MAX_AGE_HOURS:
        allowed = timedelta(hours=MANUAL_MAX_AGE_HOURS)
    else:
        return False
    return now - indexed > allowed


def health(source: KnowledgeSource) -> dict:
    kind = source.error_kind if (source.sync_status or "") == "error" else None
    return {
        "error_kind": kind,
        "error_hint": HINTS.get(kind or "", None),
        "failure_count": source.failure_count or 0,
        "last_attempt_at": source.last_attempt_at.isoformat() if source.last_attempt_at else None,
        "indexed_at": source.indexed_at.isoformat() if source.indexed_at else None,
        "auto_sync_paused": auto_sync_paused(source),
        "overdue": is_overdue(source),
    }
