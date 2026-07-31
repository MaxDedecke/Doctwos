"""
Liveness check for the celery beat scheduler container.

Beat doesn't respond to celery's broadcast `inspect ping` (that's only
answered by workers), so the only way to tell "beat process died" from
"container up but wedged" is to confirm the beat process itself is still
running. Exits 0 if found, 1 otherwise — used as docker-compose's
healthcheck test for the parser-beat service.
"""
import os
import sys

for pid in os.listdir("/proc"):
    if not pid.isdigit():
        continue
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            cmdline = f.read().decode(errors="ignore")
    except OSError:
        continue
    if "celery" in cmdline and "beat" in cmdline:
        sys.exit(0)

sys.exit(1)
