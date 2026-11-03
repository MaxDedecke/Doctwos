"""GitLab instance URL and bounded, same-endpoint pagination for repository browsing."""

from urllib.parse import urlsplit
from fastapi import HTTPException


def gitlab_base(url):
    base = (url or "https://gitlab.com").rstrip("/")
    parsed = urlsplit(base)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.query
        or parsed.fragment
    ):
        raise HTTPException(status_code=400, detail="Invalid GitLab instance URL")
    return base


async def gitlab_pages(client, url, headers, **params):
    result, page = [], 1
    while True:
        response = await client.get(
            url, headers=headers, params={**params, "page": page, "per_page": 100}
        )
        response.raise_for_status()
        items = response.json()
        if not isinstance(items, list):
            raise HTTPException(status_code=502, detail="Invalid GitLab response")
        result.extend(items)
        next_page = response.headers.get("X-Next-Page")
        if next_page:
            number = int(next_page)
            if number <= page:
                raise HTTPException(status_code=502, detail="GitLab pagination did not advance")
            page = number
        elif "X-Next-Page" in response.headers or len(items) < 100:
            return result
        else:
            page += 1
        if page > 1000:
            raise HTTPException(
                status_code=502, detail="GitLab listing exceeds 1000 pages; narrow permissions"
            )
