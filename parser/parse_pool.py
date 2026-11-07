"""Prozess-Pool für die Strukturparser (CPU-gebunden, reines Python).

ANTLR-/Lexer-Parsing hält den GIL; `asyncio.to_thread` nutzt deshalb nur einen
Kern, solange ein Sync läuft. Der Pool verteilt die Dateien auf mehrere Prozesse.
Pro Sync wird ein eigener Pool angelegt, weil das Ergebnis der prepare_source-
Hooks (z. B. der Copybook-Index) einmalig per Initializer in die Worker geht
und nicht bei jedem Aufruf neu serialisiert wird.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from typing import Any

_prepared_by_lang: dict[str, Any] = {}
# Eine Datei, deren Parser länger braucht, landet im Text-Fallback statt ihren Prozess unbegrenzt zu belegen.
# Die Zeit zählt ab der Übergabe an den Pool; der Standard lässt auch voller Warteschlange viel Raum.
PARSE_FILE_TIMEOUT = max(10.0, float(os.getenv("PARSE_FILE_TIMEOUT_SECONDS", "900")))


class ParseTimeout(RuntimeError):
    """Der Strukturparser einer Datei hat das Zeitlimit überschritten."""


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


async def parse(pool: ProcessPoolExecutor, lang: str, text: str, path: str, profile: Any):
    """Parst eine Datei im Pool. Nach dem Zeitlimit wird der Pool beendet, weil sich ein einzelner hängender
    Aufruf nicht abbrechen lässt; die übrigen laufenden Dateien scheitern dann mit ``BrokenProcessPool`` und
    werden vom Aufrufer einzeln nachgeparst."""
    return await run_with_timeout(pool, _parse_in_worker, lang, text, path, profile)


async def run_with_timeout(pool: ProcessPoolExecutor, fn, *args: Any):
    future = asyncio.get_running_loop().run_in_executor(pool, fn, *args)
    try:
        return await asyncio.wait_for(future, PARSE_FILE_TIMEOUT)
    except TimeoutError:
        terminate(pool)
        raise ParseTimeout(f"Parser-Zeitlimit von {PARSE_FILE_TIMEOUT:g} s überschritten") from None


def terminate(pool: ProcessPoolExecutor) -> None:
    for process in list((getattr(pool, "_processes", None) or {}).values()):
        process.kill()
    pool.shutdown(wait=False, cancel_futures=True)
