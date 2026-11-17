"""Größenbegrenzung der Logdateien unter /var/log/doctus (``data/logs`` auf dem Host).

Backend, Worker und Beat schreiben dort zusätzlich zu stdout, damit das Diagnosepaket ohne Docker-Socket an die Logs
kommt. Docker begrenzt nur seine eigenen Logs; diese Dateien wuchsen bisher unbegrenzt. Mehrere Prozesse schreiben im
Anhängemodus in dieselbe Datei, deshalb wird wie bei ``logrotate copytruncate`` kopiert und dann auf null gekürzt
statt umbenannt: Die Schreiber behalten ihren Dateideskriptor und schreiben am neuen Ende weiter. Zwischen Kopie und
Kürzung geschriebene Zeilen können verloren gehen; das ist der übliche Preis von copytruncate.
"""

from __future__ import annotations

import logging
import os
import shutil

logger = logging.getLogger(__name__)

LOGS_ROOT = "/var/log/doctus"


def trim_logs(root: str = LOGS_ROOT) -> list[str]:
    max_bytes = max(1, int(os.getenv("LOG_FILE_MAX_MB", "100"))) * 1024 * 1024
    keep = max(1, int(os.getenv("LOG_FILE_KEEP", "3")))
    trimmed = []
    if not os.path.isdir(root):
        return trimmed
    for service in sorted(os.listdir(root)):
        folder = os.path.join(root, service)
        if not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            path = os.path.join(folder, name)
            if not name.endswith(".log") or not os.path.isfile(path):
                continue
            try:
                if os.path.getsize(path) < max_bytes:
                    continue
                for index in range(keep - 1, 0, -1):
                    older = f"{path}.{index}"
                    if os.path.exists(older):
                        os.replace(older, f"{path}.{index + 1}")
                shutil.copyfile(path, f"{path}.1")
                with open(path, "r+b") as handle:
                    handle.truncate(0)
                trimmed.append(path)
            except OSError as exc:
                logger.warning("Logdatei %s nicht gekürzt: %s", path, exc)
    if trimmed:
        logger.info("Logdateien gekürzt: %s", ", ".join(trimmed))
    return trimmed
