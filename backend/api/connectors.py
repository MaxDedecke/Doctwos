"""
backend/api/connectors.py
==========================
Verbindungstest- und Repository-Browser-Endpoints für Git- und Wissensquellen-Connectoren.

Unterstützte Connector-Typen:
    Git:         "github", "bitbucket" (Cloud + Server/DC), "gitlab"
    Wissensbasis: "confluence", "jira"

Bitbucket Cloud vs. Server/Data Center:
    Cloud  — kein url-Feld; API unter api.bitbucket.org/2.0
    Server — url-Feld gesetzt (z.B. https://bitbucket.example.com);
             REST API 1.0 unter {url}/rest/api/1.0
             Auth: Basic (username+password) oder Bearer (PAT)

Alle Endpoints sind zustandslos — die Zugangsdaten kommen im Request-Body
und werden nicht persistiert (das übernimmt /knowledge-sources bzw. /repositories).

Sicherheitshinweis:
    Der Token-Validator prüft auf kyrillische Lookalike-Zeichen (U+0441 ≈ 'c'),
    da Copy-Paste-Fehler aus PDFs oder Slack dort häufig auftreten.
"""

from urllib.parse import quote_plus

import httpx
from fastapi import APIRouter, HTTPException

from api.schemas import ConnectorBranchesRequest, ConnectorReposRequest, ConnectorTestRequest

router = APIRouter(prefix="/connectors", tags=["connectors"])

_USER_AGENT = "Doctus-AI-Backend"

# Kyrillisches 'с' (U+0441) wird oft fälschlich statt lateinischem 'c' eingefügt (Copy-Paste aus PDFs)
_CYRILLIC_C = 0x0441


def _bitbucket_server_auth(username: str | None, token: str | None, base_headers: dict):
    """Returns (auth, headers) for Bitbucket Server.

    PAT (Personal Access Token) → Bearer header, no Basic Auth.
    username + password → Basic Auth tuple.
    """
    headers = dict(base_headers)
    if username:
        return (username, token), headers
    headers["Authorization"] = f"Bearer {token}"
    return None, headers


def _pick_https_clone(item: dict) -> str:
    """Picks the HTTPS clone URL from a Bitbucket API repo item (Cloud and Server share this shape)."""
    for link in item.get("links", {}).get("clone", []):
        if link.get("name") == "https" or link.get("href", "").startswith("https://"):
            return link["href"]
    clones = item.get("links", {}).get("clone", [])
    return clones[0]["href"] if clones else ""


def _default_branch_first(branches: list[str], default_branch: str | None) -> list[str]:
    """Keep the provider's default branch first while preserving API order."""
    if not default_branch:
        return branches
    if default_branch not in branches:
        return [default_branch, *branches]
    return [default_branch, *(branch for branch in branches if branch != default_branch)]


def _check_ascii(value: str | None, field_name: str) -> dict | None:
    """Gibt einen Fehler-Response zurück wenn value Nicht-ASCII-Zeichen enthält, sonst None."""
    if not value:
        return None
    if any(ord(c) > 127 for c in value):
        if any(ord(c) == _CYRILLIC_C for c in value):
            return {"success": False, "message": f"Fehler: {field_name} enthält ein kyrillisches 'с' (U+0441) statt eines normalen lateinischen 'c'. Bitte überprüfe deine Eingabe auf Kopierfehler."}
        return {"success": False, "message": f"Fehler: {field_name} enthält ungültige Nicht-ASCII-Zeichen."}
    return None


