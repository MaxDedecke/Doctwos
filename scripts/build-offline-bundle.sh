#!/bin/sh
# Run by the consultant on a machine with internet/registry access. Builds and
# tags the 3 custom images, pulls the 3 pinned base images, pulls a clean copy
# of the embedding model plus an optional explicitly enabled LLM, and assembles everything into a
# self-contained bundle dir for install-offline.sh to consume on an air-gapped
# customer machine. See docs/DEPLOYMENT.md, "Air-Gapped / Offline Installation".
set -e

repo_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$repo_root"

CODENA_VERSION="${1:-$(git rev-parse --short HEAD 2>/dev/null || echo dev)}"
remote_inference=0
[ "${2:-}" != "--remote-inference" ] || remote_inference=1
export CODENA_VERSION

# Optional local LLM to bake into this bundle. Disabled for the CPU-only pilot
# until first delivery; set an explicit validated tag for a suitably sized host.
LLM_MODEL="${LLM_MODEL:-disabled}"

# Baked into the backend image so GET /version reports what's actually
# running, independent of the diagnostics bundle (docs/DEPLOYMENT.md).
GIT_SHA=$(git rev-parse HEAD 2>/dev/null || echo unknown)
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
export GIT_SHA BUILD_TIME

bundle_dir="$repo_root/dist/codena-offline-bundle-${CODENA_VERSION}"
echo "Building offline bundle ${CODENA_VERSION} into ${bundle_dir}"
case "$bundle_dir" in "$repo_root"/dist/codena-offline-bundle-*) ;; *) echo "Invalid bundle path" >&2; exit 1 ;; esac
case "$CODENA_VERSION" in *[!a-zA-Z0-9._-]*|'') echo "Invalid version" >&2; exit 1 ;; esac
rm -rf -- "$bundle_dir"
mkdir -p "$bundle_dir"

export DOCKER_DEFAULT_PLATFORM="${DOCKER_DEFAULT_PLATFORM:-linux/amd64}"

echo "==> Building codena-backend-api, codena-parser-worker, codena-frontend:${CODENA_VERSION} (platform: ${DOCKER_DEFAULT_PLATFORM})"
docker compose build backend-api
docker compose build parser-worker
docker compose build frontend

echo "==> Pulling pinned base images (db, redis, ollama)"
docker compose pull db redis
models_dir=$(mktemp -d)
if [ "$remote_inference" = 0 ]; then
docker compose pull ollama

echo "==> Pulling a clean set of Ollama models — not this host's live ./data/ollama, which may carry stale models"
docker rm -f codena-bundle-ollama >/dev/null 2>&1 || true
ollama_image=$(docker compose config --images ollama)
docker run -d --name codena-bundle-ollama -v "$models_dir:/root/.ollama" "$ollama_image" >/dev/null
trap 'docker rm -f codena-bundle-ollama >/dev/null 2>&1 || true' EXIT
# Wait for the server inside the container to be ready before pulling.
for i in $(seq 1 30); do
    docker exec codena-bundle-ollama ollama list >/dev/null 2>&1 && break
    sleep 1
done
if [ -n "$LLM_MODEL" ] && [ "$LLM_MODEL" != "disabled" ]; then
    docker exec codena-bundle-ollama ollama pull "$LLM_MODEL"
fi
docker exec codena-bundle-ollama ollama pull bge-m3

echo "==> Recording model provenance (see docs/OSS-CLEARING.md for license text)"
{
    echo "Codena offline bundle ${CODENA_VERSION} — model provenance manifest"
    echo "Built: ${BUILD_TIME}"
    echo
    echo "Pulled models (name, digest, size — from 'ollama list' on the build host):"
    docker exec codena-bundle-ollama ollama list
    echo
    echo "LLM_MODEL tag baked into this bundle: ${LLM_MODEL}"
    if [ "$LLM_MODEL" = "disabled" ]; then
        echo "  - No local chat/compliance LLM included (CPU-only pilot mode)."
    else
        echo "  - Validate license and quantization provenance for the configured tag before delivery."
    fi
    echo "Embedding model: bge-m3 (MIT, BAAI), pulled from Ollama's official library, not a"
    echo "  third-party requantization."
} > "$bundle_dir/MODEL_MANIFEST.txt"

docker rm -f codena-bundle-ollama >/dev/null 2>&1
trap - EXIT

else
    echo "Remote-only bundle: no Ollama image or model downloads."
    printf 'Remote inference only; no model weights included.\nBuilt: %s\n' "$BUILD_TIME" > "$bundle_dir/MODEL_MANIFEST.txt"
    ollama_image=
fi

