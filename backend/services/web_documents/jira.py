"""Jira (Cloud und Server/Data Center) als WebDocument."""

from __future__ import annotations

import re
from html import escape
from urllib.parse import parse_qs, urlparse

from services.web_documents.base import (
    Attachment,
    Comment,
    Fact,
    FetchContext,
    Related,
    SourceUnavailable,
    WebAdapter,
    WebDocument,
)

_FIELDS = (
    "summary,description,comment,status,priority,assignee,reporter,issuetype,labels,components,"
    "fixVersions,versions,resolution,created,updated,duedate,parent,subtasks,issuelinks,attachment"
)
_KEY_RE = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)")

# Jira rendert Code und Panels mit eigenen Klassen.
_CSS = """
.code.panel,.preformatted.panel,.panel{border:1px solid var(--wd-border)!important;border-radius:6px;margin:1em 0;overflow:hidden}
.panelHeader,.codeHeader{padding:6px 12px;font-weight:600;background:var(--wd-surface)!important}
.panelContent,.codeContent,.preformattedContent{padding:0 12px}
.panelContent pre,.codeContent pre,.preformattedContent pre{border:0;background:transparent}
.code-keyword{color:var(--wd-accent)}
.code-comment{color:var(--wd-muted)}
.image-wrap{display:inline-block;max-width:100%}
"""


def _name(value: dict | None) -> str | None:
    return (value or {}).get("displayName") or (value or {}).get("name")


def _names(values: list | None) -> list[str]:
    return [item["name"] if isinstance(item, dict) else str(item) for item in values or []]


def _text_to_html(value: object) -> str:
    """Jira Cloud liefert ohne gerendertes Feld einen ADF-Baum, Jira Server Wiki-Text."""
    if isinstance(value, dict):
        return _adf_to_html(value)
    return escape(str(value)).replace("\n", "<br>") if value else ""


_ADF_BLOCKS = {
    "paragraph": "p",
    "bulletList": "ul",
    "orderedList": "ol",
    "listItem": "li",
    "blockquote": "blockquote",
}


def _adf_to_html(node: dict | None) -> str:
    if not node:
        return ""
    kind = node.get("type")
    if kind == "text":
        text = escape(node.get("text", ""))
        for mark in node.get("marks", []):
            mark_type = mark.get("type")
            if mark_type == "strong":
                text = f"<strong>{text}</strong>"
            elif mark_type == "em":
                text = f"<em>{text}</em>"
            elif mark_type == "code":
                text = f"<code>{text}</code>"
            elif mark_type == "link":
                href = escape((mark.get("attrs") or {}).get("href", ""), quote=True)
                text = f'<a href="{href}">{text}</a>'
        return text
    if kind == "hardBreak":
        return "<br>"
    inner = "".join(_adf_to_html(child) for child in node.get("content", []))
    if kind == "heading":
        level = int((node.get("attrs") or {}).get("level", 3))
        return f"<h{level}>{inner}</h{level}>"
    if kind == "codeBlock":
        return f"<pre><code>{inner}</code></pre>"
    tag = _ADF_BLOCKS.get(kind)
    return f"<{tag}>{inner}</{tag}>" if tag else inner


class JiraAdapter(WebAdapter):
    def index_key(self, url: str) -> str | None:
        parsed = urlparse(url)
        selected = parse_qs(parsed.query).get("selectedIssue")
        if selected:
            return selected[0].upper()
        match = _KEY_RE.search(parsed.path)
        return match.group(1).upper() if match else None

    def fetch(self, ctx: FetchContext, key: str, meta: dict) -> WebDocument:
        issue = None
        # /2 gibt es auf Server und Cloud, /3 ist nur der Rückweg, falls /2 abgeschaltet ist.
        for version in ("2", "3"):
            try:
                issue = ctx.get_json(
                    f"/rest/api/{version}/issue/{key}",
                    {"expand": "renderedFields", "fields": _FIELDS},
                )
                break
            except SourceUnavailable:
                continue
        if issue is None:
            raise SourceUnavailable(f"Ticket {key} nicht abrufbar")

        fields = issue.get("fields") or {}
        rendered = issue.get("renderedFields") or {}
        browse = f"{ctx.base_url}/browse"

        facts: list[Fact] = []

        def fact(fact_key: str, label: str, values, kind: str = "text") -> None:
            values = [values] if isinstance(values, str) else [v for v in values or [] if v]
            if values:
                facts.append(Fact(fact_key, label, values, kind))

        fact("type", "Type", (fields.get("issuetype") or {}).get("name"))
        fact("status", "Status", (fields.get("status") or {}).get("name"), "status")
        fact("priority", "Priority", (fields.get("priority") or {}).get("name"))
        fact("resolution", "Resolution", (fields.get("resolution") or {}).get("name"))
        fact("assignee", "Assignee", _name(fields.get("assignee")))
        fact("reporter", "Reporter", _name(fields.get("reporter")))
        fact("labels", "Labels", fields.get("labels"))
        fact("components", "Components", _names(fields.get("components")))
        fact("fix_versions", "Fix versions", _names(fields.get("fixVersions")))
        fact("affects_versions", "Affects versions", _names(fields.get("versions")))
        fact("due", "Due", fields.get("duedate"), "date")
        fact("created", "Created", fields.get("created"), "date")
        fact("updated", "Updated", fields.get("updated"), "date")

        comment_block = fields.get("comment") or {}
        rendered_comments = (rendered.get("comment") or {}).get("comments") or []
        comments = []
        for index, comment in enumerate(comment_block.get("comments") or []):
            html = rendered_comments[index].get("body") if index < len(rendered_comments) else None
            comments.append(
                Comment(
                    author=_name(comment.get("author")) or "",
                    created=comment.get("created"),
                    body_html=html or _text_to_html(comment.get("body")),
                )
            )

        related: list[Related] = []

        def relate(relation: str, other: dict | None) -> None:
            if not other or not other.get("key"):
                return
            other_fields = other.get("fields") or {}
            related.append(
                Related(
                    relation=relation,
                    title=other_fields.get("summary") or other["key"],
                    url=f"{browse}/{other['key']}",
                    identifier=other["key"],
                    status=(other_fields.get("status") or {}).get("name"),
                )
            )

        relate("parent", fields.get("parent"))
        for subtask in fields.get("subtasks") or []:
            relate("subtask", subtask)
        for link in fields.get("issuelinks") or []:
            kind = link.get("type") or {}
            if link.get("outwardIssue"):
                relate(kind.get("outward") or kind.get("name") or "", link["outwardIssue"])
            if link.get("inwardIssue"):
                relate(kind.get("inward") or kind.get("name") or "", link["inwardIssue"])

        return WebDocument(
            title=fields.get("summary") or key,
            url=f"{browse}/{key}",
            kind="ticket",
            identifier=key,
            facts=facts,
            body_html=rendered.get("description") or _text_to_html(fields.get("description")),
            comments=comments,
            comments_total=comment_block.get("total"),
            attachments=[
                Attachment(
                    name=item.get("filename") or "",
                    url=item["content"],
                    size=item.get("size"),
                    mime=item.get("mimeType"),
                )
                for item in fields.get("attachment") or []
                if item.get("content")
            ],
            related=related,
            extra_css=_CSS,
        )