@router.post("/test")
async def test_connector(req: ConnectorTestRequest):
    for value, name in [(req.token, "Token"), (req.url, "URL"), (req.username, "Username")]:
        err = _check_ascii(value, name)
        if err:
            return err

    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if req.type == "github":
                headers["Authorization"] = f"Bearer {req.token}"
                resp = await client.get("https://api.github.com/user", headers=headers)
                if resp.status_code == 200:
                    return {"success": True, "message": "Verbindung zu GitHub erfolgreich hergestellt!"}
                return {"success": False, "message": f"GitHub-Fehler ({resp.status_code}): {resp.text}"}

            elif req.type == "bitbucket":
                if req.url:
                    # Bitbucket Server / Data Center
                    base = req.url.rstrip("/")
                    bb_auth, bb_headers = _bitbucket_server_auth(req.username, req.token, headers)
                    resp = await client.get(f"{base}/rest/api/1.0/projects?limit=1", auth=bb_auth, headers=bb_headers)
                    if resp.status_code == 200:
                        return {"success": True, "message": f"Verbindung zu Bitbucket Server ({base}) erfolgreich!"}
                    return {"success": False, "message": f"Bitbucket Server-Fehler ({resp.status_code}): {resp.text}"}
                else:
                    # Bitbucket Cloud
                    if not req.username:
                        return {"success": False, "message": "Username ist für Bitbucket Cloud erforderlich."}
                    resp = await client.get("https://api.bitbucket.org/2.0/user", auth=(req.username, req.token), headers=headers)
                    if resp.status_code == 200:
                        return {"success": True, "message": "Verbindung zu Bitbucket Cloud erfolgreich hergestellt!"}
                    return {"success": False, "message": f"Bitbucket-Fehler ({resp.status_code}): {resp.text}"}

            elif req.type == "gitlab":
                headers["Private-Token"] = req.token
                resp = await client.get("https://gitlab.com/api/v4/user", headers=headers)
                if resp.status_code == 200:
                    return {"success": True, "message": "Verbindung zu GitLab erfolgreich hergestellt!"}
                return {"success": False, "message": f"GitLab-Fehler ({resp.status_code}): {resp.text}"}

            elif req.type == "confluence":
                if not req.url:
                    return {"success": False, "message": "Server-URL ist für Confluence erforderlich."}
                if not req.username:
                    return {"success": False, "message": "E-Mail/Username ist für Confluence erforderlich."}
                base_url = req.url.rstrip("/")
                resp = await client.get(f"{base_url}/wiki/rest/api/space?limit=1", auth=(req.username, req.token), headers=headers)
                if resp.status_code == 200:
                    return {"success": True, "message": "Verbindung zu Confluence erfolgreich hergestellt!"}
                return {"success": False, "message": f"Confluence-Fehler ({resp.status_code}): {resp.text}"}

            elif req.type == "jira":
                if not req.url:
                    return {"success": False, "message": "Server-URL ist für Jira erforderlich."}
                if not req.username:
                    return {"success": False, "message": "E-Mail/Username ist für Jira erforderlich."}
                base_url = req.url.rstrip("/")
                resp = await client.get(f"{base_url}/rest/api/2/project?maxResults=1", auth=(req.username, req.token), headers=headers)
                if resp.status_code == 200:
                    return {"success": True, "message": "Verbindung zu Jira erfolgreich hergestellt!"}
                return {"success": False, "message": f"Jira-Fehler ({resp.status_code}): {resp.text}"}

            else:
                raise HTTPException(status_code=400, detail="Ungültiger Connector-Typ.")
        except HTTPException:
            raise
        except Exception as e:
            return {"success": False, "message": f"Netzwerkfehler: {str(e)}"}


@router.post("/repos")
async def get_connector_repos(req: ConnectorReposRequest):
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if req.type == "github":
                headers["Authorization"] = f"Bearer {req.token}"
                resp = await client.get("https://api.github.com/user/repos?per_page=100&sort=updated", headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"GitHub API Fehler: {resp.text}")
                return [{"name": r["name"], "full_name": r["full_name"], "clone_url": r["clone_url"]} for r in resp.json()]

            elif req.type == "bitbucket":
                if req.url:
                    # Bitbucket Server / Data Center — flat /repos endpoint returns all accessible repos
                    base = req.url.rstrip("/")
                    bb_auth, bb_headers = _bitbucket_server_auth(req.username, req.token, headers)
                    resp = await client.get(f"{base}/rest/api/1.0/repos?limit=100", auth=bb_auth, headers=bb_headers)
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=f"Bitbucket Server API Fehler: {resp.text}")
                    result = []
                    for item in resp.json().get("values", []):
                        project_key = item.get("project", {}).get("key", "")
                        slug = item.get("slug", "")
                        full_name = f"{project_key}/{slug}"
                        clone_url = _pick_https_clone(item)
                        result.append({"name": item["name"], "full_name": full_name, "clone_url": clone_url})
                    return result
                else:
                    # Bitbucket Cloud
                    if not req.username:
                        raise HTTPException(status_code=400, detail="Username ist für Bitbucket Cloud erforderlich.")
                    resp = await client.get("https://api.bitbucket.org/2.0/repositories?role=member&pagelen=100", auth=(req.username, req.token), headers=headers)
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=f"Bitbucket API Fehler: {resp.text}")
                    result = []
                    for item in resp.json().get("values", []):
                        clone_url = _pick_https_clone(item)
                        result.append({"name": item["name"], "full_name": item["full_name"], "clone_url": clone_url})
                    return result

            elif req.type == "gitlab":
                headers["Private-Token"] = req.token
                resp = await client.get("https://gitlab.com/api/v4/projects?membership=true&per_page=100", headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"GitLab API Fehler: {resp.text}")
                return [{"name": r["name"], "full_name": r["path_with_namespace"], "clone_url": r["http_url_to_repo"]} for r in resp.json()]

            else:
                raise HTTPException(status_code=400, detail="Ungültiger Connector-Typ.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Repositories: {str(e)}")


