"""
parser/connectors/jira.py
==========================
Connector für Atlassian Jira (Cloud & Server).

Unterstützte Authentifizierung:
    - Basic Auth: source.username + source.token (API-Token)
    - Bearer Token: nur source.token gesetzt

Delta-Sync:
    Jira unterstützt zeitbasierte JQL-Abfragen (`updated >= '...'`). Der Connector
    übergibt source.last_synced_at direkt an Jira via JQL, statt jedes Ticket
    einzeln zu prüfen — effizienter als der Confluence/Notion-Ansatz.

Pagination:
    Jira liefert Issues in Batches (Standard: 50). Die _fetch()-Methode enthält
    exponentielles Backoff für Rate-Limiting (HTTP 429).

Inhalts-Parsing:
    Jira Cloud nutzt Atlassian Document Format (ADF) — ein JSON-Baum.
    Jira Server liefert HTML oder Plaintext. Beide werden von _extract_text()
    in lesbaren Plaintext umgewandelt.
"""

import asyncio

import httpx

from connectors.base import BaseConnector, Document
from connectors.http_retry import request_with_retry


class JiraConnector(BaseConnector):
    """
    Crawlt ein Jira-Projekt und liefert Issues als Document-Objekte.

    Jedes Issue (Titel + Beschreibung + Kommentare) wird als ein Document
    geliefert, das anschließend in der Basisklasse in Chunks aufgeteilt wird.
    """

    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._search_path: str | None = None
        self._all_keys: set[str] = set()
        self._crawl_complete = False

    async def fetch_documents(self):
        spaces = self._parse_spaces()

        auth = None
        headers: dict = {}
        if self.source.username and self.source.token:
            auth = (self.source.username, self.source.token)
        elif self.source.token:
            headers["Authorization"] = f"Bearer {self.source.token}"

        base_url = self.source.url.rstrip("/")
        jql = self._build_jql(spaces)
        self._log(f"Jira Delta-Sync JQL: {jql}")

        async with httpx.AsyncClient(verify=self._http_verify()) as client:
            start = 0
            batch_size = 50
            connection_verified = False

            while True:
                search_data = await self._search_issues(
                    client, base_url, auth, headers, jql, start, batch_size
                )
                if search_data is None:
                    if not connection_verified:
                        raise RuntimeError(
                            "Verbindung zur Jira-API fehlgeschlagen. Bitte überprüfe die Server-URL und die API-Logins."
                        )
                    break
                connection_verified = True

                total_issues = search_data.get("total", 0)
                issues = search_data.get("issues", [])
                if not issues:
                    break

                for i, issue in enumerate(issues):
                    current_count = start + i + 1
                    doc = self._build_document(issue, base_url)
                    self._update_progress(
                        current_count,
                        total_issues,
                        message=f"Indexiere Issue '{issue.get('key')}' ({current_count}/{total_issues})...",
                    )
                    if doc is not None:
                        yield doc

                start += len(issues)
                if start >= search_data.get("total", 0) or len(issues) < batch_size:
                    break

            # Der Delta-Lauf liefert nur Geänderte; ob ein Issue noch existiert, zeigt erst die Schlüsselliste.
            self._crawl_complete = await self._list_all_keys(client, base_url, auth, headers, spaces)

    async def sync(self, force_reindex: bool = False) -> None:
        await super().sync()
        if self._crawl_complete and self._all_keys:
            if self._remove_orphans(self._all_keys):
                self.has_changes = True

    async def _list_all_keys(self, client, base_url, auth, headers, spaces) -> bool:
        """Schlüssel aller Issues im Projektfilter (ohne Zeitfilter, nur das Feld ``key``).

        Gibt False zurück, wenn die Liste nicht vollständig abrufbar war; dann wird nichts aufgeräumt.
        """
        clauses = []
        if spaces and "ALL" not in spaces:
            clauses.append("(" + " OR ".join(f"project={p}" for p in spaces) + ")")
        jql = " AND ".join(clauses) if clauses else "project is not EMPTY"
        start, limit = 0, 500
        keys: set[str] = set()
        try:
            while True:
                params = {"jql": jql, "startAt": start, "maxResults": limit, "fields": "key"}
                data = await self._get_json(client, f"{base_url}{self._search_path}", auth, headers, params)
                issues = data.get("issues", [])
                keys.update(issue["key"] for issue in issues if issue.get("key"))
                start += len(issues)
                if not issues or start >= data.get("total", 0):
                    break
        except Exception as exc:  # noqa: BLE001 - nur Aufräumen entfällt, der Sync selbst ist durch
            self._log(f"[WARNUNG] Schlüsselliste nicht vollständig abrufbar ({exc}); gelöschte Issues werden diesmal nicht aufgeräumt.")
            return False
        self._all_keys = keys
        return True

    # ── JQL aufbauen ─────────────────────────────────────────────────────────

    def _build_jql(self, spaces: list[str]) -> str:
        """
        Erstellt den JQL-Query-String für den Delta-Sync.

        Kombiniert optional einen Projekt-Filter mit einem Zeit-Filter basierend
        auf source.last_synced_at — Jira übernimmt damit die Delta-Sync-Logik.
        """
        clauses: list[str] = []

        if spaces and "ALL" not in spaces:
            proj_clause = " OR ".join(f"project={p}" for p in spaces)
            clauses.append(f"({proj_clause})")

        if self.source.last_synced_at:
            formatted = self.source.last_synced_at.strftime("%Y-%m-%d %H:%M")
            clauses.append(f"updated >= '{formatted}'")
        elif not clauses:
            # Kein Zeitfilter und kein Projektfilter — auf 30 Tage begrenzen,
            # um den ersten Sync bei großen Instanzen nicht zu überlasten
            clauses.append("created >= -30d")

        return " AND ".join(clauses)

    # ── API-Aufruf ────────────────────────────────────────────────────────────

    async def _search_issues(
        self, client, base_url, auth, headers, jql, start, limit
    ) -> dict:
        """
        Führt eine Jira-Issue-Suche durch.

        Server/Data Center bietet /rest/api/2, Cloud zusätzlich /rest/api/3. Der erste Pfad, der antwortet,
        wird für den Rest des Syncs gemerkt; ein 404 wird ohne Wartezeit mit dem nächsten Pfad beantwortet.
        Anmeldefehler (401/403) und Serverfehler werden weitergereicht statt den Sync still zu beenden.
        """
        params = {
            "jql": jql,
            "startAt": start,
            "maxResults": limit,
            "fields": "summary,description,comment,status,priority,assignee",
        }
        paths = [self._search_path] if self._search_path else ["/rest/api/2/search", "/rest/api/3/search"]
        for path in paths:
            try:
                data = await self._get_json(client, f"{base_url}{path}", auth, headers, params)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in (404, 410):
                    self._log(f"Jira API-Pfad {path} nicht vorhanden. Versuche Alternative...")
                    continue
                if exc.response.status_code in (401, 403):
                    raise RuntimeError(
                        f"Anmeldung abgelehnt (HTTP {exc.response.status_code}). Prüfe Benutzername, "
                        "Passwort bzw. Personal Access Token."
                    ) from exc
                raise
            self._search_path = path
            return data
        raise RuntimeError(
            f"Keine Jira-REST-API unter {base_url} gefunden (geprüft: /rest/api/2, /rest/api/3). "
            "Prüfe die Server-URL einschließlich eines evtl. Kontextpfads."
        )

    async def _get_json(self, client, url, auth, headers, params) -> dict:
        """GET mit Backoff nur bei 429/5xx/Netzwerkfehlern; 4xx werden sofort gemeldet."""
        response = await request_with_retry(
            client, "GET", url, headers_fn=lambda: headers, auth=auth, params=params,
            timeout=30.0, log=self._log,
        )
        await asyncio.sleep(0.05)
        return response.json()

    # ── Dokument aufbauen ────────────────────────────────────────────────────

    def _build_document(self, issue: dict, base_url: str) -> Document | None:
        """Wandelt ein Jira-Issue-Objekt in ein Document um."""
        key = issue.get("key", "UNKNOWN")
        fields = issue.get("fields", {})
        summary = fields.get("summary", "")

        description_text = self._extract_text(fields.get("description"))
        comments_text = self._extract_comments(fields.get("comment", {}).get("comments", []))

        content = (
            f"Jira Issue: {key}\n"
            f"Summary: {summary}\n"
            f"Description: {description_text}\n"
            f"{comments_text}"
        )

        return Document(
            title=f"{key}: {summary}",
            content=content,
            url=f"{base_url}/browse/{key}",
            source_type="Jira",
            # Jira-Issues verwenden den Issue-Key als storage_key, nicht den Titel —
            # der Key ist stabiler und garantiert eindeutig pro Projekt
            storage_key=key,
            extra_meta={"issue_key": key},
        )

    def _extract_text(self, node) -> str:
        """
        Wandelt Atlassian Document Format (ADF) rekursiv in Plaintext um.
        ADF ist ein JSON-Baum den Jira Cloud in Beschreibungen und Kommentaren nutzt.
        Jira Server liefert manchmal Strings — diese werden direkt zurückgegeben.
        """
        if not node:
            return ""
        if isinstance(node, str):
            return node
        if node.get("type") == "text":
            return node.get("text", "")
        text = ""
        for child in node.get("content", []):
            text += self._extract_text(child)
        if node.get("type") in ("paragraph", "heading"):
            text += "\n"
        return text

    def _extract_comments(self, comments: list) -> str:
        """Wandelt eine Liste von Jira-Kommentaren in lesbaren Text um."""
        parts: list[str] = []
        for comment in comments:
            author = comment.get("author", {}).get("displayName", "User")
            body = self._extract_text(comment.get("body", ""))
            parts.append(f"Comment by {author}: {body}")
        return "\n".join(parts)
