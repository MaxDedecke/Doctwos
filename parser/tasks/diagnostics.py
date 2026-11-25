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
  - Service-Logs: direktes Lesen aus dem gemeinsamen /var/log/codena-Mount
    (siehe docker-compose.yml) statt `docker compose logs`.
  - Docker-Container-Status/Image-Digests/`ollama list` bleiben bewusst
    außen vor — dafür weiterhin scripts/generate_diagnostics.py auf dem Host
    verwenden (dokumentiert in docs/DEPLOYMENT.md).

Redaction-Logik dupliziert aus generate_diagnostics.py statt importiert:
backend/parser sind getrennte Docker-Images ohne gemeinsames Package (gleiches
Muster wie codena_models/database.py).
"""

import csv
import io
import json
import logging
import os
import re
import shutil
import tarfile
from datetime import datetime, timezone

from sqlalchemy import text

from db import SessionLocal
from codena_models.database import (
    AIProfile,
    AISettings,
    DiagnosticsRun,
    EmbeddingMigration,
    EmbeddingProfile,
    KnowledgeSource,
    LinkBuilderRun,
    SourceScanFile,
)

logger = logging.getLogger(__name__)

LOGS_ROOT = "/var/log/codena"
LOG_TAIL_BYTES = 8 * 1024 * 1024
SYNC_LOG_TAIL_LINES = 400
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


# Zugangsdaten, die nicht als Umgebungsvariable bekannt sind (Quell-URLs mit Benutzer und Token, Header in Logzeilen).
_GENERIC_SECRETS = (
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1[REDACTED]@"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"), r"\1[REDACTED]"),
    (
        re.compile(
            r"(?i)((?:private-token|x-api-key|authorization)[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]{6,}"
        ),
        r"\1[REDACTED]",
    ),
    (re.compile(r"(?i)((?:token|password|passwd|secret|api_key)=)[^&\s]{4,}"), r"\1[REDACTED]"),
)


def _sanitize(text_value: str, secrets: set[str]) -> str:
    if not text_value:
        return ""
    sanitized = text_value
    for secret in secrets:
        sanitized = sanitized.replace(secret, "[REDACTED]")
    for pattern, replacement in _GENERIC_SECRETS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def _rows_to_csv(rows, columns) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    if columns is None:
        columns = list(rows[0]) if rows else []
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row[col] for col in columns])
        return buf.getvalue()
    writer.writerow(columns)
    for row in rows:
        writer.writerow([getattr(row, col) for col in columns])
    return buf.getvalue()


def _write_versions(db, out_dir: str) -> None:
    """Welche Stände laufen: Parser-Image, Backend-Image (über /version), Modellpaket, Datenbankschema."""
    import platform

    import httpx

    import codena_models

    info = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "parser": {
            "git_sha": os.getenv("GIT_SHA", "unknown"),
            "build_time": os.getenv("BUILD_TIME", "unknown"),
            "codena_models": getattr(codena_models, "__version__", "unknown"),
            "python": platform.python_version(),
        },
        "codena_version": os.getenv("CODENA_VERSION", "unknown"),
    }
    try:
        info["alembic"] = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001
        info["alembic"] = f"error: {exc}"
    for name, url in (
        ("backend", "http://backend-api:8000/version"),
        ("health", "http://backend-api:8000/health"),
    ):
        try:
            info[name] = httpx.get(url, timeout=5.0).json()
        except Exception as exc:  # noqa: BLE001
            info[name] = f"error: {exc}"
    with open(os.path.join(out_dir, "versions.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=2, default=str)


def _dump_db_tables(db, out_dir: str, secrets: set[str]) -> None:
    tables = {
        "db_knowledge_sources.csv": (
            KnowledgeSource,
            [
                "id",
                "name",
                "type",
                "url",
                "project_id",
                "branch",
                "sync_status",
                "error_kind",
                "failure_count",
                "last_attempt_at",
                "last_synced_at",
                "indexed_at",
                "sync_interval_minutes",
                "embedding_model",
                "progress_message",
                "total_files",
                "parsed_files",
                "last_error",
                "last_error_detail",
            ],
        ),
        # Profile ohne Schlüssel: welcher Endpunkt, welches Modell, welche Fenster.
        "db_embedding_profiles.csv": (
            EmbeddingProfile,
            ["id", "name", "provider", "model", "base_url", "path", "dimension", "context_length"],
        ),
        "db_ai_profiles.csv": (
            AIProfile,
            [
                "id",
                "name",
                "kind",
                "provider",
                "protocol",
                "llm_model",
                "llm_base_url",
                "llm_path",
                "llm_context_length",
                "llm_max_concurrency",
                "llm_temperature",
            ],
        ),
        "db_ai_settings.csv": (
            AISettings,
            ["id", "active_profile_id", "active_embedding_profile_id"],
        ),
        "db_embedding_migrations.csv": (
            EmbeddingMigration,
            [
                "id",
                "project_id",
                "status",
                "previous_model",
                "target_model",
                "target_dimension",
                "total",
                "done",
                "error",
                "created_at",
                "switched_at",
            ],
        ),
        "db_link_builder_runs.csv": (
            LinkBuilderRun,
            [
                "id",
                "task_type",
                "project_id",
                "created_at",
                "status",
                "progress_message",
                "error_message",
                "finished_at",
                "links_created",
            ],
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

    counts = db.execute(
        text(
            "SELECT embedding_model, embedding_dimension, count(*) FROM document_chunks "
            "GROUP BY embedding_model, embedding_dimension ORDER BY 3 DESC"
        )
    ).all()
    with open(os.path.join(out_dir, "db_chunks_per_model.csv"), "w", encoding="utf-8") as f:
        f.write(
            _rows_to_csv([dict(zip(("model", "dimension", "chunks"), r)) for r in counts], None)
        )

    # Die letzten Zeilen jedes Sync-Logs: dort steht, was beim Einlesen einer Quelle geschah.
    logs_dir = os.path.join(out_dir, "sync_logs")
    os.makedirs(logs_dir, exist_ok=True)
    for source_id, name, log in db.query(
        KnowledgeSource.id, KnowledgeSource.name, KnowledgeSource.sync_log
    ):
        if not log:
            continue
        tail = "\n".join(log.splitlines()[-SYNC_LOG_TAIL_LINES:])
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "")[:60]
        with open(os.path.join(logs_dir, f"{source_id}_{safe}.txt"), "w", encoding="utf-8") as f:
            f.write(_sanitize(tail, secrets))


def _copy_service_logs(out_dir: str, secrets: set[str]) -> None:
    """Reads every service's own log file directly off the shared /var/log/codena
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
            # Aktuelle Datei und die letzte gekürzte (.1); ältere Stände bleiben auf dem Host.
            if not os.path.isfile(src_path) or not (
                log_file.endswith(".log") or log_file.endswith(".log.1")
            ):
                continue
            try:
                with open(src_path, "rb") as f:
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    f.seek(max(0, size - LOG_TAIL_BYTES))
                    content = f.read().decode("utf-8", errors="ignore")
                if size > LOG_TAIL_BYTES:
                    content = (
                        f"[… nur die letzten {LOG_TAIL_BYTES // (1024 * 1024)} MB …]\n" + content
                    )
            except OSError as e:
                content = f"[Konnte {src_path} nicht lesen: {e}]"
            target = f"logs_{service}{'_previous' if log_file.endswith('.1') else ''}.txt"
            with open(os.path.join(out_dir, target), "w", encoding="utf-8") as f:
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
    if run.status == "cancelled":
        logger.info(f"[Diagnostics] Run {run_id} wurde vor dem Start abgebrochen.")
        db.close()
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    bundle_name = f"codena-diagnostics-{timestamp}"
    work_dir = os.path.join(BUNDLE_OUTPUT_DIR, f".tmp-{run_id}-{bundle_name}")
    archive_path = os.path.join(BUNDLE_OUTPUT_DIR, f"{bundle_name}.tar.gz")

    try:
        run.status = "running"
        db.commit()

        os.makedirs(work_dir, exist_ok=True)
        secrets = _collect_secrets_from_env()

        logger.info(f"[Diagnostics] Run {run_id}: sammle Versionen und DB-Metadaten…")
        _write_versions(db, work_dir)
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