@router.post("/branches")
async def get_connector_branches(req: ConnectorBranchesRequest):
    headers = {"User-Agent": _USER_AGENT}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            if req.type == "github":
                if req.token:
                    headers["Authorization"] = f"Bearer {req.token}"
                repo_resp = await client.get(f"https://api.github.com/repos/{req.repo_name}", headers=headers)
                default_branch = repo_resp.json().get("default_branch") if repo_resp.status_code == 200 else None
                resp = await client.get(f"https://api.github.com/repos/{req.repo_name}/branches?per_page=100", headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"GitHub API Fehler: {resp.text}")
                return _default_branch_first([item["name"] for item in resp.json()], default_branch)

            elif req.type == "bitbucket":
                if req.url:
                    # Bitbucket Server — repo_name is "PROJECT_KEY/repo-slug"
                    base = req.url.rstrip("/")
                    parts = req.repo_name.split("/", 1)
                    if len(parts) != 2:
                        raise HTTPException(status_code=400, detail="repo_name muss 'PROJECT_KEY/slug' sein für Bitbucket Server.")
                    project_key, repo_slug = parts
                    bb_auth, bb_headers = _bitbucket_server_auth(req.username, req.token, headers)
                    repo_resp = await client.get(
                        f"{base}/rest/api/1.0/projects/{project_key}/repos/{repo_slug}",
                        auth=bb_auth, headers=bb_headers
                    )
                    default_branch = (
                        repo_resp.json().get("defaultBranch", {}).get("displayId")
                        if repo_resp.status_code == 200 else None
                    )
                    resp = await client.get(
                        f"{base}/rest/api/1.0/projects/{project_key}/repos/{repo_slug}/branches?limit=100",
                        auth=bb_auth, headers=bb_headers
                    )
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=f"Bitbucket Server API Fehler: {resp.text}")
                    return _default_branch_first(
                        [item["displayId"] for item in resp.json().get("values", [])], default_branch
                    )
                else:
                    # Bitbucket Cloud
                    auth = (req.username, req.token) if req.username and req.token else None
                    repo_resp = await client.get(
                        f"https://api.bitbucket.org/2.0/repositories/{req.repo_name}",
                        auth=auth, headers=headers
                    )
                    default_branch = (
                        repo_resp.json().get("mainbranch", {}).get("name")
                        if repo_resp.status_code == 200 else None
                    )
                    resp = await client.get(f"https://api.bitbucket.org/2.0/repositories/{req.repo_name}/refs/branches?pagelen=100", auth=auth, headers=headers)
                    if resp.status_code != 200:
                        raise HTTPException(status_code=resp.status_code, detail=f"Bitbucket API Fehler: {resp.text}")
                    return _default_branch_first(
                        [item["name"] for item in resp.json().get("values", [])], default_branch
                    )

            elif req.type == "gitlab":
                if req.token:
                    headers["Private-Token"] = req.token
                encoded_name = quote_plus(req.repo_name)
                resp = await client.get(f"https://gitlab.com/api/v4/projects/{encoded_name}/repository/branches?per_page=100", headers=headers)
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=f"GitLab API Fehler: {resp.text}")
                return [item["name"] for item in resp.json()]

            else:
                raise HTTPException(status_code=400, detail="Ungültiger Connector-Typ.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Fehler beim Laden der Branches: {str(e)}")
