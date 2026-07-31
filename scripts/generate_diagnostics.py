#!/usr/bin/env python3
import os
import sys
import re
import json
import shutil
import tarfile
import subprocess
from datetime import datetime

# Define output directory and file names
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
TEMP_DIR = f"doctus-diagnostics-{TIMESTAMP}"
ARCHIVE_NAME = f"doctus-diagnostics-{TIMESTAMP}.tar.gz"

print(f"=== Starting Doctus Diagnostics Collection (Timestamp: {TIMESTAMP}) ===")

# 1. Read and parse .env to identify secrets for redaction
secrets_to_redact = set()
env_sanitized = []
env_path = ".env"

if os.path.exists(env_path):
    print("Found .env file. Parsing configuration...")
    try:
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped or line_stripped.startswith("#"):
                    env_sanitized.append(line)
                    continue
                
                # Check for KEY=VALUE
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    
                    # Identify sensitive keys
                    is_sensitive = any(s in key.upper() for s in ["PASSWORD", "SECRET", "KEY", "TOKEN"])
                    
                    if is_sensitive and val:
                        secrets_to_redact.add(val)
                        env_sanitized.append(f"{key}=[REDACTED]\n")
                    else:
                        env_sanitized.append(line)
    except Exception as e:
        print(f"Warning: Could not parse .env: {e}")
else:
    print("Warning: .env file not found in current directory. Secrets redaction from logs will be limited.")

# Helper function to sanitize a string by removing secrets
def sanitize_text(text):
    if not text:
        return ""
    sanitized = text
    for secret in secrets_to_redact:
        if len(secret) > 3:  # Only redact secrets that are long enough to avoid false positives
            sanitized = sanitized.replace(secret, "[REDACTED]")
    return sanitized

# Helper to run system commands and get stdout
def run_command(cmd, shell=False):
    try:
        res = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=30, errors='ignore')
        if res.returncode == 0:
            return res.stdout.strip()
        else:
            return f"Error (Exit Code {res.returncode}): {res.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out"
    except Exception as e:
        return f"Error: {str(e)}"

# Create temp directory
os.makedirs(TEMP_DIR, exist_ok=True)

