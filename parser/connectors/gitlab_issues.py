"""Read-only GitLab project issues and human comments, including full resync/deletion handling."""

from urllib.parse import quote, urlsplit

import httpx

from connectors.base import BaseConnector, Document
from connectors.http_retry import request_with_retry
from db import SessionLocal
from doctus_models.database import DocumentChunk


class GitLabIssuesConnector(BaseConnector):
    async def _pages(self, client, path, **params):
        page = 1
        while True:
            response = await request_with_retry(
                client,
                "GET",
                f"{self._base}/api/v4{path}",
                headers_fn=lambda: {"PRIVATE-TOKEN": self.source.token},
                params={**params, "page": page, "per_page": 100},
                timeout=30.0,
                log=self._log,
            )
            items = response.json()
            if not isinstance(items, list):
                raise ValueError("GitLab returned an invalid paginated response")
            for item in items:
                yield item
            next_page = response.headers.get("X-Next-Page")
            if next_page:
                number = int(next_page)
                if number <= page:
                    raise ValueError("GitLab pagination did not advance")
                page = number
            elif "X-Next-Page" in response.headers or len(items) < 100:
                break
            else:
                page += 1

    async def fetch_documents(self):
        self._base = (self.source.url or "").rstrip("/")
        parsed = urlsplit(self._base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("GitLab requires an HTTP(S) instance URL without credentials/query")
        projects = self._parse_spaces()
        if not projects or any(str(p).upper() == "ALL" for p in projects):
            raise ValueError("Select explicit GitLab project IDs or namespace/project paths")
        seen = set()
        async with httpx.AsyncClient(verify=self._http_verify(), follow_redirects=False) as client:
            for project in projects:
                path = f"/projects/{quote(str(project), safe='')}/issues"
                async for issue in self._pages(
                    client, path, scope="all", state="all", order_by="created_at", sort="asc"
                ):
                    # Source credentials may see more than the Doctwos project members.
                    if issue.get("confidential"):
                        continue
                    project_id, iid = int(issue["project_id"]), int(issue["iid"])
                    key = f"{project_id}/issues/{iid}"
                    if key in seen:
                        continue
                    notes = []
                    async for note in self._pages(
                        client,
                        f"/projects/{project_id}/issues/{iid}/notes",
                        sort="asc",
                        order_by="created_at",
                    ):
                        if note.get("system") or note.get("internal") or note.get("confidential"):
                            continue
                        author = (note.get("author") or {}).get("name", "Unknown")
                        notes.append(
                            f"Comment #{note['id']} by {author} ({note.get('created_at', '')}):\n{note.get('body') or ''}"
                        )
                    seen.add(key)
                    title = issue.get("title") or ""
                    content = (
                        f"GitLab Issue #{iid}: {title}\nState: {issue.get('state', '')}\n"
                        f"Labels: {', '.join(issue.get('labels') or [])}\n\n"
                        f"{issue.get('description') or ''}\n\n" + "\n\n".join(notes)
                    )
                    yield Document(
                        title=f"#{iid}: {title}",
                        content=content,
                        url=issue.get("web_url"),
                        source_type="GitLabIssues",
                        storage_key=key,
                        extra_meta={
                            "project_id": project_id,
                            "issue_iid": iid,
                            "state": issue.get("state"),
                            "labels": issue.get("labels") or [],
                            "updated_at": issue.get("updated_at"),
                            "comment_count": len(notes),
                        },
                    )
        # Full enumeration (including notes) must finish before removing stale or newly confidential entries.
        self._prune(seen)

    def _prune(self, seen):
        with SessionLocal() as db:
            known = {
                key
                for (key,) in db.query(DocumentChunk.file_path)
                .filter(DocumentChunk.source_id == self.source_id)
                .distinct()
            }
            stale = sorted(known - seen)
            for offset in range(0, len(stale), 500):
                db.query(DocumentChunk).filter(
                    DocumentChunk.source_id == self.source_id,
                    DocumentChunk.file_path.in_(stale[offset : offset + 500]),
                ).delete(synchronize_session=False)
            db.commit()
            if stale:
                self.has_changes = True
