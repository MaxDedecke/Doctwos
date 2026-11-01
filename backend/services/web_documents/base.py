"""Das gemeinsame Format der Webansicht und der Vertrag für Adapter (siehe docs/WEB_DOCUMENTS.md).

Ein Adapter liefert nur Daten; Darstellung, Link-Auflösung, Bilder und der Rückfall auf den Index sind
für alle Systeme gleich. ``body_html`` und ``Comment.body_html`` gelten als nicht vertrauenswürdig: Das
Frontend bereinigt sie und zeigt sie im abgeschotteten iframe.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class Fact:
    """Eine Angabe im Kopf. ``key`` wählt die Übersetzung, ``label`` greift bei unbekannten Schlüsseln."""

    key: str
    label: str
    values: list[str]
    kind: str = "text"  # text | status | date


@dataclass
class Crumb:
    title: str
    url: str | None = None
    source_id: int | None = None


@dataclass
class Comment:
    author: str
    created: str | None
    body_html: str


@dataclass
class Attachment:
    name: str
    url: str
    size: int | None = None
    mime: str | None = None


@dataclass
class Related:
    relation: str
    title: str
    url: str
    identifier: str | None = None
    status: str | None = None
    source_id: int | None = None


@dataclass
class WebDocument:
    title: str
    url: str | None
    kind: str = "document"
    identifier: str | None = None
    facts: list[Fact] = field(default_factory=list)
    breadcrumbs: list[Crumb] = field(default_factory=list)
    body_html: str = ""
    comments: list[Comment] = field(default_factory=list)
    comments_total: int | None = None
    attachments: list[Attachment] = field(default_factory=list)
    related: list[Related] = field(default_factory=list)
    # Nur feste Regeln des Adapters, nie Inhalte der Quelle. Farben über die Variablen --wd-* des Frontends.
    extra_css: str = ""
    origin: str = "live"  # live | index
    notice: str | None = None  # unreachable | index_only
    synced_at: str | None = None


class NotRenderable(Exception):
    """Dieser Eintrag lässt sich nicht live darstellen (z. B. ein Anhang); der Index zeigt seinen Text."""


class SourceUnavailable(Exception):
    """Das Quellsystem hat nicht wie erwartet geantwortet."""


@dataclass
class FetchContext:
    """Der Zugang zur Instanz einer Quelle; Adapter sehen weder Datenbank noch Zugangsdaten-Herkunft."""

    client: httpx.Client
    base_url: str
    auth: tuple[str, str] | None
    headers: dict

    def get_json(self, path: str, params: dict | None = None) -> dict:
        response = self.client.get(
            f"{self.base_url}{path}", auth=self.auth, headers=self.headers, params=params
        )
        if response.status_code != 200:
            raise SourceUnavailable(f"HTTP {response.status_code} für {path}")
        return response.json()


class WebAdapter:
    """Grundfall für jedes System: ohne eigenen Adapter zeigt die Webansicht den indexierten Text."""

    def index_key(self, url: str) -> str | None:
        """Index-Schlüssel (``DocumentChunk.file_path``) zu einer URL, ohne Netzzugriff.

        Mit führendem ``*`` zählt nur das Ende des Schlüssels. ``None``: Die URL verrät ihn nicht.
        """
        return None

    def fetch(self, ctx: FetchContext, key: str, meta: dict) -> WebDocument:
        raise NotRenderable(key)
