#!/bin/sh
# Run on the customer's air-gapped machine, inside the extracted bundle
# produced by build-offline-bundle.sh. No internet access required or used.
set -e

bundle_dir=$(cd "$(dirname "$0")" && pwd)
cd "$bundle_dir"

remote_inference=0
for arg in "$@"; do
    case "$arg" in
        --remote-inference|--remote-ai)
            remote_inference=1
            ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required but not found." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is required but not found." >&2
    exit 1
fi

echo "==> Verifying bundle integrity"
if ! sha256sum -c SHA256SUMS --quiet; then
    echo "Checksum verification failed — the bundle may be corrupted or incomplete from the transfer. Aborting." >&2
    exit 1
fi

echo "==> Loading images (no registry access needed)"
gunzip -c images.tar.gz | docker load

echo "==> Restoring Ollama models"
mkdir -p data/ollama
tar xzf ollama-models.tar.gz -C data/ollama

. scripts/lib/env-bootstrap.sh
bundle_version=$(sed -n 's/^DOCTUS_VERSION=//p' .env.example | head -n 1)
[ -n "$bundle_version" ] || { echo "Missing bundle version" >&2; exit 1; }
bootstrap_env "$bundle_dir" "$bundle_version"
grep -q '^DOCTUS_VERSION=' .env || echo 'DOCTUS_VERSION=' >> .env
sed "s/^DOCTUS_VERSION=.*/DOCTUS_VERSION=$bundle_version/" .env > .env.tmp
mv .env.tmp .env
sync_compose_file "$bundle_dir" "docker-compose.offline.yml" "$remote_inference"

if [ "$remote_inference" = "1" ]; then
    echo
    echo "NOTE: Remote inference active (docker-compose.remote-inference.yml)."
    echo "Verify independent LLM_BASE_URL/LLM_PROVIDER and EMBEDDING_BASE_URL/EMBEDDING_PROVIDER/model settings in .env."
    echo "You can test connectivity with: ./test-remote-inference.sh"
    echo "Local Ollama requires its image and model weights; these are not included in remote-only bundles."
    echo
fi

if grep -q '^POSTGRES_PASSWORD=change-me$' .env; then
    echo "Set POSTGRES_PASSWORD in .env before starting the customer deployment." >&2
    exit 1
fi
echo "==> Starting services (no build — images come from the loaded bundle)"
# No -f here: sync_compose_file above set COMPOSE_FILE in .env to
# docker-compose.offline.yml, plus docker-compose.gpu.yml when a GPU was
# detected — docker compose picks both up from .env in this cwd.
startup_since=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
docker compose up -d --pull never --wait --wait-timeout 180
show_bootstrap_credentials "$startup_since"

check_env_ready "$bundle_dir"

. ./.env
echo
echo "Done. Open ${FRONTEND_URL:-http://localhost:3000} to sign in."
