"""
backend/core/login_throttle.py
==============================
Rate-Limit für die Anmeldung (F-005, Plan §11).

Zwei Zähler, die sich absichtlich ergänzen:

* **Redis, pro (Benutzername, IP)** — kurzlebig, mit Zeitfenster. Er greift auch
  für unbekannte Benutzernamen und bremst damit das Durchprobieren von Namen,
  ohne dass dafür Zeilen in der DB entstehen.
* **DB, pro Nutzer** (`users.failed_login_count` / `users.locked_until`) — dauerhaft.
  Er überlebt einen Redis-Neustart und ist die Sperre, die ein Administrator im
  Users-Tab sieht und aufheben kann.

Maßgeblich ist der höhere der beiden Zähler. Ist Redis nicht erreichbar, bleibt
die DB-Sperre allein wirksam: die Anmeldung wird dadurch nie unmöglich, aber auch
nie ungebremst.
"""

import logging
from typing import Optional

import redis

import core.config as cfg

logger = logging.getLogger(__name__)

# Fehlversuche, die folgenlos bleiben. Der 6. Versuch sperrt zum ersten Mal.
FREE_ATTEMPTS = 5
# Sperrdauer des ersten Treffers; jeder weitere Fehlversuch verdoppelt sie.
BASE_LOCK_SECONDS = 60
MAX_LOCK_SECONDS = 3600
# Nach dieser Ruhezeit ohne Fehlversuch verfällt der Redis-Zähler.
FAILURE_WINDOW_SECONDS = 900

_KEY_PREFIX = "doctus:login:fail"
_LOCK_PREFIX = "doctus:login:lock"

_client: Optional[redis.Redis] = None
_client_broken = False


def lock_seconds_for(failed_count: int) -> int:
    """Sperrdauer in Sekunden nach `failed_count` Fehlversuchen (0 = keine Sperre).

    Rein rechnerisch und ohne Seiteneffekte — das ist der Teil, den die Tests
    ohne Redis und ohne DB prüfen können.
    """
    if failed_count <= FREE_ATTEMPTS:
        return 0
    return min(BASE_LOCK_SECONDS * 2 ** (failed_count - FREE_ATTEMPTS - 1), MAX_LOCK_SECONDS)


def _redis() -> Optional[redis.Redis]:
    """Redis-Verbindung oder None. Nach dem ersten Fehler wird nicht erneut
    verbunden — sonst zahlt jeder Login-Versuch den Verbindungs-Timeout."""
    global _client, _client_broken
    if _client_broken:
        return None
    if _client is None:
        try:
            _client = redis.from_url(
                cfg.REDIS_URL,
                socket_connect_timeout=1,
                socket_timeout=1,
                decode_responses=True,
            )
            _client.ping()
        except Exception as e:
            logger.warning("[login-throttle] Redis nicht erreichbar (%s) — nur DB-Sperre aktiv.", e)
            _client = None
            _client_broken = True
            return None
    return _client


def _key(username: str, client_ip: str) -> str:
    return f"{_KEY_PREFIX}:{username.lower()}:{client_ip}"


def _lock_key(username: str, client_ip: str) -> str:
    return f"{_LOCK_PREFIX}:{username.lower()}:{client_ip}"


def set_lock(username: str, client_ip: str, seconds: int) -> None:
    """Sperrt (Benutzername, IP) für `seconds`. Für bekannte Nutzer spiegelt der
    Aufrufer dieselbe Sperre zusätzlich nach `users.locked_until` — die hier ist
    flüchtig, die dortige überlebt einen Redis-Neustart."""
    if seconds <= 0:
        return
    client = _redis()
    if client is None:
        return
    try:
        client.setex(_lock_key(username, client_ip), seconds, "1")
    except Exception as e:
        logger.warning("[login-throttle] Redis-Sperre nicht setzbar: %s", e)


def remaining_lock_seconds(username: str, client_ip: str) -> int:
    """Restliche Sperrzeit aus Redis; 0 wenn nicht gesperrt oder Redis fehlt."""
    client = _redis()
    if client is None:
        return 0
    try:
        ttl = client.ttl(_lock_key(username, client_ip))
        # -2 = Schlüssel weg, -1 = ohne Ablauf (kann hier nicht entstehen)
        return ttl if ttl and ttl > 0 else 0
    except Exception as e:
        logger.warning("[login-throttle] Redis-TTL-Lesefehler: %s", e)
        return 0


def current_failures(username: str, client_ip: str, db_failed_count: int = 0) -> int:
    """Maßgebliche Fehlversuchszahl: der höhere von Redis- und DB-Zähler."""
    count = db_failed_count or 0
    client = _redis()
    if client is not None:
        try:
            raw = client.get(_key(username, client_ip))
            if raw is not None:
                count = max(count, int(raw))
        except Exception as e:
            logger.warning("[login-throttle] Redis-Lesefehler: %s", e)
    return count


def register_failure(username: str, client_ip: str, db_failed_count: int = 0) -> int:
    """Zählt einen Fehlversuch und liefert die neue maßgebliche Fehlversuchszahl.

    `db_failed_count` ist der bereits hochgezählte Wert aus der users-Zeile (0 für
    unbekannte Benutzernamen, für die es keine Zeile gibt)."""
    count = db_failed_count or 0
    client = _redis()
    if client is not None:
        try:
            key = _key(username, client_ip)
            pipe = client.pipeline()
            pipe.incr(key)
            pipe.expire(key, FAILURE_WINDOW_SECONDS)
            redis_count = pipe.execute()[0]
            count = max(count, int(redis_count))
        except Exception as e:
            logger.warning("[login-throttle] Redis-Schreibfehler: %s", e)
    return count


def clear_failures(username: str, client_ip: str) -> None:
    """Nach erfolgreicher Anmeldung. Löscht nur den Zähler dieser IP — Versuche
    von anderen Adressen gegen denselben Namen bleiben gezählt."""
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_key(username, client_ip), _lock_key(username, client_ip))
    except Exception as e:
        logger.warning("[login-throttle] Redis-Löschfehler: %s", e)


def client_ip_of(request) -> str:
    """Client-IP aus dem Request. Hinter dem Reverse-Proxy steht die echte Adresse
    im ersten Eintrag von X-Forwarded-For; ohne Proxy ist der Header nicht gesetzt.

    Der Header ist fälschbar — er darf deshalb nur die Granularität des Zählers
    bestimmen, nie eine Berechtigung. Wer ihn fälscht, umgeht das IP-Bucket, läuft
    aber weiter in die DB-Sperre des Nutzers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
