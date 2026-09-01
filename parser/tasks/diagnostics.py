"""
parser/tasks/diagnostics.py
============================
Celery-Gegenstück zum bestehenden scripts/generate_diagnostics.py, ausgelöst
über den "Diagnose-Bundle erzeugen"-Button in Settings > Logs statt per
Shell-Zugriff.

Wichtiger Unterschied zum Skript: scripts/generate_diagnostics.py läuft auf
dem Host und ruft `docker compose exec`/`docker compose logs` auf — dieser
Task läuft im parser-worker-Container, der weder Docker-CLI noch Docker-
Socket hat (bewusst, um keinen Docker-Socket-Mount für ein "Diagnose"-Feature
einzuführen). Deshalb:
  - DB-Metadaten: direkte SQLAlchemy-Queries statt `psql` via docker exec.
  - Service-Logs: direktes Lesen aus dem gemeinsamen /var/log/doctus-Mount
    (siehe docker-compose.yml) statt `docker compose logs`.
  - Docker-Container-Status/Image-Digests/`ollama list` bleiben bewusst
    außen vor — dafür weiterhin scripts/generate_diagnostics.py auf dem Host
    verwenden (dokumentiert in docs/DEPLOYMENT.md).

Redaction-Logik dupliziert aus generate_diagnostics.py statt importiert:
backend/parser sind getrennte Docker-Images ohne gemeinsames Package (gleiches
Muster wie models/database.py).
"""

import csv
import io
import logging
import os
import re
import shutil
import tarfile
from datetime import datetime, timezone

from sqlalchemy import text

from db import SessionLocal
from models.database import (
    DiagnosticsRun,
    KnowledgeSource,
    LinkBuilderRun,
    SourceScanFile,
)

logger = logging.getLogger(__name__)

LOGS_ROOT = "/var/log/doctus"
BUNDLE_OUTPUT_DIR = "/repos/diagnostics"

SENSITIVE_ENV_MARKERS = ("PASSWORD", "SECRET", "KEY", "TOKEN")


def _collect_secrets_from_env() -> set[str]:
    """Same redaction target as generate_diagnostics.py's .env scan, but read
    straight from the process environment — this container has no .env file,
    just the already-resolved env vars docker-compose.yml passes in."""
    secrets = set()
    for key, val in os.environ.items():
        if val and len(val) > 3 and any(marker in key.upper() for marker in SENSITIVE_ENV_MARKERS):
            secrets.add(val)

    # DATABASE_URL embeds the password inline (postgresql://user:PASS@host/db)
    # — not caught by the key-name scan above since the secret isn't its own
    # env var here.
    db_url = os.environ.get("DATABASE_URL", "")
    match = re.search(r"://[^:/]+:([^@]+)@", db_url)
    if match and len(match.group(1)) > 3:
        secrets.add(match.group(1))

    return secrets


def _sanitize(text_value: str, secrets: set[str]) -> str:
    if not text_value:
        return ""
    sanitized = text_value
    for secret in secrets:
        sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized


def _rows_to_csv(rows, columns) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([getattr(row, col) for col in columns])
    return buf.getvalue()


def _dump_db_tables(db, out_dir: str, secrets: set[str]) -> None:
    tables = {
        "db_knowledge_sources.csv": (
            KnowledgeSource,
            ["id", "name", "type", "url", "sync_status", "last_synced_at", "last_error"],
        ),
        "db_link_builder_runs.csv": (
            LinkBuilderRun,
            ["id", "task_type", "project_id", "created_at", "status", "progress_message",
             "error_message", "finished_at", "links_created"],
        ),
        # Fehlerregister der Ingestion (F-029): welche Datei ist warum nicht
        # parsebar. parse_error kann Pfade enthalten, läuft daher durch _sanitize.
        "db_source_scan_files.csv": (
            SourceScanFile,
            ["id", "source_id", "file_path", "parse_status", "parse_error", "indexed_at"],
        ),
    }
    for filename, (model, columns) in tables.items():
        rows = db.query(model).all()
        csv_text = _rows_to_csv(rows, columns)
        with open(os.path.join(out_dir, filename), "w", encoding="utf-8") as f:
            f.write(_sanitize(csv_text, secrets))

    alembic_version = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    with open(os.path.join(out_dir, "alembic_current.txt"), "w", encoding="utf-8") as f:
        f.write(str(alembic_version or "unknown"))


def _copy_service_logs(out_dir: str, secrets: set[str]) -> None:
    """Reads every service's own log file directly off the shared /var/log/doctus
    mount — the reduced, no-Docker-CLI-needed equivalent of `docker compose
    logs` in generate_diagnostics.py."""
    if not os.path.isdir(LOGS_ROOT):
        return
    for service in sorted(os.listdir(LOGS_ROOT)):
        service_dir = os.path.join(LOGS_ROOT, service)
        if not os.path.isdir(service_dir):
            continue
        for log_file in sorted(os.listdir(service_dir)):
            src_path = os.path.join(service_dir, log_file)
            if not os.path.isfile(src_path):
                continue
            try:
                with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError as e:
                content = f"[Konnte {src_path} nicht lesen: {e}]"
            with open(os.path.join(out_dir, f"logs_{service}.txt"), "w", encoding="utf-8") as f:
                f.write(_sanitize(content, secrets))


async def generate_diagnostics_bundle_async(run_id: int) -> None:
    """
    run_id zeigt auf eine DiagnosticsRun-Zeile (vom Aufrufer als "pending"
    angelegt), die dieser Task auf running/completed/failed aktualisiert —
    ohne das wäre ein Absturz hier (ausgerechnet im Diagnose-Feature selbst)
    wieder nur eine stille logger.error-Zeile.
    """
    db = SessionLocal()
    run = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == run_id).first()
    if not run:
        logger.error(f"[Diagnostics] DiagnosticsRun {run_id} nicht gefunden — abgebrochen.")
        db.close()
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_name = f"doctus-diagnostics-{timestamp}"
    work_dir = os.path.join(BUNDLE_OUTPUT_DIR, f".tmp-{run_id}-{bundle_name}")
    archive_path = os.path.join(BUNDLE_OUTPUT_DIR, f"{bundle_name}.tar.gz")

    try:
        run.status = "running"
        db.commit()

        os.makedirs(work_dir, exist_ok=True)
        secrets = _collect_secrets_from_env()

        logger.info(f"[Diagnostics] Run {run_id}: sammle DB-Metadaten…")
        _dump_db_tables(db, work_dir, secrets)

        logger.info(f"[Diagnostics] Run {run_id}: sammle Service-Logs…")
        _copy_service_logs(work_dir, secrets)

        logger.info(f"[Diagnostics] Run {run_id}: packe Bundle…")
        os.makedirs(BUNDLE_OUTPUT_DIR, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(work_dir, arcname=bundle_name)

        run.status = "completed"
        run.progress_message = "Bundle erstellt (DB-Metadaten, Service-Logs, Schema-Version)."
        run.bundle_path = archive_path
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        logger.info(f"[Diagnostics] Run {run_id}: fertig — {archive_path}")
    except Exception as e:
        logger.error(f"[Diagnostics] Run {run_id} fehlgeschlagen: {e}")
        db.rollback()
        run = db.query(DiagnosticsRun).filter(DiagnosticsRun.id == run_id).first()
        if run:
            run.status = "failed"
            run.error_message = str(e)[:500]
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        if os.path.isdir(work_dir):
            shutil.rmtree(work_dir, ignore_errors=True)
        db.close()
