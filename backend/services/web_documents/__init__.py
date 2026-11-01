"""Webansicht: Einträge fremder Systeme einheitlich darstellen (siehe docs/WEB_DOCUMENTS.md)."""

from __future__ import annotations

from services.web_documents.base import WebAdapter
from services.web_documents.confluence import ConfluenceAdapter
from services.web_documents.jira import JiraAdapter

# Quellen, die Dateien liefern und im Dokument- oder Code-Viewer landen. Alles andere ist ein Web-System;
# Gegenstück im Frontend: lib/webSources.ts.
FILE_SOURCE_TYPES = {"git", "local", "folderwatch", "webdav"}

# Ein neues System braucht hier einen Eintrag nur für die volle Darstellung; ohne ihn zeigt der Grundfall
# den indexierten Text.
ADAPTERS: dict[str, WebAdapter] = {"jira": JiraAdapter(), "confluence": ConfluenceAdapter()}
_FALLBACK = WebAdapter()


def is_web_source(source_type: str | None) -> bool:
    return bool(source_type) and source_type.lower() not in FILE_SOURCE_TYPES


def adapter_for(source_type: str | None) -> WebAdapter:
    return ADAPTERS.get((source_type or "").lower(), _FALLBACK)
