#!/bin/sh
# Run the probe inside the loaded backend image; no host Python or internet required.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$script_dir/check_remote_inference.py" ]; then probe_dir="$script_dir"; else exit 1; fi
docker compose run --rm --no-deps --pull never --entrypoint python \
    -v "$probe_dir:/doctus-probe:ro" backend-api /doctus-probe/check_remote_inference.py "$@"
