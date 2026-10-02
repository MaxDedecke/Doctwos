"""Prozess-Pool für die Strukturparser (CPU-gebunden, reines Python).

ANTLR-/Lexer-Parsing hält den GIL; `asyncio.to_thread` nutzt deshalb nur einen
Kern, solange ein Sync läuft. Der Pool verteilt die Dateien auf mehrere Prozesse.
Pro Sync wird ein eigener Pool angelegt, weil das Ergebnis der prepare_source-
Hooks (z. B. der Copybook-Index) einmalig per Initializer in die Worker geht
und nicht bei jedem Aufruf neu serialisiert wird.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any

_prepared_by_lang: dict[str, Any] = {}


def default_workers() -> int:
    configured = os.getenv("PARSE_WORKERS")
    if configured:
        return max(0, int(configured))
    return max(1, min(os.cpu_count() or 1, 6))


def _init_worker(prepared_by_lang: dict[str, Any]) -> None:
    global _prepared_by_lang
    _prepared_by_lang = prepared_by_lang


def _parse_in_worker(lang: str, text: str, path: str, profile: Any):
    from core.registry import STRUCTURE_PARSERS

    kwargs: dict[str, Any] = {"prepared_source": _prepared_by_lang.get(lang)}
    if profile is not None:
        kwargs["profile"] = profile
    return STRUCTURE_PARSERS[lang].parse(text, path, **kwargs)


def _ping() -> bool:
    return True


def create_pool(workers: int, prepared_by_lang: dict[str, Any]) -> ProcessPoolExecutor:
    # Celery-Prefork-Kinder sind Daemon-Prozesse, und multiprocessing verbietet
    # denen Kindprozesse ("daemonic processes are not allowed to have children").
    # Dieser Prozess macht nichts anderes, als Tasks abzuarbeiten -- das Flag
    # bleibt deshalb dauerhaft aus, weil der Pool seine Worker lazy startet.
    current = multiprocessing.current_process()
    current._config["daemon"] = False
    # billiard ersetzt den Auth-Key durch einen eigenen Typ, der sich nie pickeln
    # lässt -- spawn braucht aber den der Standardbibliothek.
    current._config["authkey"] = multiprocessing.process.AuthenticationString(
        bytes(current._config["authkey"])
    )
    # spawn übernimmt das sys.path des Elternprozesses; im Celery-Prozess steht das
    # Arbeitsverzeichnis dort nicht drin, `parse_pool` wäre im Kind nicht importierbar.
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    # spawn statt fork: der Celery-Prozess hält DB-/Redis-Verbindungen und Threads.
    return ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=_init_worker,
        initargs=(prepared_by_lang,),
    )
