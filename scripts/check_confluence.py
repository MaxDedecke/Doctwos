#!/usr/bin/env python3
"""Prueft eine echte Confluence-Instanz (Server, Data Center oder Cloud) mit den Abfragen des Doctus-Connectors.

Nur lesend. Zeigt, ob REST-Wurzel, Anmeldung, Spaces, Seiten (mit Vorfahren und Leseeinschraenkungen),
Blogposts, Anhaenge und Kommentare so antworten, wie der Connector es erwartet, und wie lange ein Listenabruf dauert.

Beispiel (im Parser-Image, ohne weitere Installation):
  docker run --rm -v "$PWD/scripts:/s:ro" doctus-parser-worker:latest \\
      python /s/check_confluence.py --url https://wiki.firma.local/confluence --token <PAT> --space DOCS

  --user NAME      Benutzername fuer Basic Auth (Cloud: E-Mail); ohne Angabe wird das Token als Bearer-PAT genutzt
  --ca PFAD        CA-Bundle (PEM) fuer interne Zertifikate;  --insecure  Zertifikatspruefung abschalten (nur Test)
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass

import httpx

API_ROOTS = ("/rest/api", "/wiki/rest/api")
RESTRICTION_EXPAND = "restrictions.read.restrictions.user,restrictions.read.restrictions.group,ancestors"


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def _get(client: httpx.Client, url: str, **kwargs) -> httpx.Response:
    return client.get(url, timeout=30.0, **kwargs)


def run_checks(client: httpx.Client, base_url: str, space: str | None, auth, headers) -> list[Result]:
    results: list[Result] = []
    base_url = base_url.rstrip("/")
    kw = {"auth": auth, "headers": headers}

    root = None
    statuses = []
    for candidate in API_ROOTS:
        try:
            response = _get(client, f"{base_url}{candidate}/space", params={"limit": 5}, **kw)
        except httpx.HTTPError as exc:
            statuses.append(f"{candidate}: {type(exc).__name__}: {exc}")
            continue
        statuses.append(f"{candidate}: HTTP {response.status_code}")
        if response.status_code == 200:
            root = candidate
            spaces = [item.get("key") for item in response.json().get("results", [])]
            results.append(Result("REST-Wurzel", True, f"{base_url}{root} ({'Cloud' if 'wiki' in root else 'Server/Data Center'}); Spaces (Auszug): {', '.join(map(str, spaces)) or '-'}"))
            break
    if root is None:
        results.append(Result("REST-Wurzel", False, "; ".join(statuses) + ". Pruefe URL (Kontextpfad?), Zugangsdaten und Zertifikat."))
        return results

    params = {"type": "page", "limit": 25, "expand": "body.view,version,space,ancestors"}
    if space:
        params["spaceKey"] = space
    started = time.monotonic()
    response = _get(client, f"{base_url}{root}/content", params=params, **kw)
    elapsed = time.monotonic() - started
    if response.status_code != 200:
        results.append(Result("Seiten", False, f"HTTP {response.status_code}" + (f" (Space {space} vorhanden und lesbar?)" if space else "")))
        return results
    pages = response.json().get("results", [])
    with_ancestors = sum(1 for page in pages if page.get("ancestors"))
    results.append(Result("Seiten", bool(pages), f"{len(pages)} Seiten in {elapsed:.1f}s ({with_ancestors} mit Elternseiten, Text als body.view: {sum(1 for p in pages if p.get('body', {}).get('view', {}).get('value'))})"))
    results.append(Result("Antwortzeit", elapsed < 10, f"{elapsed:.1f}s fuer 25 Seiten mit Text" + ("" if elapsed < 10 else " – langsam; Server oder Makros pruefen")))

    params = {**params, "expand": RESTRICTION_EXPAND, "limit": 100}
    response = _get(client, f"{base_url}{root}/content", params=params, **kw)
    if response.status_code == 200:
        restricted = 0
        for page in response.json().get("results", []):
            read = (page.get("restrictions") or {}).get("read") or {}
            restrictions = read.get("restrictions") or {}
            restricted += any((restrictions.get(kind) or {}).get("results") for kind in ("user", "group"))
        results.append(Result("Leseeinschraenkungen", True, f"{restricted} eingeschraenkte Seite(n) in den ersten 100 erkannt (werden standardmaessig uebersprungen, samt Unterseiten)"))
    else:
        results.append(Result("Leseeinschraenkungen", False, f"HTTP {response.status_code}: Einschraenkungen nicht abrufbar, der Connector bricht dann ab"))

    blog = _get(client, f"{base_url}{root}/content", params={"type": "blogpost", "limit": 5, **({"spaceKey": space} if space else {})}, **kw)
    results.append(Result("Blogposts", blog.status_code == 200, f"HTTP {blog.status_code}, {len(blog.json().get('results', [])) if blog.status_code == 200 else 0} im Auszug"))

    if pages:
        page_id = pages[0].get("id")
        attachments = _get(client, f"{base_url}{root}/content/{page_id}/child/attachment", params={"limit": 50}, **kw)
        results.append(Result("Anhaenge", attachments.status_code == 200, f"HTTP {attachments.status_code} (Seite {page_id})"))
        comments = _get(client, f"{base_url}{root}/content/{page_id}/child/comment", params={"limit": 5, "expand": "body.view,version"}, **kw)
        results.append(Result("Kommentare", comments.status_code == 200, f"HTTP {comments.status_code} (Seite {page_id})"))
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--user")
    parser.add_argument("--space")
    parser.add_argument("--ca")
    parser.add_argument("--insecure", action="store_true")
    args = parser.parse_args(argv)

    verify = False if args.insecure else (args.ca or True)
    auth = (args.user, args.token) if args.user else None
    headers = {} if args.user else {"Authorization": f"Bearer {args.token}"}
    try:
        with httpx.Client(verify=verify) as client:
            results = run_checks(client, args.url, args.space, auth, headers)
    except httpx.HTTPError as exc:
        print(f"[FEHLER] Verbindung: {type(exc).__name__}: {exc}")
        return 2

    for result in results:
        print(f"[{'OK' if result.ok else 'FEHLER'}] {result.name}: {result.detail}")
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
