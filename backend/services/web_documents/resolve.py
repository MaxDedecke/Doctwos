"""Vom Verweis zum fertigen WebDocument: Index-Prüfung, Abruf, Rückfall, Links und Bilder.

Angezeigt wird nur, was der Sync dieser Quelle aufgenommen hat. Die Zugangsdaten einer Quelle können mehr lesen
als freigegeben ist (andere Bereiche, gesperrte Seiten), eine frei übergebene URL darf das nicht öffnen.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import asdict
from html import escape, unescape
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import or_
from sqlalchemy.orm import Session

import core.config as cfg
from doctus_models.database import DocumentChunk, KnowledgeSource, User
from services.source_access import source_visible
from services.web_documents import adapter_for, is_web_source
from services.web_documents.base import FetchContext, NotRenderable, WebDocument

logger = logging.getLogger(__name__)

ASSET_MAX_AGE_SECONDS = 3600
ASSET_MAX_BYTES = 50 * 1024 * 1024
_ASSET_MAX_REDIRECTS = 3
_INDEX_MAX_CHUNKS = 400
_MAX_LINKS = 200

_signer = URLSafeTimedSerializer(cfg.SESSION_SECRET_KEY, salt="doctus-web-asset")
_TAG_RE = re.compile(r"<(a|img)\b([^>]*)>", re.IGNORECASE)


def _attribute(attributes: str, name: str) -> re.Match | None:
    return re.search(rf"""\b{name}\s*=\s*("[^"]*"|'[^']*')""", attributes, re.IGNORECASE)


def _same_origin(url: str, base_url: str) -> bool:
    first, second = urlparse(url), urlparse(base_url)
    return (first.scheme, first.netloc) == (second.scheme, second.netloc)


def source_access(source: KnowledgeSource) -> tuple[tuple[str, str] | None, dict]:
    if source.username and source.token:
        return (source.username, source.token), {}
    if source.token:
        return None, {"Authorization": f"Bearer {source.token}"}
    return None, {}


# ── Index ────────────────────────────────────────────────────────────────────


def _find_indexed(db: Session, source: KnowledgeSource, reference: str) -> tuple[str, dict] | None:
    """Index-Schlüssel und Metadaten eines Verweises: Schlüssel, URL-Muster oder gespeicherte URL."""
    chunks = db.query(DocumentChunk.file_path, DocumentChunk.metadata_json).filter(
        DocumentChunk.source_id == source.id
    )
    reference = reference.split("#", 1)[0]
    row = None
    if not reference.lower().startswith(("http://", "https://")):
        row = (
            chunks.filter(DocumentChunk.file_path == reference).first()
            or chunks.filter(DocumentChunk.file_path.ilike(reference, escape="\\")).first()
        )
    elif _same_origin(reference, source.url or ""):
        key = adapter_for(source.type).index_key(reference)
        if key:
            column = DocumentChunk.file_path
            row = chunks.filter(
                column.endswith(key[1:], autoescape=True) if key[0] == "*" else column == key
            ).first()
        if row is None:
            row = chunks.filter(DocumentChunk.metadata_json["url"].as_string() == reference).first()
    return (row[0], row[1] or {}) if row else None


def _from_index(db: Session, source: KnowledgeSource, key: str, meta: dict, notice: str) -> WebDocument:
    rows = (
        db.query(DocumentChunk.content)
        .filter(
            DocumentChunk.source_id == source.id,
            or_(
                DocumentChunk.file_path == key,
                DocumentChunk.file_path.startswith(f"{key}#", autoescape=True),
            ),
        )
        .order_by(DocumentChunk.start_line, DocumentChunk.id)
        .limit(_INDEX_MAX_CHUNKS)
        .all()
    )
    text = "\n".join(row[0] or "" for row in rows)
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    return WebDocument(
        title=meta.get("title") or key,
        url=meta.get("url"),
        body_html="".join(f"<p>{escape(part).replace(chr(10), '<br>')}</p>" for part in paragraphs),
        origin="index",
        notice=notice,
        synced_at=source.last_synced_at.isoformat() if source.last_synced_at else None,
    )


