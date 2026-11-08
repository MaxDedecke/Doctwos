"""
parser/worker.py
================
Celery-Worker-Einstiegspunkt für den Doctus-Parser.

Aufgaben (Tasks):
    process_local_document    — Hochgeladenes Dokument parsen und einbetten
    process_knowledge_source  — Wissensquelle synchronisieren (alle Typen via Registry)
    compute_entity_links      — Semantische Links zwischen Code-Entities und Docs berechnen
    generate_diagnostics_bundle — Diagnose-Bundle erzeugen (Settings > Logs Button)
    rebuild_code_file_edges   — Grundgerüst und Gruppen der Graph-Übersicht eines Projekts neu berechnen
    rebuild_code_file_groups  — nur die Gruppen-Knoten neu berechnen (nach Topic-Änderungen)

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
from celery.signals import worker_process_init, worker_ready
from db import REDIS_URL, SessionLocal
from doctus_models.database import DiagnosticsRun, KnowledgeSource, LinkBuilderRun

from core import sync_lock
from core.tracing import TraceIdFilter, trace_id_scope
from tasks.document import process_local_document_async
from tasks.sync import process_knowledge_source_async
from tasks.link_builder import compute_entity_links_async
from tasks.cross_link_builder import compute_knowledge_links_async
from tasks.diagnostics import generate_diagnostics_bundle_async
from tasks.file_edges import refresh_code_file_edges, refresh_code_file_groups
from tasks.recovery import end_interrupted_sync, recover_interrupted_syncs

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


def _refresh_worker_ai_settings() -> None:
    """Make the current DB profile visible to connector metadata as well as HTTP calls."""
    try:
        from core import config
        from ollama_client import _load_server_settings

        settings = _load_server_settings()
        if settings:
            config.EMBED_MODEL = settings["embedding_model"]
            if (
                os.getenv("LLM_MODEL", "disabled") == config.LLM_MODEL
                or config.LLM_MODEL == "disabled"
            ):
                config.LLM_MODEL = settings["llm_model"]
    except Exception:
        logging.getLogger(__name__).debug("Could not refresh worker AI settings", exc_info=True)


def _register_task_id(model, row_id: int, task_id: str | None) -> None:
    """Persist the Celery id so the Job Center can revoke auto-triggered work."""
    if not task_id:
        return
    db = SessionLocal()
    try:
        row = db.query(model).filter(model.id == row_id).first()
        if row and row.celery_task_id != task_id:
            row.celery_task_id = task_id
            db.commit()
    except Exception:
        db.rollback()
        logging.getLogger(__name__).warning("Could not register Celery task id", exc_info=True)
    finally:
        db.close()


@worker_process_init.connect
def _reset_db_pool_after_fork(**kwargs):
    """Geforkte Prefork-Kinder dürfen keine vom Elternprozess geerbten DB-Verbindungen nutzen."""
    from db import engine

    engine.dispose(close=False)


@worker_process_init.connect
def _warmup_antlr_cobol_parser(**kwargs):
    """Phase 3 (E-11, docs/ENTSCHEIDUNGEN.md): zahlt ANTLRs einmaligen
    Full-Context-Fallback (siehe cobol/antlr_bridge.py::warmup()) beim
    Start jedes geforkten Worker-Prozesses statt bei der ersten echten
    COBOL-Datei - der ATN-DFA-Cache lebt pro Prozess, `worker_process_init`
    feuert deshalb einmal je Prefork-Kind, nicht nur einmal insgesamt.
    Fehlschlag ist kein Blocker (nur ein langsamerer erster echter Parse),
    deshalb hier bewusst nur geloggt statt den Worker-Start zu blockieren."""
    try:
        import time

        from cobol.antlr_bridge import warmup as _antlr_warmup

        t0 = time.monotonic()
        _antlr_warmup()
        logging.getLogger(__name__).info(
            "ANTLR-COBOL-Warmup abgeschlossen (%.3fs).", time.monotonic() - t0
        )
    except Exception:
        logging.getLogger(__name__).warning(
            "ANTLR-COBOL-Warmup fehlgeschlagen - kein Blocker, nur langsamerer erster Parse.",
            exc_info=True,
        )


@app.task(name="refresh_insight_embeddings", time_limit=120)
def refresh_insight_embeddings_task():
    from tasks.insight_embeddings import refresh_insight_embeddings

    return asyncio.run(refresh_insight_embeddings())


app.conf.beat_schedule = {
    "insight-embeddings": {"task": "refresh_insight_embeddings", "schedule": crontab(minute="*/2")},
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


# Zeitlimits je Lauf. Das eigene Limit bricht den Sync geordnet ab (Aufräumen, Log, Sperre) und setzt eine
# lesbare Fehlermeldung. Blockiert die Ereignisschleife selbst, beendet Celerys hartes Limit 10 Minuten später
# den Prozess; dann läuft die Sperre ab und die Wiederherstellung meldet den Abbruch.
SYNC_TIME_LIMIT = int(float(os.getenv("SYNC_TIME_LIMIT_HOURS", "24")) * 3600)
DOCUMENT_TIME_LIMIT = int(float(os.getenv("DOCUMENT_TIME_LIMIT_HOURS", "2")) * 3600)
HARD_LIMIT_GRACE = 600


@worker_ready.connect
def _end_syncs_interrupted_by_a_previous_worker(**kwargs):
    recover_interrupted_syncs()


def _run_source_task(source_id: int, coroutine, limit_seconds: int) -> None:
    """Führt einen Sync mit Zeitlimit aus und hinterlässt nie eine Sperre im wiederverwendeten Worker-Prozess."""
    try:
        asyncio.run(asyncio.wait_for(coroutine, limit_seconds))
    except TimeoutError:
        end_interrupted_sync(
            source_id,
            f"Sync nach dem Zeitlimit von {limit_seconds / 3600:g} h beendet. Bereits verarbeitete "
            "Dateien bleiben erhalten; ein neuer Sync setzt dort fort.",
        )
        raise
    finally:
        sync_lock.release_all()


@app.task(
    name="process_local_document",
    bind=True,
    time_limit=DOCUMENT_TIME_LIMIT + HARD_LIMIT_GRACE,
)
def process_local_document(task, source_id: int, file_path: str, trace_id: str | None = None):
    """Celery-Task: Hochgeladenes lokales Dokument (PDF, Word, Text) parsen und einbetten."""
    _register_task_id(KnowledgeSource, source_id, task.request.id)
    _refresh_worker_ai_settings()
    with trace_id_scope(trace_id):
        _run_source_task(
            source_id,
            process_local_document_async(source_id, file_path),
            DOCUMENT_TIME_LIMIT,
        )
    return {"status": "finished", "source_id": source_id}


@app.task(
    name="process_knowledge_source",
    bind=True,
    time_limit=SYNC_TIME_LIMIT + HARD_LIMIT_GRACE,
)
def process_knowledge_source(
    task, source_id: int, force_reindex: bool = False, trace_id: str | None = None
):
    """
    Celery-Task: Wissensquelle synchronisieren (einheitlicher Task für alle Typen).

    Der passende Connector wird anhand von KnowledgeSource.type aus der
    ConnectorRegistry geladen. Neuen Typ unterstützen: nur registry.py anpassen.

    trace_id (O-072): verknüpft die Sync-Log-Zeilen dieses Task-Laufs mit dem
    ursprünglichen Backend-Request, der ihn ausgelöst hat (analog zu
    compute_entity_links/compute_knowledge_links/generate_diagnostics_bundle,
    die trace_id_scope() bereits nutzen) — ohne das war ein Kundenbericht
    "meine Quelle hat nicht synchronisiert" nur über KnowledgeSource.sync_log
    allein einzugrenzen.
    """
    _register_task_id(KnowledgeSource, source_id, task.request.id)
    _refresh_worker_ai_settings()
    with trace_id_scope(trace_id):
        _run_source_task(
            source_id,
            process_knowledge_source_async(source_id, force_reindex=force_reindex),
            SYNC_TIME_LIMIT,
        )
    return {"status": "finished", "source_id": source_id}


# ── Backward-Kompatibilität ───────────────────────────────────────────────────
# Alte Task-Namen bleiben als Aliases erhalten, bis der Backend vollständig auf
# "process_knowledge_source" umgestellt ist. Danach können diese entfernt werden.


@app.task(
    name="process_confluence_source",
    bind=True,
    time_limit=SYNC_TIME_LIMIT + HARD_LIMIT_GRACE,
)
def process_confluence_source(task, source_id: int):
    _register_task_id(KnowledgeSource, source_id, task.request.id)
    _refresh_worker_ai_settings()
    _run_source_task(source_id, process_knowledge_source_async(source_id), SYNC_TIME_LIMIT)
    return {"status": "finished", "source_id": source_id}


@app.task(
    name="process_jira_source",
    bind=True,
    time_limit=SYNC_TIME_LIMIT + HARD_LIMIT_GRACE,
)
def process_jira_source(task, source_id: int):
    _register_task_id(KnowledgeSource, source_id, task.request.id)
    _refresh_worker_ai_settings()
    _run_source_task(source_id, process_knowledge_source_async(source_id), SYNC_TIME_LIMIT)
    return {"status": "finished", "source_id": source_id}


@app.task(name="compute_entity_links", bind=True)
def compute_entity_links(
    task,
    run_id: int,
    project_id: int,
    trace_id: str | None = None,
    min_confidence: int | None = None,
    embedding_model: str | None = None,
):
    """
    Celery-Task: Semantische Verknüpfungen zwischen Code-Entities und Wissens-Chunks
    berechnen (3 Passes: semantisch, keyword, syntaktisch). Erzeugt pending-Empfehlungen
    für die manuelle Bestätigung im Link Manager. Fortschritt/Ergebnis werden laufend
    in LinkBuilderRun geschrieben, damit ein Absturz nicht spurlos bleibt.

    min_confidence: vom Nutzer im Link Manager eingestellter Mindest-Prozentsatz
    (0-100) für die LLM-Konfidenz, ab der ein Kandidat als Vorschlag gespeichert
    wird. None = Default aus link_builder.LLM_MIN_CONFIDENCE.
    """
    _register_task_id(LinkBuilderRun, run_id, task.request.id)
    _refresh_worker_ai_settings()
    with trace_id_scope(trace_id):
        asyncio.run(
            compute_entity_links_async(
                run_id,
                project_id,
                min_confidence=min_confidence,
                embedding_model=embedding_model,
            )
        )
    return {"status": "finished", "run_id": run_id, "project_id": project_id}


@app.task(name="compute_knowledge_links", bind=True)
def compute_knowledge_links(
    task,
    run_id: int,
    trace_id: str | None = None,
    min_confidence: int | None = None,
    embedding_model: str | None = None,
    project_id: int | None = None,
    source_ids: list[int] | None = None,
):
    """
    Celery-Task: Cross-Source Analyse starten. Findet semantische Verknüpfungen
    über alle Wissensquellen und Repositories hinweg. Fortschritt/Ergebnis werden
    laufend in LinkBuilderRun geschrieben, damit ein Absturz nicht spurlos bleibt.

    min_confidence: siehe compute_entity_links — hier für die Cross-Source-LLM-
    Bewertung in cross_link_builder.LLM_MIN_CONFIDENCE.
    """
    _register_task_id(LinkBuilderRun, run_id, task.request.id)
    _refresh_worker_ai_settings()
    with trace_id_scope(trace_id):
        asyncio.run(
            compute_knowledge_links_async(
                run_id,
                min_confidence=min_confidence,
                embedding_model=embedding_model,
                project_id=project_id,
                source_ids=source_ids,
            )
        )
    return {"status": "finished", "run_id": run_id}


@app.task(name="rebuild_code_file_edges")
def rebuild_code_file_edges_task(project_id: int | None):
    """Celery-Task: Dateikanten der Graph-Übersicht neu berechnen, wenn sich Code-Beziehungen
    außerhalb eines Syncs geändert haben (z. B. eine Quelle wurde gelöscht)."""
    db = SessionLocal()
    try:
        built = refresh_code_file_edges(db, project_id)
        db.commit()
    finally:
        db.close()
    return {"status": "finished", "project_id": project_id, "file_edges": built}


@app.task(name="rebuild_code_file_groups")
def rebuild_code_file_groups_task(project_id: int | None):
    """Celery-Task: Gruppen-Knoten der Graph-Übersicht neu berechnen (Topics wurden geändert)."""
    db = SessionLocal()
    try:
        built = refresh_code_file_groups(db, project_id)
        db.commit()
    finally:
        db.close()
    return {"status": "finished", "project_id": project_id, "groups": built}


@app.task(name="generate_diagnostics_bundle", bind=True)
def generate_diagnostics_bundle(task, run_id: int, trace_id: str | None = None):
    """
    Celery-Task: Diagnose-Bundle erzeugen (DB-Metadaten, Service-Logs,
    Schema-Version, redaktiert) — ausgelöst über den Settings > Logs Button.
    Fortschritt/Ergebnis werden laufend in DiagnosticsRun geschrieben.
    """
    _register_task_id(DiagnosticsRun, run_id, task.request.id)
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
    from doctus_models.database import KnowledgeSource

    # Erst abgebrochene Läufe beenden: Ihr hängender „syncing“-Status würde sonst als laufender Sync gelten.
    recover_interrupted_syncs()
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
