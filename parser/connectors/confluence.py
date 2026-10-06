"""
parser/connectors/confluence.py
================================
Connector für Atlassian Confluence (Cloud & Server).

Unterstützte Authentifizierung:
    - Basic Auth: source.username + source.token (API-Token)
    - Bearer Token: nur source.token gesetzt

Delta-Sync:
    Jede Seite und jeder Anhang wird mit source.last_synced_at verglichen
    (page/attachment version.when). Unveränderte Objekte werden übersprungen.

Attachments:
    Für jede Seite werden Anhänge über /child/attachment geladen.
    Unterstützte Typen: PDF (pypdf), DOCX (python-docx), Plaintext/Code.
    Binärdateien ohne Textinhalt (Bilder, ZIP, ...) werden übersprungen.
    Maximale Dateigröße: 20 MB (ATTACHMENT_MAX_BYTES).

Pagination:
    Confluence liefert Seiten in Batches (Standard: 25). Die _fetch()-Methode
    enthält exponentielles Backoff für Rate-Limiting (HTTP 429).
"""

import io
import asyncio
from datetime import datetime
from html.parser import HTMLParser

import httpx

from connectors.base import BaseConnector, Document
from connectors.http_retry import request_with_retry
from models.database import DocumentChunk

ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024  # 20 MB

_SUPPORTED_MIME_PREFIXES = ("text/",)
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_SUPPORTED_MIME_EXACT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    _XLSX_MIME,
    _PPTX_MIME,
}


_HEADINGS = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})