# docker load does not reliably preserve registry digest references on a fresh daemon.
# Export named local aliases; record their pinned upstream provenance alongside the bundle.
db_image=$(docker compose config --images db)
redis_image=$(docker compose config --images redis)
docker tag "$db_image" "codena-db:${CODENA_VERSION}"
docker tag "$redis_image" "codena-redis:${CODENA_VERSION}"
{
    printf 'codena-db:%s <= %s\n' "$CODENA_VERSION" "$db_image"
    printf 'codena-redis:%s <= %s\n' "$CODENA_VERSION" "$redis_image"
    if [ -n "$ollama_image" ]; then
        printf 'codena-ollama:%s <= %s\n' "$CODENA_VERSION" "$ollama_image"
    fi
} > "$bundle_dir/IMAGE_MANIFEST.txt"
if [ -n "$ollama_image" ]; then
    docker tag "$ollama_image" "codena-ollama:${CODENA_VERSION}"
    ollama_image="codena-ollama:${CODENA_VERSION}"
fi

echo "==> Saving images (this is the slow, large step — dominated by the Ollama base image)"
set -- \
    "codena-backend-api:${CODENA_VERSION}" \
    "codena-parser-worker:${CODENA_VERSION}" \
    "codena-frontend:${CODENA_VERSION}" \
    "codena-db:${CODENA_VERSION}" \
    "codena-redis:${CODENA_VERSION}" \
    -o "$bundle_dir/images.tar"
[ -z "$ollama_image" ] || set -- "$@" "$ollama_image"
docker save "$@"
gzip "$bundle_dir/images.tar"

echo "==> Packing Ollama models"
tar czf "$bundle_dir/ollama-models.tar.gz" -C "$models_dir" .
rm -rf "$models_dir"

echo "==> Assembling bundle"
cp docker-compose.offline.yml "$bundle_dir/"
cp docker-compose.remote-inference.yml "$bundle_dir/"
cp docker-compose.gpu.yml "$bundle_dir/"
cp scripts/install-offline.sh "$bundle_dir/"
cp scripts/test-remote-inference.sh "$bundle_dir/"
cp scripts/check_confluence.py "$bundle_dir/"
cp scripts/check_remote_inference.py "$bundle_dir/"
cp scripts/generate_diagnostics.py "$bundle_dir/"
cp docs/PILOT_DEPLOYMENT.md "$bundle_dir/"
cp docs/CI_INTEGRATION.md "$bundle_dir/"
mkdir -p "$bundle_dir/ci-runner/scripts/lib" "$bundle_dir/ci-runner/packages/codena-models/codena_models" "$bundle_dir/ci-runner/examples"
cp scripts/publish_maven_ci.py "$bundle_dir/ci-runner/scripts/"
cp scripts/lib/maven_ci_artifacts.py "$bundle_dir/ci-runner/scripts/lib/"
cp packages/codena-models/codena_models/__init__.py packages/codena-models/codena_models/ci_artifacts.py "$bundle_dir/ci-runner/packages/codena-models/codena_models/"
cp docs/examples/maven-ci.github.yml docs/examples/maven-ci.gitlab.yml "$bundle_dir/ci-runner/examples/"

printf 'Version: %s\nCommit: %s\nBuilt: %s\n' "$CODENA_VERSION" "$GIT_SHA" "$BUILD_TIME" > "$bundle_dir/BUILD_MANIFEST.txt"
if ! git diff --quiet; then echo "Includes uncommitted workspace changes" >> "$bundle_dir/BUILD_MANIFEST.txt"; fi
cp -r config "$bundle_dir/"
mkdir -p "$bundle_dir/scripts/lib"
cp scripts/lib/env-bootstrap.sh "$bundle_dir/scripts/lib/"
[ -f docs/DEPLOYMENT.md ] && cp docs/DEPLOYMENT.md "$bundle_dir/"
[ -f docs/REMOTE_INFERENCE.md ] && cp docs/REMOTE_INFERENCE.md "$bundle_dir/"
[ -f docs/OSS-CLEARING.md ] && cp docs/OSS-CLEARING.md "$bundle_dir/"
# GPL-Pflichten (Lizenztext, Version, Quellcode-Angebot) fuer die Debian-Pakete in den Images.
scripts/gen-third-party-notices.sh "$bundle_dir/THIRD-PARTY-NOTICES.txt" \
    "codena-backend-api:${CODENA_VERSION}" "codena-parser-worker:${CODENA_VERSION}"

# Pin CODENA_VERSION and LLM_MODEL in the shipped .env.example to whatever was
# actually built/pulled, so the customer's generated .env can't drift from the
# images/models in this bundle (same reasoning for both — see the comment atop
# this file for CODENA_VERSION, and above for LLM_MODEL).
sed -e "s|^CODENA_VERSION=.*|CODENA_VERSION=${CODENA_VERSION}|" \
    -e "s|^LLM_MODEL=.*|LLM_MODEL=${LLM_MODEL}|" \
    .env.example > "$bundle_dir/.env.example"

(cd "$bundle_dir" && find . -type f ! -name SHA256SUMS | sort | xargs sha256sum > SHA256SUMS)

echo
echo "Bundle ready: $bundle_dir"
du -sh "$bundle_dir"
echo "Archive it yourself for transfer (e.g. tar czf or zip -r) and ship via your usual secure channel — not scripted here, it's a per-engagement decision."
