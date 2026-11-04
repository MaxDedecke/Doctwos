"""GitLab Issues (selbst gehostet und gitlab.com) als WebDocument."""

from __future__ import annotations

import re

import markdown

from services.web_documents.base import (
    Comment,
    Crumb,
    Fact,
    FetchContext,
    NotRenderable,
    Related,
    SourceUnavailable,
    WebAdapter,
    WebDocument,
)

# Schlüssel des Konnektors (parser/connectors/gitlab_issues.py): numerische Projekt-ID und IID.
_KEY_RE = re.compile(r"(\d+)/issues/(\d+)")
_NOTE_PAGES = 20
_STATES = {"opened": "Open", "closed": "Closed"}

_CSS = """
.task-list-item{list-style:none}
.task-list-item input{margin-right:6px}
"""


def _html(text: str | None) -> str:
    """GitLab liefert für einzelne Issues kein gerendertes HTML mehr, nur Markdown."""
    if not text:
        return ""
    return markdown.markdown(text, extensions=["fenced_code", "tables", "sane_lists"])


def _hidden(note: dict) -> bool:
    """Dieselben Ausschlüsse wie beim Import: Systemnotizen, interne und vertrauliche Kommentare."""
    return bool(note.get("system") or note.get("internal") or note.get("confidential"))


class GitLabIssuesAdapter(WebAdapter):
    def index_key(self, url: str) -> str | None:
        # Der Schlüssel braucht die Projekt-ID, die URL nennt nur den Pfad; Links findet der Index
        # über die beim Import gespeicherte URL.
        return None

    def fetch(self, ctx: FetchContext, key: str, meta: dict) -> WebDocument:
        match = _KEY_RE.fullmatch(key)
        if not match:
            raise NotRenderable(key)
        project_id, iid = match.groups()
        api = f"/api/v4/projects/{project_id}"
        issue = ctx.get_json(f"{api}/issues/{iid}")
        # Inzwischen vertraulich: nur der zuletzt freigegebene Indexstand, bis der nächste Sync ihn entfernt.
        if issue.get("confidential"):
            raise NotRenderable(key)

        facts: list[Fact] = []

        def fact(fact_key: str, label: str, values, kind: str = "text") -> None:
            values = [values] if isinstance(values, str) else [v for v in values or [] if v]
            if values:
                facts.append(Fact(fact_key, label, values, kind))

        state = issue.get("state") or ""
        fact("status", "Status", _STATES.get(state, state), "status")
        fact("type", "Type", (issue.get("issue_type") or "").capitalize())
        fact("labels", "Labels", issue.get("labels"))
        fact("milestone", "Milestone", (issue.get("milestone") or {}).get("title"))
        fact("assignee", "Assignee", [(a or {}).get("name") for a in issue.get("assignees") or []])
        fact("author", "Author", (issue.get("author") or {}).get("name"))
        fact("due", "Due", issue.get("due_date"), "date")
        fact("created", "Created", issue.get("created_at"), "date")
        fact("updated", "Updated", issue.get("updated_at"), "date")
        fact("closed", "Closed", issue.get("closed_at"), "date")

        breadcrumbs: list[Crumb] = []
        try:
            project = ctx.get_json(api)
            path = project.get("path_with_namespace") or ""
            names = [part.strip() for part in (project.get("name_with_namespace") or "").split("/")]
            parts = path.split("/")
            if len(names) == len(parts):
                breadcrumbs = [
                    Crumb(title=name, url=f"{ctx.base_url}/{'/'.join(parts[: i + 1])}")
                    for i, name in enumerate(names)
                ]
        except SourceUnavailable:
            pass

        comments: list[Comment] = []
        try:
            for page in range(1, _NOTE_PAGES + 1):
                notes = ctx.get_json(
                    f"{api}/issues/{iid}/notes",
                    {"sort": "asc", "order_by": "created_at", "per_page": 100, "page": page},
                )
                comments += [
                    Comment(
                        author=(note.get("author") or {}).get("name") or "",
                        created=note.get("created_at"),
                        body_html=_html(note.get("body")),
                    )
                    for note in notes
                    if not _hidden(note)
                ]
                if len(notes) < 100:
                    break
        except SourceUnavailable:
            pass

        related: list[Related] = []
        try:
            for other in ctx.get_json(f"{api}/issues/{iid}/links"):
                # Die Zugangsdaten sehen auch vertrauliche Issues; schon der Titel wäre zu viel.
                if other.get("confidential") or not other.get("web_url"):
                    continue
                other_state = other.get("state") or ""
                related.append(
                    Related(
                        relation=(other.get("link_type") or "relates_to").replace("_", " "),
                        title=other.get("title") or "",
                        url=other["web_url"],
                        identifier=(other.get("references") or {}).get("full")
                        or f"#{other.get('iid')}",
                        status=_STATES.get(other_state, other_state),
                    )
                )
        except SourceUnavailable:
            pass

        return WebDocument(
            title=issue.get("title") or key,
            url=issue.get("web_url") or meta.get("url"),
            kind="ticket",
            identifier=(issue.get("references") or {}).get("short") or f"#{iid}",
            facts=facts,
            breadcrumbs=breadcrumbs,
            body_html=_html(issue.get("description")),
            comments=comments,
            comments_total=len(comments),
            related=related,
            extra_css=_CSS,
        )
