#!/usr/bin/env bash
# SBOM- und Schwachstellenscan der gebauten Images (OSS-CLEARING.md,
# "Nicht automatisch geprueft"). Nutzt syft/grype als Container, nichts
# muss installiert werden; die Images muessen lokal vorhanden sein.
#
# Aufruf: sbom-scan.sh <ausgabeverzeichnis> [<image> ...]
# Ohne Image-Angabe: die drei Doctus-Images, der Deployer und DB/Valkey aus
# docker-compose.yml. Ergebnis je Image: <name>.cdx.json (CycloneDX-SBOM,
# inkl. Lizenzen) und <name>.grype.json (Schwachstellen). Das Skript bricht
# nicht bei Funden ab, es liefert Daten fuer die manuelle Bewertung.
set -euo pipefail

out="$1"; shift
mkdir -p "$out"
out=$(cd "$out" && pwd)

if [ "$#" -eq 0 ]; then
    set -- "doctus-backend-api:${DOCTUS_VERSION:-latest}" \
           "doctus-parser-worker:${DOCTUS_VERSION:-latest}" \
           "doctus-frontend:${DOCTUS_VERSION:-latest}" \
           "doctus-deployer:${DOCTUS_VERSION:-latest}" \
           "$(docker compose config --images db)" \
           "$(docker compose config --images redis)"
fi

for image in "$@"; do
    name=$(echo "$image" | sed 's|@sha256:.*||' | tr '/:' '__')
    echo "==> $image"
    docker run --rm -v /var/run/docker.sock:/var/run/docker.sock anchore/syft:latest \
        -q "$image" -o cyclonedx-json > "$out/$name.cdx.json"
    docker run --rm -v "$out:/s:ro" anchore/grype:latest \
        -q "sbom:/s/$name.cdx.json" -o json > "$out/$name.grype.json"
done
echo "Fertig: $out"
