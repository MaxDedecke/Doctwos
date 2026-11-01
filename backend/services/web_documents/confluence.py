"""Confluence (Cloud und Server/Data Center) als WebDocument."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from services.web_documents.base import (
    Attachment,
    Comment,
    Crumb,
    Fact,
    FetchContext,
    NotRenderable,
    SourceUnavailable,
    WebAdapter,
    WebDocument,
)

_PAGE_RE = re.compile(r"/pages/(\d+)(?:/|$)")
_PAGE_KEY_RE = re.compile(r"[^/]+/(\d+)")
_API_ROOTS = ("/rest/api", "/wiki/rest/api")
_PAGE_LIMIT = 100

# Makros kommen als fertiges HTML mit Confluence-Klassen; deren Stylesheet und Skripte fehlen hier.
_CSS = """
.confluence-information-macro{border:1px solid var(--wd-border);border-left:4px solid var(--wd-accent);border-radius:6px;padding:10px 14px;margin:1em 0;background:var(--wd-surface)!important}
.confluence-information-macro-warning{border-left-color:var(--wd-danger)}
.confluence-information-macro-note{border-left-color:var(--wd-warning)}
.confluence-information-macro-tip{border-left-color:var(--wd-success)}
.confluence-information-macro .title{font-weight:700;margin-bottom:4px}
.confluence-information-macro-icon{display:none}
.panel{border:1px solid var(--wd-border)!important;border-radius:6px;margin:1em 0;overflow:hidden}
.panelHeader{padding:6px 12px;font-weight:600;background:var(--wd-surface)!important}
.panelContent{padding:8px 12px}
.code.panel .codeContent,.codeContent{padding:0}
.table-wrap{overflow-x:auto;margin:1em 0}
.status-macro,.aui-lozenge{display:inline-block;padding:0 6px;border-radius:3px;border:1px solid var(--wd-border);font-size:.75em;font-weight:700;text-transform:uppercase}
.client-side-toc-macro:empty{display:none}
.expand-content{display:block!important;opacity:1!important;height:auto!important}
.expand-control{font-weight:600}
.expand-control-icon{display:none}
.confluence-embedded-file-wrapper{display:inline-block;max-width:100%}
.user-mention{font-weight:600}
"""


class ConfluenceAdapter(WebAdapter):
    def index_key(self, url: str) -> str | None:
        parsed = urlparse(url)
        page_id = parse_qs(parsed.query).get("pageId")
        if page_id:
            return f"*/{page_id[0]}"
        match = _PAGE_RE.search(parsed.path)
        return f"*/{match.group(1)}" if match else None

    def fetch(self, ctx: FetchContext, key: str, meta: dict) -> WebDocument:
        # Seiten heißen ``SPACE/ID``; Anhänge liegen darunter und werden nur als Text gezeigt.
        match = _PAGE_KEY_RE.fullmatch(key)
        if not match:
            raise NotRenderable(key)
        page_id = match.group(1)

        page, root = None, None
        for candidate in _API_ROOTS:
            try:
                page = ctx.get_json(
                    f"{candidate}/content/{page_id}",
                    {"expand": "body.view,version,space,ancestors,history,metadata.labels"},
                )
                root = candidate
                break
            except SourceUnavailable:
                continue
        if page is None:
            raise SourceUnavailable(f"Seite {page_id} nicht abrufbar")

        links = page.get("_links") or {}
        site = ctx.base_url
        # Nur der Pfad zählt: Viele Instanzen heißen selbst wiki.firma.de.
        if urlparse(links.get("base") or "").path.rstrip("/").endswith("/wiki") and not site.endswith(
            "/wiki"
        ):
            site = f"{site}/wiki"

        version = page.get("version") or {}
        history = page.get("history") or {}
        facts: list[Fact] = []

        def fact(fact_key: str, label: str, value, kind: str = "text") -> None:
            values = value if isinstance(value, list) else [value]
            values = [str(v) for v in values if v not in (None, "")]
            if values:
                facts.append(Fact(fact_key, label, values, kind))

        fact("space", "Space", (page.get("space") or {}).get("name"))
        fact("version", "Version", version.get("number"))
        fact("modified_by", "Modified by", (version.get("by") or {}).get("displayName"))
        fact("updated", "Updated", version.get("when"), "date")
        fact("author", "Author", (history.get("createdBy") or {}).get("displayName"))
        fact("created", "Created", history.get("createdDate"), "date")
        fact(
            "labels",
            "Labels",
            [
                label.get("name")
                for label in ((page.get("metadata") or {}).get("labels") or {}).get("results") or []
            ],
        )

        comments: list[Comment] = []
        comments_total = None
        attachments: list[Attachment] = []
        # Die Seite steht; fehlen Kommentare oder Anhänge, wird sie trotzdem gezeigt.
        try:
            data = ctx.get_json(
                f"{root}/content/{page_id}/child/comment",
                {"limit": _PAGE_LIMIT, "depth": "all", "expand": "body.view,version,history"},
            )
            comments_total = data.get("size")
            for item in data.get("results") or []:
                comments.append(
                    Comment(
                        author=((item.get("history") or {}).get("createdBy") or {}).get(
                            "displayName"
                        )
                        or ((item.get("version") or {}).get("by") or {}).get("displayName")
                        or "",
                        created=(item.get("history") or {}).get("createdDate")
                        or (item.get("version") or {}).get("when"),
                        body_html=((item.get("body") or {}).get("view") or {}).get("value") or "",
                    )
                )
            data = ctx.get_json(
                f"{root}/content/{page_id}/child/attachment", {"limit": _PAGE_LIMIT}
            )
            for item in data.get("results") or []:
                download = (item.get("_links") or {}).get("download")
                if download:
                    attachments.append(
                        Attachment(
                            name=item.get("title") or "",
                            url=f"{site}{download}",
                            size=(item.get("extensions") or {}).get("fileSize"),
                            mime=(item.get("extensions") or {}).get("mediaType"),
                        )
                    )
        except SourceUnavailable:
            pass

        webui = links.get("webui")
        return WebDocument(
            title=page.get("title") or meta.get("title") or key,
            url=f"{site}{webui}" if webui else meta.get("url"),
            kind="page",
            facts=facts,
            breadcrumbs=[
                Crumb(
                    title=ancestor.get("title") or "",
                    url=f"{site}/pages/viewpage.action?pageId={ancestor['id']}"
                    if ancestor.get("id")
                    else None,
                )
                for ancestor in page.get("ancestors") or []
            ],
            body_html=((page.get("body") or {}).get("view") or {}).get("value") or "",
            comments=comments,
            comments_total=comments_total,
            attachments=attachments,
            extra_css=_CSS,
        )
