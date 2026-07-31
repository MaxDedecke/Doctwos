"""
parser/connectors/webdav.py
===========================
Connector für WebDAV-Verzeichnisse (Nextcloud, ownCloud, SharePoint, WebDAV-Shares).

Ablauf:
    1. WebDAV-Verzeichnis per PROPFIND rekursiv scannen
    2. Datei-Metadaten (Last-Modified + Size) hashen und mit SourceScanFile-Eintrag vergleichen
    3. Nur neue oder veränderte Dateien herunterladen und als Document yielden (Delta-Sync)
    4. Nach dem Sync: SourceScanFile-Tabelle aktualisieren + Orphan-Chunks löschen

Unterstützte Formate: PDF (Text-Layer + OCR-Fallback), DOCX/DOC, TXT, MD
"""

import hashlib
import json
import logging
import os
import tempfile
from typing import AsyncIterator
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET
import httpx
from sqlalchemy import or_

from connectors.base import BaseConnector, Document
from connectors.extract import extract_cloud_file
from db import SessionLocal
from models.database import CodeEntity, DocumentChunk, SourceScanFile, KnowledgeSource

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md"}

# PROPFIND-/List-Aufrufe (XML, klein): großzügiger Read-Timeout statt httpx-Default (5 s).
_API_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)
# Datei-Downloads: reale Anhänge sind zig–hunderte MB und laden nicht in 5 s.
# read=None hebt den Read-Timeout für den (gestreamten) Body auf, Connect bleibt begrenzt.
_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=None, pool=10.0)
_DOWNLOAD_CHUNK = 1024 * 1024  # 1 MiB Chunks auf Platte statt Gesamtdatei in RAM


def _resolve_verify(spaces_config: dict):
    """TLS-Verifikation für httpx aus der Quell-Konfiguration ableiten.

    Standard ist verify=True (Sicherheit per Default). Für self-hosted Server (Nextcloud/
    ownCloud/SharePoint) mit interner CA kann ``spaces.ca_bundle`` auf ein CA-Bundle zeigen;
    nur als ausdrücklicher Opt-out schaltet ``spaces.verify_ssl = false`` die Prüfung ab.
    """
    ca_bundle = spaces_config.get("ca_bundle")
    if ca_bundle:
        return ca_bundle
    return bool(spaces_config.get("verify_ssl", True))


def _get_webdav_hash(item: dict) -> str:
    lm = item.get("last_modified") or ""
    sz = item.get("size") or 0
    raw = f"{lm}#{sz}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _get_local_name(tag: str) -> str:
    if '}' in tag:
        return tag.split('}', 1)[1]
    return tag


def _parse_webdav_xml(xml_content: bytes) -> list[dict]:
    root = ET.fromstring(xml_content)
    results = []

    # Find DAV response elements dynamically
    response_nodes = []
    for node in root.iter():
        if _get_local_name(node.tag) == 'response':
            response_nodes.append(node)

    for resp in response_nodes:
        href = None
        is_dir = False
        size = 0
        last_modified = None

        href_node = next((n for n in resp if _get_local_name(n.tag) == 'href'), None)
        if href_node is not None:
            href = href_node.text

        propstat_nodes = [n for n in resp if _get_local_name(n.tag) == 'propstat']
        for propstat in propstat_nodes:
            status_node = next((n for n in propstat if _get_local_name(n.tag) == 'status'), None)
            if status_node is not None and "200" not in status_node.text:
                continue

            prop_node = next((n for n in propstat if _get_local_name(n.tag) == 'prop'), None)
            if prop_node is not None:
                for prop in prop_node:
                    local_prop = _get_local_name(prop.tag)
                    if local_prop == 'resourcetype':
                        if any(_get_local_name(child.tag) == 'collection' for child in prop):
                            is_dir = True
                    elif local_prop == 'getcontentlength':
                        try:
                            size = int(prop.text)
                        except (ValueError, TypeError):
                            pass
                    elif local_prop == 'getlastmodified':
                        last_modified = prop.text

        if href:
            results.append({
                "href": href,
                "is_dir": is_dir,
                "size": size,
                "last_modified": last_modified
            })
    return results


