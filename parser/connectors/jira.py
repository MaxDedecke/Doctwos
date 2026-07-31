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
from datetime import datetime, timezone

import httpx

from connectors.base import BaseConnector, Document


class JiraConnector(BaseConnector):
    """
    Crawlt ein Jira-Projekt und liefert Issues als Document-Objekte.

    Jedes Issue (Titel + Beschreibung + Kommentare) wird als ein Document
    geliefert, das anschließend in der Basisklasse in Chunks aufgeteilt wird.
    """

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

        async with httpx.AsyncClient() as client:
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
                    self._update_progress(current_count, total_issues, message=f"Indexiere Issue '{issue.get('key')}' ({current_count}/{total_issues})...")
                    if doc is not None:
                        yield doc

                start += len(issues)
                if start >= search_data.get("total", 0) or len(issues) < batch_size:
                    break

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
        self, client, base_url, auth, headers, jql, start, limit, max_retries: int = 5
    ) -> dict | None:
        """
        Führt eine Jira-Issue-Suche durch.
        Versucht beide API-Versionen (/rest/api/3 und /rest/api/2),
        da Jira Cloud v3 und Jira Server v2 nutzt.
        """
        params = {
            "jql": jql,
            "startAt": start,
            "maxResults": limit,
            "fields": "summary,description,comment,status,priority,assignee",
        }

        for path in ["/rest/api/3/search", "/rest/api/2/search"]:
            try:
                return await self._fetch_with_retry(
                    client, f"{base_url}{path}", auth, headers, params, max_retries
                )
            except Exception as e:
                self._log(f"Jira API-Pfad {path} fehlgeschlagen: {e}. Versuche Alternative...")

        self._log("Keine erreichbare Jira-API gefunden.")
        return None

    async def _fetch_with_retry(
        self, client, url, auth, headers, params, max_retries: int = 5
    ) -> dict:
        """GET-Request mit exponentiellem Backoff bei Rate-Limiting (HTTP 429)."""
        backoff = 1.0
        for attempt in range(max_retries):
            try:
                response = await client.get(
                    url, auth=auth, headers=headers, params=params, timeout=30.0
                )
                if response.status_code == 429:
                    wait = float(response.headers.get("Retry-After", backoff))
                    self._log(f"Rate Limit (429). Warte {wait}s...")
                    await asyncio.sleep(wait)
                    backoff *= 2.0
                    continue
                response.raise_for_status()
                await asyncio.sleep(0.2)
                return response.json()
            except Exception as e:
                if attempt < max_retries - 1:
                    self._log(f"Anfrage fehlgeschlagen: {e}. Retry in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                else:
                    raise

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
