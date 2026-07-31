"""
parser/worker.py
================
Celery-Worker-Einstiegspunkt für den Doctus-Parser.

Aufgaben (Tasks):
    process_local_document    — Hochgeladenes Dokument parsen und einbetten
    process_knowledge_source  — Wissensquelle synchronisieren (alle Typen via Registry)
    compute_entity_links      — Semantische Links zwischen Code-Entities und Docs berechnen
    generate_diagnostics_bundle — Diagnose-Bundle erzeugen (Settings > Logs Button)

Connector-Architektur:
    Alle Wissensquellen (Git, Confluence, Jira, ...) werden über die ConnectorRegistry
    in connectors/registry.py verwaltet. Neuen Connector-Typ hinzufügen:
      → connectors/registry.py: Eintrag hinzufügen
      → Kein Ändern dieser Datei nötig.

Skalierung:
    Für Codebases > 100 GB empfiehlt sich ein separater Worker mit höherer
    Parallelität für parse_repository (Klonen + Einbetten dauert deutlich länger
    als Wissensquellen-Syncs).
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from celery import Celery
from celery.schedules import crontab
from db import REDIS_URL, SessionLocal

from core.tracing import TraceIdFilter, trace_id_scope
from tasks.document import process_local_document_async
from tasks.sync import process_knowledge_source_async
from tasks.link_builder import compute_entity_links_async
from tasks.cross_link_builder import compute_knowledge_links_async
from tasks.diagnostics import generate_diagnostics_bundle_async

# Celery installs its own root handler by default (no basicConfig call existed
# here before), so log lines from this worker had a different format than
# backend's — inconsistent when reading both side by side in a diagnostics
# bundle. force=True replaces Celery's handler with this one.
_handlers: list[logging.Handler] = [logging.StreamHandler()]
_log_file_path = os.getenv("LOG_FILE_PATH")
if _log_file_path:
    try:
        os.makedirs(os.path.dirname(_log_file_path), exist_ok=True)
        _handlers.append(logging.FileHandler(_log_file_path))
    except OSError:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(trace_id)s]: %(message)s",
    handlers=_handlers,
    force=True,
)
for _handler in logging.getLogger().handlers:
    _handler.addFilter(TraceIdFilter())

app = Celery("parser", broker=REDIS_URL, backend=REDIS_URL)
# Celery hijacks the root logger at worker startup by default, discarding the
# format/handlers/filter set up above — turn that off so our trace-ID format
# and shared-log-file FileHandler survive.
app.conf.worker_hijack_root_logger = False

app.conf.beat_schedule = {
    # Ein einziger Pull-Scan für ALLE synchronisierbaren Quelltypen statt eines
    # Copy-Paste-Blocks pro Typ. Deckt automatisch jeden in der ConnectorRegistry
    # registrierten Connector ab (Git/FolderWatch/Confluence/Jira/WebDAV) — ein
    # neuer Connector wird ohne Änderung hier geschedult.
    "scan-pull-sources": {
        "task": "scan_pull_sources",
        # Alle 15 Min ticken; welche Quelle tatsächlich synchronisiert wird,
        # entscheidet das pro-Quelle konfigurierte sync_interval_minutes im Task.
        # Der Tick muss feiner sein als das kleinste wählbare Intervall (1h),
        # damit dieses ohne systematischen Verzug eingehalten wird.
        "schedule": crontab(minute="*/15"),
    },
}





@app.task(name="process_local_document")
def process_local_document(source_id: int, file_path: str):
    """Celery-Task: Hochgeladenes lokales Dokument (PDF, Word, Text) parsen und einbetten."""
    asyncio.run(process_local_document_async(source_id, file_path))
    return {"status": "finished", "source_id": source_id}


@app.task(name="process_knowledge_source")
def process_knowledge_source(source_id: int):
    """
    Celery-Task: Wissensquelle synchronisieren (einheitlicher Task für alle Typen).

    Der passende Connector wird anhand von KnowledgeSource.type aus der
    ConnectorRegistry geladen. Neuen Typ unterstützen: nur registry.py anpassen.
    """
    asyncio.run(process_knowledge_source_async(source_id))
    return {"status": "finished", "source_id": source_id}


# ── Backward-Kompatibilität ───────────────────────────────────────────────────
# Alte Task-Namen bleiben als Aliases erhalten, bis der Backend vollständig auf
# "process_knowledge_source" umgestellt ist. Danach können diese entfernt werden.

@app.task(name="process_confluence_source")
def process_confluence_source(source_id: int):
    asyncio.run(process_knowledge_source_async(source_id))
    return {"status": "finished", "source_id": source_id}


@app.task(name="process_jira_source")
def process_jira_source(source_id: int):
    asyncio.run(process_knowledge_source_async(source_id))
    return {"status": "finished", "source_id": source_id}


@app.task(name="compute_entity_links")
def compute_entity_links(run_id: int, project_id: int, trace_id: str | None = None):
    """
    Celery-Task: Semantische Verknüpfungen zwischen Code-Entities und Wissens-Chunks
    berechnen (3 Passes: semantisch, keyword, syntaktisch). Erzeugt pending-Empfehlungen
    für die manuelle Bestätigung im Link Manager. Fortschritt/Ergebnis werden laufend
    in LinkBuilderRun geschrieben, damit ein Absturz nicht spurlos bleibt.
    """
    with trace_id_scope(trace_id):
        asyncio.run(compute_entity_links_async(run_id, project_id))
    return {"status": "finished", "run_id": run_id, "project_id": project_id}


@app.task(name="compute_knowledge_links")
def compute_knowledge_links(run_id: int, trace_id: str | None = None):
    """
    Celery-Task: Cross-Source Analyse starten. Findet semantische Verknüpfungen
    über alle Wissensquellen und Repositories hinweg. Fortschritt/Ergebnis werden
    laufend in LinkBuilderRun geschrieben, damit ein Absturz nicht spurlos bleibt.
    """
    with trace_id_scope(trace_id):
        asyncio.run(compute_knowledge_links_async(run_id))
    return {"status": "finished", "run_id": run_id}


@app.task(name="generate_diagnostics_bundle")
def generate_diagnostics_bundle(run_id: int, trace_id: str | None = None):
    """
    Celery-Task: Diagnose-Bundle erzeugen (DB-Metadaten, Service-Logs,
    Schema-Version, redaktiert) — ausgelöst über den Settings > Logs Button.
    Fortschritt/Ergebnis werden laufend in DiagnosticsRun geschrieben.
    """
    with trace_id_scope(trace_id):
        asyncio.run(generate_diagnostics_bundle_async(run_id))
    return {"status": "finished", "run_id": run_id}


# Kleine Toleranz (~halber Beat-Tick), damit eine Quelle mit Intervall N nicht
# systematisch erst beim übernächsten Tick (≈ N + Tick) läuft, sondern nahe N.
_SYNC_DUE_GRACE = timedelta(minutes=7)


@app.task(name="scan_pull_sources")
def scan_pull_sources():
    """
    Celery-Beat-Task: Fällige Wissensquellen synchronisieren.

    Läuft alle 15 Min und stößt jede synchronisierbare KnowledgeSource an, deren
    pro-Quelle konfiguriertes Intervall (sync_interval_minutes) seit last_synced_at
    abgelaufen ist. sync_interval_minutes == 0 bedeutet „nur manuell" und wird
    übersprungen. Der eigentliche Delta-/Full-Sync passiert idempotent im jeweiligen
    Connector, ein erneuter Trigger ist damit unschädlich.

    Deckt alle in der ConnectorRegistry registrierten Quelltypen ab (Git, Confluence,
    Jira, FolderWatch, WebDAV, ...). Der Typvergleich
    ist case-insensitiv, damit abweichend gespeicherte type-Strings nicht durchrutschen.
    Ein neuer Connector wird allein durch den Registry-Eintrag mitgescannt — kein Ändern
    dieser Datei.
    """
    from connectors.registry import REGISTRY
    from models.database import KnowledgeSource

    auto_sync_types = {k.lower() for k in REGISTRY.keys()}
    now = datetime.now(timezone.utc)

    db = SessionLocal()
    try:
        sources = db.query(KnowledgeSource).all()
        due_ids: list[int] = []
        for s in sources:
            if (s.type or "").lower() not in auto_sync_types:
                continue
            interval = s.sync_interval_minutes or 0
            if interval <= 0:
                continue  # nur manuell — kein Auto-Sync
            last = s.last_synced_at
            if last is None:
                due_ids.append(s.id)
                continue
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last >= timedelta(minutes=interval) - _SYNC_DUE_GRACE:
                due_ids.append(s.id)
    finally:
        db.close()

    for source_id in due_ids:
        app.send_task("process_knowledge_source", args=[source_id])

    return {"status": "finished", "triggered": len(due_ids)}

