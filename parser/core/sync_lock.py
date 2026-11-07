"""Sperre gegen parallele Syncs derselben Quelle, mit Herzschlag.

Beat-Scan und ein manueller Klick dürfen dieselbe Quelle nicht gleichzeitig synchronisieren (doppelte Chunks).
Redis ``SET NX EX`` schließt das Rennen. Früher verlängerte nur der Fortschritt einzelner Dateien die Sperre
(Lease 1 h): Eine lange Phase ohne Dateifortschritt verlor sie mitten im Lauf, und nach einem Absturz blieb
die Quelle bis zu einer Stunde gesperrt. Jetzt verlängert ein Thread die Sperre in festen Abständen, solange
der Prozess lebt; stirbt er, ist sie nach ``LEASE_SECONDS`` frei. Eine Quelle mit Status ``syncing`` ohne
Sperre ist damit sicher ein abgebrochener Lauf (``tasks/recovery.py``).
"""

from __future__ import annotations

import logging
import os
import threading
import uuid

import redis

from db import REDIS_URL

logger = logging.getLogger(__name__)

LEASE_SECONDS = max(30, int(os.getenv("SYNC_LOCK_LEASE_SECONDS", "300")))
HEARTBEAT_SECONDS = max(5.0, LEASE_SECONDS / 5)

# Nur der Besitzer darf verlängern oder freigeben: Eine abgelaufene und neu vergebene Sperre bleibt unberührt.
_RENEW = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('EXPIRE', KEYS[1], ARGV[2]) end return 0"
)
_RELEASE = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end return 0"
)

_client = redis.from_url(REDIS_URL)
_held: dict[str, SyncLock] = {}
_held_guard = threading.Lock()


def lock_key(source_id: int) -> str:
    return f"lock:sync_source:{source_id}"


def is_held(source_id: int) -> bool:
    return bool(_client.exists(lock_key(source_id)))


class SyncLock:
    def __init__(self, source_id: int) -> None:
        self.key = lock_key(source_id)
        self.owner = f"{os.getpid()}:{uuid.uuid4().hex}"
        self._stop = threading.Event()

    def acquire(self) -> bool:
        if not _client.set(self.key, self.owner, nx=True, ex=LEASE_SECONDS):
            return False
        with _held_guard:
            _held[self.key] = self
        threading.Thread(target=self._beat, name=f"heartbeat-{self.key}", daemon=True).start()
        return True

    def _beat(self) -> None:
        while not self._stop.wait(HEARTBEAT_SECONDS):
            try:
                if not _client.eval(_RENEW, 1, self.key, self.owner, LEASE_SECONDS):
                    logger.warning("Sync-Sperre %s verloren; Herzschlag endet.", self.key)
                    return
            except Exception:
                logger.warning("Sync-Sperre %s nicht verlängert", self.key, exc_info=True)

    def release(self) -> None:
        self._stop.set()
        with _held_guard:
            if _held.get(self.key) is self:
                del _held[self.key]
        try:
            _client.eval(_RELEASE, 1, self.key, self.owner)
        except Exception:
            logger.warning("Sync-Sperre %s nicht freigegeben", self.key, exc_info=True)


def release_all() -> None:
    """Gibt alle Sperren dieses Prozesses frei. Der Celery-Task ruft das nach jedem Lauf auf: Verlässt ein
    Zeitlimit ``asyncio.run`` an der Ereignisschleife vorbei, liefe der Herzschlag sonst im wiederverwendeten
    Worker-Prozess weiter und hielte die Quelle für immer gesperrt."""
    with _held_guard:
        locks = list(_held.values())
    for lock in locks:
        lock.release()
