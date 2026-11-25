#!/usr/bin/env python3
"""Diagnosepaket auf dem Codena-Host: alles, was zum Nachvollziehen eines Fehlers aus der Ferne nötig ist.

Aufruf im Installationsverzeichnis (dort, wo docker-compose.yml und .env liegen), vor jedem Neustart:

    python3 generate_diagnostics.py            # oder: python3 scripts/generate_diagnostics.py im Repository

Ein Neustart leert den Log-Puffer des Containers, und Docker hält je Dienst nur 3 × 10 MB. Erst sammeln, dann
eingreifen. Das Ergebnis ``codena-diagnostics-<Zeit>.tar.gz`` enthält keine Dokumentinhalte, Chats oder Vektoren,
nur Zustand, Versionen, Konfiguration (Geheimnisse ersetzt) und Logs. Es braucht nur Python 3 und Docker.

Gegenüber dem Paket aus Einstellungen > Logs kommt hinzu, was nur der Host sieht: Containerzustand mit Neustarts,
OOM-Kills und Exit-Codes, Images, Ressourcen, GPU, Docker-Logs aller Dienste und die Celery-Warteschlangen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = f"codena-diagnostics-{STAMP}"
ARCHIVE = f"{OUT}.tar.gz"
LOG_TAIL_LINES = "5000"
FILE_LOG_TAIL_BYTES = 8 * 1024 * 1024
SENSITIVE = ("PASSWORD", "SECRET", "KEY", "TOKEN")

GENERIC_SECRETS = (
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


def run(cmd: list[str], timeout: int = 120, stdin: str | None = None) -> str:
    try:
        done = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, input=stdin, errors="replace"
        )
        out = done.stdout
        if done.returncode != 0:
            out += f"\n[exit {done.returncode}] {done.stderr.strip()}"
        return out
    except FileNotFoundError:
        return f"[nicht verfügbar: {cmd[0]}]"
    except subprocess.TimeoutExpired:
        return f"[Zeitüberschreitung nach {timeout}s: {' '.join(cmd)}]"


def compose(*args: str, timeout: int = 120, stdin: str | None = None) -> str:
    return run(["docker", "compose", *args], timeout=timeout, stdin=stdin)


# ── Geheimnisse aus .env ──────────────────────────────────────────────────────
env: dict[str, str] = {}
secrets: set[str] = set()
env_lines: list[str] = []
if os.path.exists(".env"):
    with open(".env", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                env[key] = value
                if value and len(value) > 3 and any(m in key.upper() for m in SENSITIVE):
                    secrets.add(value)
                    line = f"{key}=[REDACTED]\n"
            env_lines.append(line)
else:
    print("Warnung: keine .env im aktuellen Verzeichnis; im Installationsverzeichnis aufrufen.")


def clean(text: str) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    for pattern, replacement in GENERIC_SECRETS:
        text = pattern.sub(replacement, text)
    return text


def write(name: str, content: str) -> None:
    path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(clean(content))


os.makedirs(OUT, exist_ok=True)
print(f"=== Codena-Diagnose {STAMP} ===")
write("env_sanitized.txt", "".join(env_lines))

# ── Host und Docker ───────────────────────────────────────────────────────────
print("Host, Docker, GPU …")
host = {
    "uname": run(["uname", "-a"]),
    "os_release": open("/etc/os-release").read() if os.path.exists("/etc/os-release") else "",
    "cpus": str(os.cpu_count()),
    "memory": run(["free", "-h"]),
    "disk_install_dir": run(["df", "-h", "."]),
    "disk_data_dirs": run(
        ["du", "-sh", "data/postgres", "data/repos", "data/ollama", "data/logs"], timeout=300
    ),
    "nvidia_smi_host": run(["nvidia-smi"]),
    "docker_version": run(["docker", "version"]),
    "compose_version": compose("version"),
    "docker_info": run(["docker", "info"]),
    "docker_df": run(["docker", "system", "df"]),
}
write("host.json", json.dumps(host, indent=2))

services = [s for s in compose("config", "--services").split() if not s.startswith("[")]
write("compose_ps.txt", compose("ps", "-a"))
write("compose_images.txt", compose("images"))
write("compose_config_images.txt", compose("config", "--images"))
containers = [c for c in compose("ps", "-a", "--format", "{{.Name}}").split() if c]
state = (
    run(
        [
            "docker",
            "inspect",
            "--format",
            "{{.Name}} status={{.State.Status}} restarts={{.RestartCount}} oom_killed={{.State.OOMKilled}} "
            "exit={{.State.ExitCode}} started={{.State.StartedAt}} finished={{.State.FinishedAt}} "
            "health={{if .State.Health}}{{.State.Health.Status}}{{end}} image={{.Config.Image}} "
            "memory_limit={{.HostConfig.Memory}}",
            *containers,
        ]
    )
    if containers
    else "[keine Container]"
)
write("containers_state.txt", state)
write("containers_stats.txt", run(["docker", "stats", "--no-stream", "--no-trunc"], timeout=60))

# ── Laufende Version und Zustand aus Sicht des Backends ───────────────────────
probe = (
    "import json,urllib.request\n"
    "out={}\n"
    "for n,u in (('version','http://localhost:8000/version'),('health','http://localhost:8000/health')):\n"
    "    try: out[n]=json.load(urllib.request.urlopen(u,timeout=10))\n"
    "    except Exception as e: out[n]=str(e)\n"
    "print(json.dumps(out,indent=2))\n"
)
write(
    "backend_version_health.json", compose("exec", "-T", "backend-api", "python", "-", stdin=probe)
)
write("alembic_current.txt", compose("exec", "-T", "backend-api", "alembic", "current"))

# ── Datenbank: Zustand, keine Inhalte ─────────────────────────────────────────
db_user = env.get("POSTGRES_USER", "admin")
db_name = env.get("POSTGRES_DB", "codena")
QUERIES = {
    "db_knowledge_sources.csv": (
        "SELECT id, name, type, url, project_id, branch, sync_status, error_kind, failure_count, last_attempt_at, "
        "last_synced_at, indexed_at, sync_interval_minutes, embedding_model, progress_message, total_files, "
        "parsed_files, last_error, last_error_detail FROM knowledge_sources ORDER BY id"
    ),
    "db_embedding_profiles.csv": (
        "SELECT id, name, provider, model, base_url, path, dimension, context_length FROM embedding_profiles"
    ),
    "db_ai_profiles.csv": (
        "SELECT id, name, kind, provider, protocol, llm_model, llm_base_url, llm_path, llm_context_length, "
        "llm_max_concurrency, llm_temperature FROM ai_profiles"
    ),
    "db_ai_settings.csv": "SELECT id, active_profile_id, active_embedding_profile_id FROM ai_settings",
    "db_embedding_migrations.csv": "SELECT * FROM embedding_migrations ORDER BY id DESC LIMIT 50",
    "db_chunks_per_model.csv": (
        "SELECT embedding_model, embedding_dimension, count(*) FROM document_chunks GROUP BY 1, 2 ORDER BY 3 DESC"
    ),
    "db_link_builder_runs.csv": (
        "SELECT id, task_type, project_id, status, progress_message, error_message, created_at, finished_at "
        "FROM link_builder_runs ORDER BY id DESC LIMIT 100"
    ),
    "db_scan_file_errors.csv": (
        "SELECT source_id, file_path, parse_status, parse_error, indexed_at FROM source_scan_files "
        "WHERE parse_status IS DISTINCT FROM 'ok' ORDER BY indexed_at DESC NULLS LAST LIMIT 1000"
    ),
    "db_table_sizes.csv": (
        "SELECT relname, n_live_tup, pg_size_pretty(pg_total_relation_size(relid)) AS size "
        "FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 30"
    ),
    "db_activity.csv": (
        "SELECT state, wait_event_type, count(*), max(now() - query_start) AS longest "
        "FROM pg_stat_activity WHERE datname = current_database() GROUP BY 1, 2"
    ),
    "db_size.csv": "SELECT pg_size_pretty(pg_database_size(current_database())), version()",
}
if "db" in services:
    print("Datenbank-Metadaten …")
    for name, sql in QUERIES.items():
        write(
            name,
            compose("exec", "-T", "db", "psql", "-U", db_user, "-d", db_name, "--csv", "-c", sql),
        )
    sync_logs = compose(
        "exec",
        "-T",
        "db",
        "psql",
        "-U",
        db_user,
        "-d",
        db_name,
        "-At",
        "-c",
        "SELECT id || E'\\t' || coalesce(name,'') || E'\\t' || "
        "replace(right(coalesce(sync_log,''), 60000), E'\\n', E'\\\\n') FROM knowledge_sources",
        timeout=180,
    )
    for row in sync_logs.splitlines():
        parts = row.split("\t", 2)
        if len(parts) == 3 and parts[2]:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", parts[1])[:60]
            write(f"sync_logs/{parts[0]}_{safe}.txt", parts[2].replace("\\n", "\n"))

# ── Warteschlangen ────────────────────────────────────────────────────────────
if "redis" in services:
    queues = {
        q: compose("exec", "-T", "redis", "redis-cli", "LLEN", q).strip()
        for q in ("celery", "global_link_runs")
    }
    queues["info_memory"] = compose("exec", "-T", "redis", "redis-cli", "INFO", "memory")
    queues["sync_locks"] = compose(
        "exec", "-T", "redis", "redis-cli", "--scan", "--pattern", "lock:*"
    )
    write("redis_queues.json", json.dumps(queues, indent=2))

# ── Logs: Docker (je Dienst) und Dateien unter data/logs ──────────────────────
for service in services:
    print(f"Logs {service} …")
    write(
        f"logs/docker_{service}.txt",
        compose("logs", "--timestamps", f"--tail={LOG_TAIL_LINES}", service, timeout=180),
    )
if os.path.isdir("data/logs"):
    for folder, _dirs, files in os.walk("data/logs"):
        for name in files:
            if not (name.endswith(".log") or name.endswith(".log.1")):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as handle:
                    handle.seek(0, os.SEEK_END)
                    size = handle.tell()
                    handle.seek(max(0, size - FILE_LOG_TAIL_BYTES))
                    content = handle.read().decode("utf-8", errors="ignore")
            except OSError as exc:
                content = f"[nicht lesbar: {exc}]"
            write(
                f"logs/file_{os.path.relpath(path, 'data/logs').replace(os.sep, '_')}.txt", content
            )

# ── Modellserver ──────────────────────────────────────────────────────────────
if "ollama" in services and "ollama" in compose("ps", "--services", "--status", "running"):
    write(
        "ollama.txt",
        "\n\n".join(
            compose("exec", "-T", "ollama", *cmd)
            for cmd in (["ollama", "list"], ["ollama", "ps"], ["nvidia-smi"])
        ),
    )

# ── Packen ────────────────────────────────────────────────────────────────────
with tarfile.open(ARCHIVE, "w:gz") as tar:
    tar.add(OUT, arcname=OUT)
shutil.rmtree(OUT, ignore_errors=True)
print(f"\nFertig: {ARCHIVE}")
print(
    "Geheimnisse aus .env, URL-Zugangsdaten und Token in Logzeilen sind ersetzt. Keine Inhalte, Chats oder Vektoren."
)
sys.exit(0)
