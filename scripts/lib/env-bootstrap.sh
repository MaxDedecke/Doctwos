#!/bin/sh
# Shared by install.sh and install-offline.sh. Source it, then call bootstrap_env.
set -e

# nvidia-smi only proves the driver is installed, not that Docker can actually
# hand a container a GPU — that needs the NVIDIA Container Toolkit's runtime
# registered with Docker too (`nvidia-ctk runtime configure` adds an "nvidia"
# entry to `docker info`'s Runtimes line). Checking both avoids wiring in
# docker-compose.gpu.yml on a host that would then just fail to start ollama.
gpu_ready_for_docker() {
    command -v nvidia-smi >/dev/null 2>&1 || return 1
    docker info 2>/dev/null | grep -qi nvidia
}

# Keeps COMPOSE_FILE in .env in sync with GPU availability, so every
# `docker compose` call — this installer's own, and any manual command run
# later per docs/DEPLOYMENT.md (e.g. after a `git pull` update) — picks up
# docker-compose.gpu.yml without -f flags needing to be remembered by hand.
# Deliberately separate from bootstrap_env (which only runs on a brand-new
# .env): safe to call on every install(-offline).sh run, including reinstalls/
# updates on an existing .env, since it only ever touches this one line.
sync_compose_file() {
    repo_root="$1"
    base_compose_file="$2"
    env_file="$repo_root/.env"
    [ -f "$env_file" ] || return 0

    compose_files="$base_compose_file"
    if gpu_ready_for_docker; then
        echo "NVIDIA GPU + Container Toolkit detected — enabling GPU passthrough for Ollama (docker-compose.gpu.yml)."
        compose_files="$compose_files:docker-compose.gpu.yml"
    elif command -v nvidia-smi >/dev/null 2>&1; then
        echo "NVIDIA GPU detected, but Docker's NVIDIA Container Toolkit runtime isn't registered — Ollama will run CPU-only."
        echo "Install it, then re-run this installer to enable GPU passthrough (see docs/DEPLOYMENT.md, \"GPU passthrough (Ollama)\")."
    fi

    if grep -q "^COMPOSE_FILE=" "$env_file"; then
        sed -e "s|^COMPOSE_FILE=.*|COMPOSE_FILE=${compose_files}|" "$env_file" > "$env_file.tmp"
        mv "$env_file.tmp" "$env_file"
    else
        echo "COMPOSE_FILE=${compose_files}" >> "$env_file"
    fi
}

bootstrap_env() {
    repo_root="$1"

    if [ -f "$repo_root/.env" ]; then
        echo "Found existing .env — leaving it as is."
        return
    fi

    echo "No .env found, creating one from .env.example..."
    cp "$repo_root/.env.example" "$repo_root/.env"

    master_key=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null) \
        || master_key=$(docker run --rm python:3.11-slim sh -c "pip install -q cryptography >/dev/null 2>&1 && python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"")
    session_key=$(openssl rand -base64 32)

    # Portable in-place edit (BSD/GNU sed differ on -i): write to a temp file, then replace.
    sed -e "s|^MASTER_ENCRYPTION_KEY=.*|MASTER_ENCRYPTION_KEY=${master_key}|" \
        -e "s|^SESSION_SECRET_KEY=.*|SESSION_SECRET_KEY=${session_key}|" \
        "$repo_root/.env" > "$repo_root/.env.tmp"
    mv "$repo_root/.env.tmp" "$repo_root/.env"

    echo "Generated MASTER_ENCRYPTION_KEY and SESSION_SECRET_KEY in .env."
    echo "Review .env now and set API_URL/FRONTEND_URL before continuing."
}

# Called after bootstrap_env, right before/after bringing the stack up. Prints
# a loud, hard-to-miss warning for the way login silently ends up unreachable:
# URLs left on localhost when the browser isn't on this same machine. Das
# erreicht "Done, open the URL" ohne eigene Fehlermeldung — das Einzige zwischen
# erreichbarer und unerreichbarer Oberfläche ist, ob jemand das hier liest.
# Siehe docs/DEPLOYMENT.md#troubleshooting.
#
# Die frühere OIDC-Prüfung ist mit AP-0 entfallen: Doctus meldet lokal an und
# legt den ersten Superuser beim Start selbst an (BOOTSTRAP_SUPERUSER*).
check_env_ready() {
    repo_root="$1"
    env_file="$repo_root/.env"
    [ -f "$env_file" ] || return 0

    frontend_url=$(grep -E "^FRONTEND_URL=" "$env_file" | cut -d= -f2-)
    api_url=$(grep -E "^API_URL=" "$env_file" | cut -d= -f2-)

    warned=0
    case "$frontend_url$api_url" in
        *localhost*|*127.0.0.1*)
            echo
            echo "!! FRONTEND_URL/API_URL still reference localhost/127.0.0.1."
            echo "!! That only works if the browser opening Doctus runs on THIS machine. If you're deploying"
            echo "!! to a server you'll reach from another machine, replace localhost in both with this"
            echo "!! host's actual reachable address (e.g. its IP or hostname), then: docker compose up -d"
            warned=1
            ;;
    esac
    [ "$warned" = 1 ] && echo
    return 0
}