class WebdavConnector(BaseConnector):

    def __init__(self, source_id: int) -> None:
        super().__init__(source_id)
        self._current_scan: dict[str, dict] = {}
        self._successful_files: set[str] = set()
        self._new_or_changed: set[str] = set()
        self._auth = None
        self._headers = {}
        # TLS-Verifikation (True | CA-Bundle-Pfad | False), aus spaces-Config abgeleitet.
        self._verify = True
        # DB-Primärschlüssel des Projekts (für CodeEntity.project_id).
        self._db_project_id: int | None = None
        # Bei jedem gefangenen Scan-Fehler auf False gesetzt: ein unvollständiger Scan darf
        # nicht autoritativ für die Orphan-Bereinigung werden (sonst stiller Datenverlust
        # bei einem transienten Fehler auf einem Teilverzeichnis).
        self._scan_complete: bool = True

    def _prepare_auth(self) -> None:
        spaces_config = self.source.spaces or {}
        if isinstance(spaces_config, str):
            try:
                spaces_config = json.loads(spaces_config)
            except Exception:
                spaces_config = {}
        self._verify = _resolve_verify(spaces_config)

        token_str = self.source.token
        if token_str:
            try:
                creds = json.loads(token_str)
                if isinstance(creds, dict):
                    username = creds.get("username")
                    password = creds.get("password")
                    if username and password:
                        self._auth = (username, password)
                        return
            except Exception:
                pass
            # Fallback structure: treat as raw API key or token
            self._headers["Authorization"] = f"Bearer {token_str}"

    async def _scan_webdav_recursive(self, base_url: str) -> dict[str, dict]:
        """Scannt das WebDAV-Verzeichnis rekursiv nach unterstützten Dateien."""
        scanned_files = {}
        queue = [base_url]
        visited = set()

        body = """<?xml version="1.0" encoding="utf-8" ?>
<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname/>
    <d:getcontentlength/>
    <d:getlastmodified/>
    <d:resourcetype/>
  </d:prop>
</d:propfind>"""

        prop_headers = dict(self._headers)
        prop_headers["Depth"] = "1"
        prop_headers["Content-Type"] = "application/xml; charset=utf-8"

        async with httpx.AsyncClient(verify=self._verify, timeout=_API_TIMEOUT) as client:
            while queue:
                current_url = queue.pop(0)
                if current_url in visited:
                    continue
                visited.add(current_url)

                try:
                    self._log(f"Scanne WebDAV-Ordner: {current_url}")
                    response = await client.request(
                        "PROPFIND", current_url, content=body,
                        headers=prop_headers, auth=self._auth
                    )
                    response.raise_for_status()
                    items = _parse_webdav_xml(response.content)

                    for item in items:
                        # Href auflösen
                        full_item_url = urljoin(current_url, item["href"])
                        
                        # Infinite Loops durch Self-Referencing verhindern
                        if full_item_url == current_url or full_item_url + "/" == current_url:
                            continue

                        if item["is_dir"]:
                            # Sicherstellen, dass Verzeichnisse mit einem Slash enden
                            dir_url = full_item_url if full_item_url.endswith("/") else full_item_url + "/"
                            if dir_url not in visited:
                                queue.append(dir_url)
                        else:
                            ext = os.path.splitext(urlparse(full_item_url).path)[1].lower()
                            if ext in SUPPORTED_EXTENSIONS:
                                scanned_files[full_item_url] = item

                except Exception as e:
                    self._log(f"[WARNUNG] Fehler beim Scannen von '{current_url}': {e}")
                    # Verzeichnis unvollständig gelesen → Scan als unvollständig markieren,
                    # damit sync() die Orphan-Bereinigung überspringt (kein stiller Datenverlust).
                    self._scan_complete = False
                    continue

        return scanned_files

    async def fetch_documents(self) -> AsyncIterator[Document]:
        base_url = (self.source.url or "").strip()
        if not base_url:
            raise ValueError("WebDAV-Basis-URL fehlt oder ist leer.")

        # Stelle sicher, dass der Pfad mit einem Slash endet
        if not base_url.endswith("/"):
            base_url += "/"

        self._prepare_auth()
        self._db_project_id = self.source.project_id
        self._log(f"Starte WebDAV-Verbindung zu: {base_url}")
        
        # 1. Rekursiver Verzeichnis-Scan
        raw_scan = await self._scan_webdav_recursive(base_url)
        self._current_scan = {url: _get_webdav_hash(meta) for url, meta in raw_scan.items()}
        self._log(f"{len(self._current_scan)} unterstützte Datei(en) auf WebDAV-Server gefunden.")

        # 2. Delta-Sync Abgleich
        existing: dict[str, str] = {
            r.file_path: r.content_hash
            for r in self.db.query(SourceScanFile).filter(
                SourceScanFile.source_id == self.source_id
            ).all()
        }

        new_or_changed = [
            url for url, h in self._current_scan.items()
            if existing.get(url) != h
        ]
        self._new_or_changed = set(new_or_changed)
        self._successful_files = set()
        self._log(
            f"{len(new_or_changed)} neue/veränderte Datei(en) werden heruntergeladen und indiziert, "
            f"{len(self._current_scan) - len(new_or_changed)} unverändert übersprungen."
        )

        # 3. Download & Text-Extraktion
        async with httpx.AsyncClient(verify=self._verify, timeout=_API_TIMEOUT) as client:
            for i, file_url in enumerate(new_or_changed, start=1):
                parsed = urlparse(file_url)
                rel_path = parsed.path.replace(urlparse(base_url).path, "", 1)
                file_name = os.path.basename(parsed.path)
                ext = os.path.splitext(parsed.path)[1].lower()

                self._update_progress(i, len(new_or_changed), f"Lade herunter: {file_name}")
                try:
                    # Gestreamter Download: chunked auf Platte schreiben statt die ganze
                    # (u. U. hunderte MB große) Datei via response.content in den RAM zu laden.
                    async with client.stream(
                        "GET", file_url, auth=self._auth, headers=self._headers,
                        timeout=_DOWNLOAD_TIMEOUT,
                    ) as response:
                        response.raise_for_status()
                        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
                            async for chunk in response.aiter_bytes(_DOWNLOAD_CHUNK):
                                tmp_file.write(chunk)
                            tmp_path = tmp_file.name

                    try:
                        docs, entities = extract_cloud_file(
                            tmp_path, ext,
                            file_key=file_url,
                            title=rel_path,
                            source_type="WebDAV",
                            url=file_url,
                            extra_meta_base={"base_url": base_url, "file_name": file_name},
                        )
                    finally:
                        os.remove(tmp_path)

                except Exception as e:
                    self._log(f"[FEHLER] '{file_name}' konnte nicht verarbeitet werden: {e}")
                    continue

                if not any(d["content"].strip() for d in docs):
                    self._log(f"[SKIP] Kein Textinhalt in '{file_name}'.")
                    continue

                self._successful_files.add(file_url)
                for doc in docs:
                    yield doc

    async def sync(self) -> None:
        await super().sync()

        db = SessionLocal()
        try:
            if not self._current_scan:
                return

            existing_records = {
                r.file_path: r
                for r in db.query(SourceScanFile).filter(
                    SourceScanFile.source_id == self.source_id
                ).all()
            }

            # Orphans NUR bei nachweislich vollständigem Scan bereinigen. Ein transienter
            # Fehler auf einem Teilverzeichnis macht _current_scan unvollständig; eine
            # Bereinigung dagegen würde gültige Dokumente unwiederbringlich löschen.
            if not self._scan_complete:
                logger.warning(
                    "[WebdavConnector] Scan unvollständig (Fehler auf einem Teilverzeichnis) — "
                    "Orphan-Bereinigung übersprungen, um keinen gültigen Index zu löschen."
                )
                src = db.query(KnowledgeSource).filter(KnowledgeSource.id == self.source_id).first()
                if src:
                    src.sync_log = (src.sync_log or "") + (
                        "[WARNUNG] Unvollständiger Scan — verwaiste Einträge wurden NICHT gelöscht. "
                        "Der nächste vollständige Sync bereinigt automatisch.\n"
                    )
            else:
                for path, record in existing_records.items():
                    if path not in self._current_scan:
                        # Eine Datei kann mehrere Chunks unter "<url>#<suffix>" ablegen —
                        # daher zusätzlich zum Exakt-Match auch den Präfix-Match bereinigen.
                        db.query(DocumentChunk).filter(
                            DocumentChunk.source_id == self.source_id,
                            or_(
                                DocumentChunk.file_path == path,
                                DocumentChunk.file_path.like(f"{path}#%"),
                            ),
                        ).delete(synchronize_session=False)
                        # Verwaiste Entities dieser Datei ebenfalls entfernen.
                        db.query(CodeEntity).filter(
                            CodeEntity.source_id == self.source_id,
                            CodeEntity.file_path == path,
                        ).delete(synchronize_session=False)
                        db.delete(record)
                        self.has_changes = True

            # Scan-Tabelle aktualisieren
            for path, content_hash in self._current_scan.items():
                if path in self._new_or_changed and path not in self._successful_files:
                    continue

                if path in existing_records:
                    existing_records[path].content_hash = content_hash
                else:
                    db.add(SourceScanFile(
                        source_id=self.source_id,
                        file_path=path,
                        content_hash=content_hash,
                    ))

            db.commit()
        except Exception as e:
            logger.error(f"[WebdavConnector] Fehler beim Aktualisieren der SourceScanFile-Tabelle: {e}")
            db.rollback()
        finally:
            db.close()