# ── Links und Bilder ─────────────────────────────────────────────────────────


def _known_links(
    db: Session, user: User, source: KnowledgeSource, urls: Iterable[str]
) -> dict[str, int]:
    """Welche Links auf indexierte Einträge sichtbarer Quellen desselben Projekts zeigen."""
    urls = list(dict.fromkeys(urls))[:_MAX_LINKS]
    if not urls:
        return {}
    others = (
        db.query(KnowledgeSource).filter(KnowledgeSource.project_id == source.project_id).all()
        if source.project_id is not None
        else [source]
    )
    known: dict[str, int] = {}
    for other in others:
        adapter = adapter_for(other.type)
        base = (other.url or "").rstrip("/")
        if not base or not is_web_source(other.type):
            continue
        wanted = {}
        for url in urls:
            if url not in known and url.startswith(f"{base}/"):
                key = adapter.index_key(url.split("#", 1)[0])
                if key:
                    wanted[url] = key
        if not wanted or not source_visible(db, user, other.id):
            continue
        column = DocumentChunk.file_path
        rows = (
            db.query(column)
            .filter(
                DocumentChunk.source_id == other.id,
                or_(
                    *(
                        column.endswith(key[1:], autoescape=True) if key[0] == "*" else column == key
                        for key in set(wanted.values())
                    )
                ),
            )
            .distinct()
            .all()
        )
        keys = [row[0] for row in rows]
        for url, key in wanted.items():
            found = any(k.endswith(key[1:]) for k in keys) if key[0] == "*" else key in keys
            if found:
                known[url] = other.id
    return known


def asset_url(source_id: int, url: str, download_name: str | None = None) -> str:
    """Signierter Pfad: Das abgeschottete iframe schickt kein Sitzungs-Cookie mit."""
    token = _signer.dumps({"s": source_id, "u": url, "n": download_name})
    return f"/knowledge-sources/{source_id}/web-asset?token={token}"


def read_asset_token(source_id: int, token: str) -> tuple[str, str | None]:
    try:
        data = _signer.loads(token, max_age=ASSET_MAX_AGE_SECONDS)
    except BadSignature as exc:
        raise HTTPException(status_code=403, detail="Ungültiger oder abgelaufener Verweis") from exc
    if data.get("s") != source_id:
        raise HTTPException(status_code=403, detail="Ungültiger Verweis")
    return data["u"], data.get("n")


def _absolute_hrefs(html: str, page_url: str) -> list[str]:
    hrefs = []
    for match in _TAG_RE.finditer(html):
        if match.group(1).lower() == "a":
            href = _attribute(match.group(2), "href")
            if href:
                value = unescape(href.group(1)[1:-1]).strip()
                if value and not value.startswith("#"):
                    hrefs.append(urljoin(page_url, value))
    return hrefs


def _rewrite_html(html: str, page_url: str, source: KnowledgeSource, known: dict[str, int]) -> str:
    """Macht Links absolut und markiert bekannte; Bilder der Instanz laufen über den Asset-Pfad."""

    def replace(match: re.Match) -> str:
        tag, attributes = match.group(1).lower(), match.group(2)
        closing = "/" if attributes.rstrip().endswith("/") else ""
        attributes = attributes.rstrip().rstrip("/")
        name = "href" if tag == "a" else "src"
        found = _attribute(attributes, name)
        if not found:
            return match.group(0)
        value = unescape(found.group(1)[1:-1]).strip()
        if tag == "a" and value.startswith("#"):
            return match.group(0)
        target = urljoin(page_url, value)
        extra = ""
        if tag == "img":
            attributes = re.sub(r"""\bsrcset\s*=\s*("[^"]*"|'[^']*')""", "", attributes, flags=re.I)
            found = _attribute(attributes, name)
            if _same_origin(target, source.url or ""):
                target = asset_url(source.id, target)
        elif target in known:
            extra = f' data-doctus-source="{known[target]}" data-doctus-url="{escape(target, quote=True)}"'
        attributes = (
            attributes[: found.start()]
            + f'{name}="{escape(target, quote=True)}"'
            + attributes[found.end() :]
        )
        return f"<{tag}{attributes}{extra}{closing}>"

    return _TAG_RE.sub(replace, html)


