"""
parser/connectors/tls.py
========================
TLS-Prüfung für HTTP-Connectoren (Confluence, Jira, WebDAV).

Kundennetze nutzen oft interne CAs oder selbst signierte Zertifikate; httpx kennt im Container
nur das mitgelieferte Mozilla-Bundle. Reihenfolge, von konkret nach allgemein:

1. ``spaces.ca_bundle``     — Pfad zu einem CA-Bundle nur für diese Quelle
2. ``spaces.verify_ssl``    — ``false`` schaltet die Prüfung für diese Quelle ausdrücklich ab (nur Test)
3. ``CUSTOM_CA_BUNDLE``     — Umgebungsvariable des Workers: ein CA-Bundle für alle Quellen
4. sonst                    — normale Prüfung (Sicherheit per Default)
"""

import os


def resolve_verify(spaces_config: dict | None):
    """Wert für ``httpx.AsyncClient(verify=...)`` aus der Quell-Konfiguration."""
    config = spaces_config or {}
    ca_bundle = config.get("ca_bundle")
    if ca_bundle:
        return ca_bundle
    if config.get("verify_ssl") is False:
        return False
    env_bundle = os.getenv("CUSTOM_CA_BUNDLE")
    if env_bundle and os.path.isfile(env_bundle):
        return env_bundle
    return True
