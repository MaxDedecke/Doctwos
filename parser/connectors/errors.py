"""Fehlerarten eines Quellen-Syncs und was nach einem Lauf am Quellenzustand festgehalten wird.

Die Art entscheidet, was der Admin tun muss (Hinweis im UI, ``backend/services/source_health.py``) und ob der
automatische Sync weiterläuft: Abgelehnte Zugangsdaten werden durch Wiederholen nicht besser, sie sperren eher
das Dienstkonto.
"""

from __future__ import annotations

import ssl
from datetime import datetime, timezone

import httpx

AUTH = "auth"
NETWORK = "network"
NOT_FOUND = "not_found"
CONFIG = "config"
SOURCE_CONTENT = "source_content"
EMBEDDING = "embedding"
INTERNAL = "internal"

# Fehlerarten, bei denen der automatische Sync nach einigen Fehlschlägen pausiert, bis jemand eingreift.
NEEDS_ACTION = {AUTH, CONFIG, NOT_FOUND}

_AUTH_WORDS = (
    "401",
    "403",
    "unauthorized",
    "forbidden",
    "authentication failed",
    "permission denied",
    "invalid credentials",
    "access denied",
    "could not read username",
)
_NETWORK_WORDS = (
    "timed out",
    "timeout",
    "connection refused",
    "connecterror",
    "could not resolve host",
    "name or service not known",
    "temporary failure in name resolution",
    "network is unreachable",
    "connection reset",
    "remote end closed",
    "server disconnected",
    "ssl",
    "certificate",
    "502",
    "503",
    "504",
)
_NOT_FOUND_WORDS = ("404", "not found", "does not exist", "repository not found")


def classify_exception(exc: BaseException) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return AUTH
        if code == 404:
            return NOT_FOUND
        if code == 429 or code >= 500:
            return NETWORK
        return CONFIG
    if isinstance(exc, (httpx.TransportError, ssl.SSLError, TimeoutError, ConnectionError)):
        return NETWORK
    name = type(exc).__name__
    if name == "EmbeddingNotConfigured":
        return EMBEDDING
    if isinstance(exc, (ValueError, PermissionError, FileNotFoundError, NotADirectoryError)):
        text_kind = classify_text(str(exc))
        return text_kind if text_kind != INTERNAL else CONFIG
    return classify_text(str(exc))


def classify_text(text: str | None) -> str:
    """Rückfall für Fehler, die nur als Text vorliegen (Git-Ausgaben, ältere Läufe)."""
    lowered = (text or "").lower()
    if any(word in lowered for word in _AUTH_WORDS):
        return AUTH
    if any(word in lowered for word in _NOT_FOUND_WORDS):
        return NOT_FOUND
    if any(word in lowered for word in _NETWORK_WORDS):
        return NETWORK
    if "embedding" in lowered or "eingebettet" in lowered:
        return EMBEDDING
    return INTERNAL


def record_outcome(source, attempted_at: datetime | None = None) -> None:
    """Nach einem Lauf: Fehler in Folge zählen bzw. zurücksetzen, Fehlerart ergänzen, Versuch festhalten."""
    source.last_attempt_at = attempted_at or datetime.now(timezone.utc)
    status = source.sync_status or ""
    if status == "completed":
        source.failure_count = 0
        source.error_kind = None
    elif status == "error":
        source.failure_count = (source.failure_count or 0) + 1
        if not source.error_kind:
            source.error_kind = classify_text(source.last_error)
