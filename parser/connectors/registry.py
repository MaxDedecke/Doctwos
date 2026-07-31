"""
parser/connectors/registry.py
==============================
Zentrale Registry aller verfügbaren Wissensquellen-Connectoren.

Neuen Connector in 2 Schritten hinzufügen:
    1. Connector-Klasse erstellen (Unterklasse von BaseConnector)
    2. Hier im REGISTRY-Dict eintragen — fertig

Der source_type-String muss exakt dem Wert entsprechen, der in der
KnowledgeSource-DB-Spalte `type` gespeichert wird und den das Frontend
beim Anlegen einer neuen Wissensquelle übergibt.
"""

from connectors.base import BaseConnector
from connectors.confluence import ConfluenceConnector
from connectors.folder import FolderConnector
from connectors.jira import JiraConnector
from connectors.webdav import WebdavConnector
from connectors.git import GitConnector

# Mapping: source_type (wie in der DB gespeichert) → Connector-Klasse
REGISTRY: dict[str, type[BaseConnector]] = {
    "Confluence": ConfluenceConnector,
    "Jira": JiraConnector,
    "FolderWatch": FolderConnector,
    "WebDAV": WebdavConnector,
    "Git": GitConnector,
}


def get_connector(source_type: str) -> type[BaseConnector]:
    """
    Gibt die Connector-Klasse für einen source_type zurück.

    Args:
        source_type: Wert aus KnowledgeSource.type (z. B. "Confluence")

    Raises:
        ValueError: Wenn kein Connector für diesen source_type registriert ist
    """
    # Case-insensitiver Lookup
    connector_cls = None
    for k, v in REGISTRY.items():
        if k.lower() == source_type.lower():
            connector_cls = v
            break
    
    if connector_cls is None:
        registered = ", ".join(set(k.capitalize() for k in REGISTRY.keys()))
        raise ValueError(
            f"Kein Connector für source_type '{source_type}' registriert. "
            f"Bekannte Typen: {registered}"
        )
    return connector_cls
