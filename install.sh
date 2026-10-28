#!/bin/sh
# Online install: this machine has internet access and builds the images itself.
# For air-gapped customers, see scripts/build-offline-bundle.sh + install-offline.sh
# and the "Air-Gapped / Offline Installation" section in docs/DEPLOYMENT.md.
set -e

repo_root=$(cd "$(dirname "$0")" && pwd)

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but not found. Install Docker first: https://docs.docker.com/engine/install/" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required but not found." >&2
    exit 1
fi

. "$repo_root/scripts/lib/env-bootstrap.sh"
bootstrap_env "$repo_root"
sync_compose_file "$repo_root" "docker-compose.yml"

cd "$repo_root"
echo "Building images..."
# parser-worker and parser-beat intentionally share the same image/tag. Docker
# 29 can race when Compose builds both services in parallel and then fail the
# second export with "image ... already exists". Build each distinct image once.
docker compose build backend-api
docker compose build parser-worker
docker compose build frontend
# The deployer (local LLM containers from Settings > AI) mounts the Docker socket, i.e. it has
# root on this host. It only starts when switched on via COMPOSE_PROFILES=deployer in .env.
compose_profiles=$(grep -E "^COMPOSE_PROFILES=" "$repo_root/.env" | cut -d= -f2-)
compose_profiles=${COMPOSE_PROFILES:-$compose_profiles}
case ",$compose_profiles," in
    *,deployer,*) deployer_enabled=1 ;;
    *) deployer_enabled=0 ;;
esac
if [ "$deployer_enabled" = 1 ]; then
    docker compose build deployer
fi

echo "Starting services (Alembic migrations run automatically on backend startup)..."
startup_since=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
docker compose up -d
show_bootstrap_credentials "$startup_since"

# Der Standard-Stack startet ohne LLM-Container. Ein lokales Deployment (Ollama, vLLM oder
# llama.cpp) und die Modelle legt man nach der ersten Anmeldung unter
# Einstellungen > KI an (LLM-Profile und Embedding-Profile).
# Wer den alten festen Ollama-Dienst weiter nutzen will: LEGACY_OLLAMA_SERVICE=true in .env,
# `docker compose --profile local-ollama up -d` und die Modelle selbst ziehen, z. B.
#   docker exec doctus-ollama ollama pull bge-m3
if docker ps --format '{{.Names}}' | grep -qx doctus-ollama; then
    llm_model=$(grep -E "^LLM_MODEL=" "$repo_root/.env" | cut -d= -f2-)
    if [ -n "$llm_model" ] && [ "$llm_model" != "disabled" ]; then
        echo "Pulling optional Ollama LLM (${llm_model})..."
        docker exec doctus-ollama ollama pull "$llm_model"
    fi
    echo "Pulling Ollama embedding model (bge-m3)..."
    docker exec doctus-ollama ollama pull bge-m3
elif [ "$deployer_enabled" = 1 ]; then
    echo "No LLM container in the default stack — create a local deployment under Settings > AI."
else
    echo "No LLM container in the default stack. Either add a remote or cloud profile under Settings > AI,"
    echo "or enable local deployments with COMPOSE_PROFILES=deployer in .env and run 'docker compose up -d'"
    echo "(the deployer gets root on this host via the Docker socket; see docs/DEPLOYMENT.md)."
fi

check_env_ready "$repo_root"

. "$repo_root/.env"
echo
echo "Done. Open ${FRONTEND_URL:-http://localhost:3000} to sign in."
