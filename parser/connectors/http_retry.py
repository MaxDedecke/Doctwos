"""
parser/connectors/http_retry.py
================================
Gemeinsamer Retry-Helper für CDE-Connectoren (Autodesk, Dalux).

Deckt zwei Fehlerklassen ab, die bei langen Crawls/Downloads gegen Cloud-CDEs
regelmäßig auftreten:
    - 429/5xx (Rate-Limit / transiente Serverfehler): Retry mit Backoff,
      Retry-After-Header wird respektiert wenn vorhanden.
    - 401 (Token mitten im Sync abgelaufen): optionaler einmaliger
      Token-Refresh + Retry über den ``refresh_auth``-Callback.

Andere 4xx-Fehler (400/403/404/...) sind keine transienten Fehler und werden
sofort weitergereicht.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Awaitable, Callable

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_BACKOFF = 30.0


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """Wartezeit vor dem nächsten Versuch: Retry-After-Header, sonst Exponential-Backoff."""
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            try:
                dt = parsedate_to_datetime(retry_after)
                tz = dt.tzinfo or timezone.utc
                return max(0.0, (dt - datetime.now(tz)).total_seconds())
            except Exception:
                pass
    return min(2 ** attempt, _MAX_BACKOFF)


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers_fn: Callable[[], dict],
    refresh_auth: Callable[[], Awaitable[None]] | None = None,
    max_attempts: int = 5,
    log: Callable[[str], None] | None = None,
    **kwargs,
) -> httpx.Response:
    """GET/POST mit 429/5xx-Retry (Retry-After-aware) + einmaligem Token-Refresh bei 401.

    ``headers_fn`` wird bei jedem Versuch neu aufgerufen (statt einmalig ein dict zu
    übergeben), damit nach einem Token-Refresh die aktuellen Header verwendet werden.
    """
    auth_retried = False
    attempt = 0
    while True:
        try:
            response = await client.request(method, url, headers=headers_fn(), **kwargs)
        except httpx.TransportError as e:
            if attempt < max_attempts - 1:
                delay = min(2 ** attempt, _MAX_BACKOFF)
                if log:
                    log(
                        f"[WARNUNG] Netzwerkfehler bei {url}: {e} — "
                        f"Retry {attempt + 1}/{max_attempts} in {delay:.1f}s."
                    )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise

        if response.status_code == 401 and refresh_auth is not None and not auth_retried:
            auth_retried = True
            if log:
                log(f"[WARNUNG] 401 von {url} — erneuere Token und wiederhole Request.")
            await refresh_auth()
            continue

        if response.status_code in _RETRYABLE_STATUS and attempt < max_attempts - 1:
            delay = _retry_delay(response, attempt)
            if log:
                log(
                    f"[WARNUNG] HTTP {response.status_code} von {url} — "
                    f"Retry {attempt + 1}/{max_attempts} in {delay:.1f}s."
                )
            await asyncio.sleep(delay)
            attempt += 1
            continue

        response.raise_for_status()
        return response


@asynccontextmanager
async def stream_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    headers_fn: Callable[[], dict],
    refresh_auth: Callable[[], Awaitable[None]] | None = None,
    max_attempts: int = 5,
    timeout: httpx.Timeout | None = None,
    log: Callable[[str], None] | None = None,
):
    """Wie ``request_with_retry``, aber für ``client.stream()``-Downloads.

    Der Status ist unmittelbar nach dem Betreten des Context-Managers bekannt, bevor der
    Body gelesen wird — Retry/Refresh laufen deshalb nur VOR dem ``yield``. Der Context-
    Manager wird dafür manuell (``__aenter__``/``__aexit__``) statt über ein verschachteltes
    ``async with`` verwaltet: ein ``@asynccontextmanager`` darf nach einer per ``athrow()``
    hineingeworfenen Exception (z. B. ein Verbindungsabbruch beim Chunk-Schreiben im Aufrufer,
    lange NACH dem ``yield``) kein zweites Mal yielden — ein verschachteltes ``async with``
    das den Retry-``continue`` über den ``yield`` hinweg umspannt, würde also bei einem
    Fehler *während* des Downloads mit ``RuntimeError: generator didn't stop after athrow()``
    abstürzen, statt (korrekterweise) den Fehler einfach durchzureichen.
    """
    auth_retried = False
    attempt = 0
    while True:
        cm = client.stream(method, url, headers=headers_fn(), timeout=timeout)
        try:
            response = await cm.__aenter__()
        except httpx.TransportError as e:
            if attempt < max_attempts - 1:
                delay = min(2 ** attempt, _MAX_BACKOFF)
                if log:
                    log(
                        f"[WARNUNG] Netzwerkfehler bei {url}: {e} — "
                        f"Retry {attempt + 1}/{max_attempts} in {delay:.1f}s."
                    )
                await asyncio.sleep(delay)
                attempt += 1
                continue
            raise

        if response.status_code == 401 and refresh_auth is not None and not auth_retried:
            auth_retried = True
            await cm.__aexit__(None, None, None)
            if log:
                log(f"[WARNUNG] 401 von {url} — erneuere Token und wiederhole Download.")
            await refresh_auth()
            continue

        if response.status_code in _RETRYABLE_STATUS and attempt < max_attempts - 1:
            delay = _retry_delay(response, attempt)
            await cm.__aexit__(None, None, None)
            if log:
                log(
                    f"[WARNUNG] HTTP {response.status_code} von {url} — "
                    f"Retry {attempt + 1}/{max_attempts} in {delay:.1f}s."
                )
            await asyncio.sleep(delay)
            attempt += 1
            continue

        # Ab hier kein Retry mehr — Body-Lesefehler beim Aufrufer werden nicht verschluckt.
        try:
            response.raise_for_status()
            yield response
        finally:
            await cm.__aexit__(None, None, None)
        return