# 2. Gather System Information
print("Gathering system specifications...")
sys_info = {
    "timestamp": TIMESTAMP,
    "os_release": run_command(["cat", "/etc/os-release"]),
    "uname": run_command(["uname", "-a"]),
    "cpu_count": run_command(["nproc"]),
    "cpu_model": run_command("grep -m 1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True),
    "memory_free": run_command(["free", "-h"]),
    "disk_space": run_command(["df", "-h", "."]),
    "nvidia_smi": run_command(["nvidia-smi"]) if shutil.which("nvidia-smi") else "NVIDIA GPU not detected or driver missing"
}

with open(os.path.join(TEMP_DIR, "system_info.json"), "w", encoding="utf-8") as f:
    json.dump(sys_info, f, indent=2)

# Write sanitized environment config
with open(os.path.join(TEMP_DIR, "env_sanitized.txt"), "w", encoding="utf-8") as f:
    f.writelines(env_sanitized)

# 3. Gather Docker Compose State
print("Gathering Docker container status...")
docker_info = {
    "docker_version": run_command(["docker", "--version"]),
    "docker_compose_version": run_command(["docker", "compose", "version"]),
    "container_status": run_command(["docker", "compose", "ps", "-a"]),
    # Image IDs, not just tags, so a support engineer can tell whether two
    # "doctus-backend-api:latest" installs are actually the same build.
    "image_ids": run_command(["docker", "compose", "images"]),
}

with open(os.path.join(TEMP_DIR, "docker_status.json"), "w", encoding="utf-8") as f:
    json.dump(docker_info, f, indent=2)

# 4. Gather Database Metadata (Sanitized)
# We pull db variables from the environment parser
db_name = "doctus"
db_user = "admin"

if os.path.exists(env_path):
    with open(env_path, "r", errors="ignore") as f:
        for line in f:
            if line.strip() and not line.strip().startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                if key == "POSTGRES_DB":
                    db_name = val
                elif key == "POSTGRES_USER":
                    db_user = val

# Check if db container is running
db_running = "Up" in run_command(["docker", "compose", "ps", "db"])
if db_running:
    print("Database container is active. Extracting metadata...")
    
    # Helper to run sql queries via docker
    def run_sql(query):
        cmd = ["docker", "compose", "exec", "-T", "db", "psql", "-U", db_user, "-d", db_name, "-c", query, "--csv"]
        # In csv format
        return run_command(cmd)

    # Fetch tables
    repos_csv = run_sql("SELECT id, name, url, branch, status, progress, progress_message, last_synced, last_commit_hash, total_files, parsed_files, parse_started_at, parse_finished_at, last_error_detail FROM repositories;")
    sources_csv = run_sql("SELECT id, name, type, url, sync_status, progress, progress_message, last_synced_at, last_error FROM knowledge_sources;")
    alerts_csv = run_sql("SELECT id, project_id, document_title, model_entity, severity, created_at, resolved FROM compliance_alerts;")
    compliance_runs_csv = run_sql("SELECT id, project_id, created_at, status, progress, progress_message, error_message, finished_at FROM compliance_runs;")

    # Summary stats
    stats_query = """
    SELECT 
      (SELECT count(*) FROM document_chunks) as total_chunks,
      (SELECT count(*) FROM code_entities) as total_entities,
      (SELECT count(*) FROM code_references) as total_references,
      (SELECT count(*) FROM entity_doc_links) as total_doc_links,
      (SELECT count(*) FROM knowledge_links) as total_knowledge_links;
    """
    stats_csv = run_sql(stats_query)

    # Save outputs
    with open(os.path.join(TEMP_DIR, "db_repositories.csv"), "w", encoding="utf-8") as f:
        f.write(sanitize_text(repos_csv))
    with open(os.path.join(TEMP_DIR, "db_knowledge_sources.csv"), "w", encoding="utf-8") as f:
        f.write(sanitize_text(sources_csv))
    with open(os.path.join(TEMP_DIR, "db_compliance_alerts.csv"), "w", encoding="utf-8") as f:
        f.write(sanitize_text(alerts_csv))
    with open(os.path.join(TEMP_DIR, "db_compliance_runs.csv"), "w", encoding="utf-8") as f:
        f.write(sanitize_text(compliance_runs_csv))
    with open(os.path.join(TEMP_DIR, "db_summary_statistics.csv"), "w", encoding="utf-8") as f:
        f.write(stats_csv)
else:
    print("Warning: Database container is offline. Skipping database metadata dump.")

# 4b. Check Applied Schema Version (Alembic)
backend_running = "Up" in run_command(["docker", "compose", "ps", "backend-api"])
if backend_running:
    print("Backend container is active. Checking applied schema version...")
    alembic_current = run_command(["docker", "compose", "exec", "-T", "backend-api", "alembic", "current"])
    with open(os.path.join(TEMP_DIR, "alembic_current.txt"), "w", encoding="utf-8") as f:
        f.write(sanitize_text(alembic_current))
else:
    print("Warning: Backend container is offline. Skipping schema version check.")

# 5. Retrieve and Sanitize Container Logs
services_to_log = ["backend-api", "parser-worker", "parser-beat", "db", "ollama", "frontend"]
for service in services_to_log:
    print(f"Retrieving logs for service: {service}...")
    log_content = run_command(["docker", "compose", "logs", "--tail=2000", service])
    sanitized_logs = sanitize_text(log_content)
    
    with open(os.path.join(TEMP_DIR, f"logs_{service}.txt"), "w", encoding="utf-8") as f:
        f.write(sanitized_logs)

# 6. Check Ollama Models
ollama_running = "Up" in run_command(["docker", "compose", "ps", "ollama"])
if ollama_running:
    print("Ollama container is active. Fetching loaded model lists...")
    models_info = run_command(["docker", "compose", "exec", "-T", "ollama", "ollama", "list"])
    with open(os.path.join(TEMP_DIR, "ollama_models.txt"), "w", encoding="utf-8") as f:
        f.write(models_info)

# 7. Package Diagnostics Bundle
print("Packaging all diagnostic files into tar.gz...")
try:
    with tarfile.open(ARCHIVE_NAME, "w:gz") as tar:
        tar.add(TEMP_DIR, arcname=os.path.basename(TEMP_DIR))
    print(f"\nSUCCESS: Diagnostic bundle created: {ARCHIVE_NAME}")
    print("----------------------------------------------------------------------")
    print("Note: All sensitive secrets (passwords, keys, tokens) read from .env")
    print("have been replaced with [REDACTED]. No file contents or blueprints")
    print("were extracted. You can safely send this archive for troubleshooting.")
    print("----------------------------------------------------------------------")
except Exception as e:
    print(f"Error packaging diagnostics: {e}")
finally:
    # Cleanup temp directory
    shutil.rmtree(TEMP_DIR)