def _finish(db: Session, user: User, source: KnowledgeSource, document: WebDocument) -> WebDocument:
    page_url = document.url or (source.url or "")
    hrefs = _absolute_hrefs(document.body_html, page_url)
    for comment in document.comments:
        hrefs += _absolute_hrefs(comment.body_html, page_url)
    hrefs += [item.url for item in document.related]
    hrefs += [crumb.url for crumb in document.breadcrumbs if crumb.url]
    known = _known_links(db, user, source, hrefs)

    document.body_html = _rewrite_html(document.body_html, page_url, source, known)
    for comment in document.comments:
        comment.body_html = _rewrite_html(comment.body_html, page_url, source, known)
    for related in document.related:
        related.source_id = known.get(related.url)
    for crumb in document.breadcrumbs:
        crumb.source_id = known.get(crumb.url) if crumb.url else None
    for attachment in document.attachments:
        if _same_origin(attachment.url, source.url or ""):
            attachment.url = asset_url(source.id, attachment.url, attachment.name or "download")
    return document


# ── Einstieg ─────────────────────────────────────────────────────────────────


def resolve_web_document(
    db: Session, user: User, source: KnowledgeSource, reference: str, verify
) -> dict:
    if not is_web_source(source.type):
        raise HTTPException(status_code=400, detail="Diese Quelle liefert Dateien, keine Webinhalte.")
    found = _find_indexed(db, source, reference)
    if found is None:
        raise HTTPException(status_code=404, detail="Dieser Eintrag gehört nicht zum Index der Quelle.")
    key, meta = found

    auth, headers = source_access(source)
    try:
        with httpx.Client(timeout=15.0, verify=verify) as client:
            ctx = FetchContext(client, (source.url or "").rstrip("/"), auth, headers)
            document = adapter_for(source.type).fetch(ctx, key, meta)
    except NotRenderable:
        document = _from_index(db, source, key, meta, "index_only")
    except Exception as exc:  # noqa: BLE001 - jeder Fehler der Quelle endet beim Indexstand, nicht beim Nutzer
        logger.warning("Webansicht: Quelle %s nicht abrufbar: %s", source.id, type(exc).__name__)
        document = _from_index(db, source, key, meta, "unreachable")
    document = _finish(db, user, source, document)
    return {"format": "web_document", "document": asdict(document), "url": document.url}


def open_asset(source: KnowledgeSource, url: str, verify) -> tuple[httpx.Client, httpx.Response]:
    """Öffnet ein Bild oder einen Anhang der Instanz. Zugangsdaten gehen nur an deren eigene Adresse."""
    auth, headers = source_access(source)
    client = httpx.Client(timeout=30.0, verify=verify, follow_redirects=False)
    try:
        for _ in range(_ASSET_MAX_REDIRECTS + 1):
            if not _same_origin(url, source.url or ""):
                raise HTTPException(status_code=403, detail="Adresse außerhalb der Quelle")
            response = client.send(
                client.build_request("GET", url, headers=headers), auth=auth, stream=True
            )
            if not response.is_redirect:
                if response.status_code != 200:
                    response.close()
                    raise HTTPException(status_code=404, detail="Datei nicht abrufbar")
                return client, response
            location = response.headers.get("location", "")
            response.close()
            url = urljoin(url, location)
        raise HTTPException(status_code=404, detail="Zu viele Weiterleitungen")
    except Exception:
        client.close()
        raise