class _ConfluenceHTMLParser(HTMLParser):
    """Converts Confluence rendered HTML (body.view.value) to clean plaintext.

    Improvements over a raw regex strip:
    - HTML entities decoded correctly (&amp; → &, &nbsp; → space, etc.)
    - Block-level tags produce newlines instead of spaces, preserving paragraphs
    - Table cells separated with ' | ' so rows stay readable
    - <script>, <style>, and Confluence param tags excluded from output
    - <pre>/<code> content kept verbatim (no whitespace collapsing inside)

    O-082: neben dem reinen Text führt der Parser parallel `_line_sections`
    mit — pro Ausgabezeile die zuletzt gesehene h1-h6-Überschrift. Anders als
    bei COBOL (Section-Grenze liegt schon aus der Strukturanalyse vor) muss
    diese Zuordnung hier während des Parsens mitlaufen: eine Überschrift ist
    erst nach ihrem </h*>-Endtag vollständig bekannt (Inline-Markup wie
    <strong> im Heading-Text), wird aber rückwirkend auch der eigenen Zeile
    zugewiesen (`_heading_line_index`). get_lines_with_sections() wendet
    dieselbe Trim-/Blankzeilen-Kollaps-Logik wie früher get_text() an, aber
    auf Text- und Section-Liste zugleich, damit beide im Index synchron
    bleiben.
    """

    _BLOCK = frozenset(
        {
            "p",
            "div",
            "li",
            "tr",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "blockquote",
            "ul",
            "ol",
            "table",
            "thead",
            "tbody",
            "pre",
        }
    )
    _SKIP = frozenset({"script", "style", "ac:parameter"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._buf: list[str] = []
        self._pre_depth = 0
        self._skip_depth = 0
        self._current_section: str | None = None
        self._line_sections: list[str | None] = [None]
        self._heading_depth = 0
        self._heading_buf: list[str] = []
        self._heading_line_index: int | None = None

    def _end_line(self) -> None:
        """Schließt die aktuelle Zeile ab und merkt die für die neue Zeile
        gültige Section vor."""
        self._buf.append("\n")
        self._line_sections.append(self._current_section)

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADINGS:
            self._end_line()
            self._heading_depth += 1
            self._heading_buf = []
            self._heading_line_index = len(self._line_sections) - 1
        elif tag in ("pre", "code"):
            self._pre_depth += 1
            self._end_line()
        elif tag == "br":
            self._end_line()
        elif tag in ("td", "th"):
            self._buf.append(" | ")
        elif tag in self._BLOCK:
            self._end_line()

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _HEADINGS:
            self._heading_depth = max(0, self._heading_depth - 1)
            heading_text = " ".join("".join(self._heading_buf).split())
            if heading_text:
                self._current_section = heading_text
                if self._heading_line_index is not None:
                    self._line_sections[self._heading_line_index] = heading_text
            self._heading_line_index = None
            self._end_line()
        elif tag in ("pre", "code"):
            self._pre_depth = max(0, self._pre_depth - 1)
            self._end_line()
        elif tag in self._BLOCK:
            self._end_line()

    def handle_data(self, data):
        if self._skip_depth:
            return
        self._buf.append(data)
        if self._heading_depth:
            self._heading_buf.append(data)

    def _normalized_lines(self) -> tuple[list[str], list[str | None]]:
        raw_lines = "".join(self._buf).split("\n")
        sections = self._line_sections
        if len(sections) < len(raw_lines):
            # Sollte nicht vorkommen (jede "\n" in _buf hat ihren _end_line()
            # Eintrag) -- defensiv statt IndexError, falls doch mal ein Tag
            # ohne Section-Nachführung Zeilen erzeugt.
            sections = sections + [sections[-1] if sections else None] * (
                len(raw_lines) - len(sections)
            )
        lines = [" ".join(line.split()) for line in raw_lines]
        sections = sections[: len(lines)]

        start = 0
        while start < len(lines) and lines[start] == "":
            start += 1
        end = len(lines)
        while end > start and lines[end - 1] == "":
            end -= 1
        lines, sections = lines[start:end], sections[start:end]

        out_lines: list[str] = []
        out_sections: list[str | None] = []
        blank_run = 0
        for line, section in zip(lines, sections):
            if line == "":
                blank_run += 1
                if blank_run > 1:
                    continue
            else:
                blank_run = 0
            out_lines.append(line)
            out_sections.append(section)
        return out_lines, out_sections

    def get_text(self) -> str:
        lines, _ = self._normalized_lines()
        return "\n".join(lines)

    def get_lines_with_sections(self) -> tuple[str, list[str | None]]:
        """Wie get_text(), liefert zusätzlich pro Zeile die zuletzt gültige
        Section (parallele Liste, 1:1 mit den Zeilen des Textes)."""
        lines, sections = self._normalized_lines()
        return "\n".join(lines), sections


def _html_to_text(html: str) -> tuple[str, list[str | None]]:
    parser = _ConfluenceHTMLParser()
    parser.feed(html)
    return parser.get_lines_with_sections()


def _extract_attachment_text(data: bytes, mime_type: str) -> str | None:
    """Extracts plaintext from attachment bytes. Returns None if unsupported or empty."""
    mime = (mime_type or "").split(";")[0].strip().lower()

    if mime == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(p.strip() for p in pages if p.strip()) or None
        except Exception:
            return None

    if mime in (_XLSX_MIME, _PPTX_MIME):
        # Die Bibliotheken lesen Dateien; deshalb über eine Temp-Datei mit passender Endung.
        import os
        import tempfile

        from connectors.folder import _extract_text

        suffix = ".xlsx" if mime == _XLSX_MIME else ".pptx"
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
                handle.write(data)
                temp_path = handle.name
            try:
                return _extract_text(temp_path).strip() or None
            finally:
                os.unlink(temp_path)
        except Exception:
            return None

    if mime == "text/html":
        from connectors.office import html_to_text

        return html_to_text(data.decode("utf-8", errors="replace")) or None

    if mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        # "application/msword" ist meist echtes Word 97 (nicht lesbar); python-docx liest nur ZIP-basierte Dateien.
        try:
            from docx import Document as DocxDoc

            doc = DocxDoc(io.BytesIO(data))
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs) or None
        except Exception:
            return None

    if mime.startswith("text/"):
        try:
            from connectors.textio import decode_text

            return decode_text(data).strip() or None
        except Exception:
            return None

    return None


def _is_supported_mime(mime_type: str) -> bool:
    mime = (mime_type or "").split(";")[0].strip().lower()
    return mime in _SUPPORTED_MIME_EXACT or any(
        mime.startswith(p) for p in _SUPPORTED_MIME_PREFIXES
    )


class ConfluenceConnector(BaseConnector):
    """
    Crawlt einen Confluence-Space und liefert Seiten als Document-Objekte.

    Confluence liefert `body.view.value` als gerendertes HTML. Die Umwandlung
    in Plaintext erfolgt über _html_to_text (HTMLParser), nicht per Regex,
    damit Entities korrekt dekodiert werden und Code-Blöcke lesbar bleiben.
    """

    # Server/Data Center liefert die REST-API unter /rest/api, Cloud unter /wiki/rest/api. Beide werden einmal
    # je Sync geprüft; der Treffer gilt dann für alle weiteren Aufrufe (kein Probieren pro Seite).
    _API_ROOTS = ("/rest/api", "/wiki/rest/api")

    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._api_root: str | None = None
        self._seen_keys: set[str] = set()
        self._crawl_complete = False
        # Gesetzt, sobald etwas nicht abrufbar war: dann darf dieser Lauf nichts als gelöscht werten.
        self._incomplete = False

    async def _discover_api_root(self, client, base_url, auth, headers) -> str:
        """Findet die REST-Wurzel dieser Installation (Server/DC oder Cloud) mit je einer Anfrage.

        401/403 auf einem Pfad heißt nicht zwingend "falsche Zugangsdaten": Cloud antwortet auf dem
        falschen Pfad teils ebenso. Erst wenn kein Pfad antwortet, wird der Auth-Fehler gemeldet.
        """
        auth_error: str | None = None
        last_error: Exception | None = None
        for root in self._API_ROOTS:
            try:
                response = await client.get(
                    f"{base_url}{root}/space", params={"limit": 1}, auth=auth, headers=headers, timeout=30.0
                )
            except httpx.HTTPError as exc:
                last_error = exc
                continue
            if response.status_code == 200:
                self._log(f"Confluence-API gefunden: {base_url}{root}")
                return root
            if response.status_code in (401, 403):
                auth_error = (
                    f"Anmeldung abgelehnt (HTTP {response.status_code}). Prüfe Benutzername, Passwort "
                    "bzw. Personal Access Token."
                )
        if auth_error:
            raise RuntimeError(auth_error)
        if last_error is not None:
            raise RuntimeError(f"Confluence nicht erreichbar: {type(last_error).__name__}: {last_error}")
        raise RuntimeError(
            f"Keine Confluence-REST-API unter {base_url} gefunden (geprüft: {', '.join(self._API_ROOTS)}). "
            "Prüfe die Server-URL einschließlich eines evtl. Kontextpfads (z. B. /confluence)."
        )

    async def fetch_documents(self):
        spaces = self._parse_spaces()
        self._log(f"Verbinde mit Confluence unter {self.source.url} (Spaces: {spaces})...")
        self._seen_keys = set()
        self._crawl_complete = False
        self._incomplete = False

        # Auth-Setup: Basic Auth hat Vorrang vor Bearer Token
        auth = None
        headers: dict = {}
        if self.source.username and self.source.token:
            auth = (self.source.username, self.source.token)
        elif self.source.token:
            headers["Authorization"] = f"Bearer {self.source.token}"

        base_url = self.source.url.rstrip("/")
        page_limit = 25
        # Ein Durchlauf je gewähltem Space, damit der Server filtert (statt die ganze Instanz zu
        # laden und clientseitig auszusortieren); "ALL" ist ein einzelner Durchlauf ohne Filter.
        space_keys: list[str | None] = [None] if "ALL" in spaces else list(spaces)

        async with httpx.AsyncClient(verify=self._http_verify()) as client:
            self._api_root = await self._discover_api_root(client, base_url, auth, headers)
            counter = 0

            for space_key in space_keys:
                start = 0
                while True:
                    pages_data = await self._fetch_pages(
                        client, base_url, auth, headers, space_key, start, page_limit
                    )

                    results = pages_data.get("results", [])
                    if not results:
                        break

                    for page in results:
                        # Absicherung, falls ein Server den Space-Filter ignoriert.
                        page_space = page.get("space", {}).get("key")
                        if space_key is not None and page_space != space_key:
                            continue

                        counter += 1
                        key = self._page_key(page)
                        self._seen_keys.add(key)
                        doc = self._build_document(page, base_url)
                        self._update_progress(
                            counter,
                            message=f"Verarbeite Seite '{page.get('title', '...')}' ({counter})...",
                        )

                        if doc is not None:
                            yield doc

                        async for att_doc in self._fetch_attachments(
                            client, base_url, auth, headers, page
                        ):
                            yield att_doc

                    start += len(results)
                    # Pagination: Ende erreicht wenn weniger Ergebnisse als erwartet
                    # oder kein "next"-Link in der Antwort
                    if len(results) < page_limit or "next" not in pages_data.get("_links", {}):
                        break

        # Nur ein bis zum Ende durchlaufener Crawl darf zum Aufräumen gelöschter Seiten führen.
        self._crawl_complete = not self._incomplete

    async def sync(self, force_reindex: bool = False) -> None:
        await super().sync()
        if not self._crawl_complete:
            return
        removed = self._remove_orphans(self._seen_keys)
        if removed:
            self.has_changes = True

    # ── Interne Hilfsmethoden ────────────────────────────────────────────────

    async def _fetch_pages(
        self, client, base_url, auth, headers, space_key, start, limit
    ) -> dict:
        """Ruft eine Seite der Content-API ab (Fehler werden weitergereicht, damit der Sync nicht still endet)."""
        params = {
            "type": "page",
            "start": start,
            "limit": limit,
            "expand": "body.view,version,space",
        }
        if space_key is not None:
            params["spaceKey"] = space_key
        return await self._get_json(client, f"{base_url}{self._api_root}/content", auth, headers, params)

    async def _get_json(self, client, url, auth, headers, params) -> dict:
        """GET mit Backoff nur bei 429/5xx/Netzwerkfehlern; 4xx (z. B. 404) werden sofort gemeldet."""
        response = await request_with_retry(
            client, "GET", url, headers_fn=lambda: headers, auth=auth, params=params,
            timeout=30.0, log=self._log,
        )
        await asyncio.sleep(0.05)  # Höflichkeits-Pause zwischen Requests
        return response.json()

    @staticmethod
    def _page_key(page: dict) -> str:
        """Eindeutiger, umbenennungsfester Index-Schlüssel einer Seite: Space und Seiten-ID.

        Der Seitentitel taugt nicht als Schlüssel: Titel wiederholen sich über Spaces hinweg
        (Seiten überschrieben sich gegenseitig) und ändern sich beim Umbenennen.
        """
        return f"{page.get('space', {}).get('key') or '_'}/{page.get('id')}"

    def _adopt_legacy_chunks(self, old_key: str, new_key: str, page_id: str | None) -> None:
        """Früher war der Seitentitel der Schlüssel. Vorhandene Chunks dieser Seite ziehen auf den neuen
        Schlüssel um, damit weder der Index noch bestätigte Verknüpfungen neu aufgebaut werden müssen."""
        if not page_id or old_key == new_key:
            return
        chunks = (
            self.db.query(DocumentChunk)
            .filter(DocumentChunk.source_id == self.source.id, DocumentChunk.file_path == old_key)
            .all()
        )
        moved = False
        for chunk in chunks:
            if str((chunk.metadata_json or {}).get("page_id")) == str(page_id):
                chunk.file_path = new_key
                moved = True
        if moved:
            self.db.commit()

    def _build_document(self, page: dict, base_url: str) -> Document | None:
        """
        Wandelt ein Confluence-Page-Objekt in ein Document um.

        Gibt None zurück wenn:
        - Die Seite seit dem letzten Sync unverändert ist (und Chunks existieren)
        - Der Seiteninhalt leer ist
        """
        title = page.get("title", "Unbekannte Seite")
        key = self._page_key(page)
        self._adopt_legacy_chunks(title, key, page.get("id"))

        # Delta-Sync: Seite überspringen wenn unverändert und bereits indiziert
        updated_at_str = page.get("version", {}).get("when")
        if self.source.last_synced_at and updated_at_str:
            try:
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                if updated_at <= self.source.last_synced_at:
                    chunks_exist = (
                        self.db.query(DocumentChunk)
                        .filter(
                            DocumentChunk.source_id == self.source.id,
                            DocumentChunk.file_path == key,
                        )
                        .first()
                        is not None
                    )
                    if chunks_exist:
                        return None
            except Exception as ex:
                self._log(f"Konnte Änderungszeitpunkt für '{title}' nicht parsen: {ex}")

        body_html = page.get("body", {}).get("view", {}).get("value", "")
        plain_text, line_sections = _html_to_text(body_html)
        if not plain_text:
            self._log(f"Seite '{title}' hat keinen Textinhalt. Überspringe.")
            return None

        # URL aufbauen — Confluence liefert relative Links in _links.webui
        webui = page.get("_links", {}).get("webui", "")
        if "/wiki" in page.get("_links", {}).get("base", ""):
            original_url = f"{base_url}/wiki{webui}"
        elif webui:
            original_url = f"{base_url}{webui}"
        else:
            original_url = f"{base_url}/pages/viewpage.action?pageId={page.get('id')}"

        return Document(
            title=title,
            content=plain_text,
            url=original_url,
            source_type="Confluence",
            storage_key=key,
            extra_meta={"page_id": page.get("id"), "space_key": page.get("space", {}).get("key")},
            line_sections=line_sections,
        )

    async def _list_attachments(self, client, base_url, auth, headers, page_id, page_title) -> list[dict]:
        """Alle Anhänge einer Seite (seitenweise abgefragt, nicht nur die ersten 50)."""
        attachments: list[dict] = []
        start, limit = 0, 50
        while True:
            try:
                resp = await self._get_json(
                    client, f"{base_url}{self._api_root}/content/{page_id}/child/attachment",
                    auth, headers, {"limit": limit, "start": start, "expand": "version"},
                )
            except httpx.HTTPError as exc:
                self._log(f"Anhänge von '{page_title}' nicht abrufbar: {exc}")
                # Unvollständige Liste: kein Aufräumen in diesem Lauf (sonst gingen Anhänge verloren).
                self._incomplete = True
                return attachments
            results = resp.get("results", [])
            attachments.extend(results)
            if len(results) < limit or "next" not in resp.get("_links", {}):
                return attachments
            start += len(results)

    async def _fetch_attachments(self, client, base_url, auth, headers, page: dict):
        """Async generator: yields Document for each supported attachment on a page."""
        page_id = page.get("id")
        page_title = page.get("title", "Unbekannte Seite")
        page_key = self._page_key(page)

        for att in await self._list_attachments(client, base_url, auth, headers, page_id, page_title):
            mime_type = att.get("metadata", {}).get("mediaType", "")
            if not _is_supported_mime(mime_type):
                continue

            filename = att.get("title", "attachment")
            file_size = att.get("extensions", {}).get("fileSize", 0)
            if file_size and file_size > ATTACHMENT_MAX_BYTES:
                self._log(
                    f"Anhang '{filename}' übersprungen (>{ATTACHMENT_MAX_BYTES // (1024 * 1024)} MB)."
                )
                continue

            # Schlüssel über die Anhangs-ID: stabil beim Umbenennen und eindeutig je Seite.
            storage_key = f"{page_key}/attachments/{att.get('id') or filename}"
            self._seen_keys.add(storage_key)
            self._adopt_legacy_chunks(f"{page_title}/attachments/{filename}", storage_key, page_id)

            # Delta-Sync: Anhang überspringen wenn unverändert und bereits indiziert
            updated_at_str = att.get("version", {}).get("when")
            if self.source.last_synced_at and updated_at_str:
                try:
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    if updated_at <= self.source.last_synced_at:
                        if (
                            self.db.query(DocumentChunk)
                            .filter(
                                DocumentChunk.source_id == self.source.id,
                                DocumentChunk.file_path == storage_key,
                            )
                            .first()
                        ):
                            continue
                except Exception:
                    pass

            download_path = att.get("_links", {}).get("download", "")
            if not download_path:
                continue

            try:
                dl_resp = await request_with_retry(
                    client, "GET", f"{base_url}{download_path}", headers_fn=lambda: headers, auth=auth,
                    follow_redirects=True, timeout=60.0, log=self._log,
                )
            except Exception as e:
                self._log(f"Download-Fehler für '{filename}': {e}")
                # Anhang fehlt in diesem Lauf: nicht als gelöscht behandeln.
                self._incomplete = True
                continue

            text = _extract_attachment_text(dl_resp.content, mime_type)
            if not text:
                continue

            att_url = f"{base_url}{download_path}"
            yield Document(
                title=f"{page_title} — {filename}",
                content=text,
                url=att_url,
                source_type="Confluence",
                storage_key=storage_key,
                extra_meta={
                    "page_id": page_id,
                    "attachment_filename": filename,
                    "mime_type": mime_type,
                },
            )
