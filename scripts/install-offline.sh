#!/bin/sh
# Run on the customer's air-gapped machine, inside the extracted bundle
# produced by build-offline-bundle.sh. No internet access required or used.
set -e

bundle_dir=$(cd "$(dirname "$0")" && pwd)
cd "$bundle_dir"

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
bootstrap_env "$bundle_dir"

echo "==> Starting services (no build — images come from the loaded bundle)"
docker compose -f docker-compose.offline.yml up -d

check_env_ready "$bundle_dir"

. ./.env
echo
echo "Done. Open ${FRONTEND_URL:-http://localhost:3000} to sign in."
