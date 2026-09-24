#!/usr/bin/env python3
"""Small stdio Language Server for Doctus CALL/COPY hints (O-325).

Uses only Python's standard library. Configuration is read from DOCTUS_* env
variables so any IDE with a stdio LSP client can launch it.
"""

import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, url2pathname, urlopen


API_URL = os.environ.get("DOCTUS_API_URL", "http://localhost:8000").rstrip("/")
WEB_URL = os.environ.get("DOCTUS_WEB_URL", "http://localhost:3000").rstrip("/")
TOKEN = os.environ.get("DOCTUS_TOKEN", "")
PROJECT_ID = os.environ.get("DOCTUS_PROJECT_ID", "")
SOURCE_ID = os.environ.get("DOCTUS_SOURCE_ID", "")
VARIANT_KEY = os.environ.get("DOCTUS_VARIANT_KEY", "")
ROOT = Path(os.environ.get("DOCTUS_REPOSITORY_ROOT", os.getcwd())).resolve()

documents = {}
cache = {}
next_request_id = 1000000


def send(message):
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    sys.stdout.buffer.flush()


def receive():
    headers = {}
    while line := sys.stdin.buffer.readline():
        if line in (b"\r\n", b"\n"):
            break
        key, _, value = line.decode("ascii", errors="replace").partition(":")
        headers[key.lower()] = value.strip()
    else:
        return None
    length = int(headers.get("content-length", "0"))
    if length <= 0 or length > 2_000_000:
        return None
    return json.loads(sys.stdin.buffer.read(length))


def source_path(uri):
    parsed = urlparse(uri)
    if parsed.scheme != "file" or parsed.netloc not in ("", "localhost"):
        return None
    absolute = Path(url2pathname(parsed.path)).resolve()
    try:
        return absolute.relative_to(ROOT).as_posix()
    except ValueError:
        return None


def graph_url(path, line):
    query = urlencode({"ide_project": PROJECT_ID, "ide_source": SOURCE_ID,
                       "ide_path": path, "ide_line": line,
                       **({"ide_variant": VARIANT_KEY} if VARIANT_KEY else {})})
    return f"{WEB_URL}/?{query}"


def markdown_text(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|>-])", r"\\\1", str(value or ""))


def references(uri):
    path = source_path(uri)
    if not path or not TOKEN or not PROJECT_ID or not SOURCE_ID:
        return None, []
    cached = cache.get(path)
    if cached and time.monotonic() - cached[0] < 30:
        return path, cached[1]
    query = {"project_id": PROJECT_ID, "source_id": SOURCE_ID, "path": path}
    if VARIANT_KEY:
        query["variant_key"] = VARIANT_KEY
    request = Request(f"{API_URL}/ide/file?{urlencode(query)}",
                      headers={"Authorization": f"Bearer {TOKEN}"})
    try:
        with urlopen(request, timeout=8) as response:
            data = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            return path, []
        raise
    rows = data.get("references", [])
    cache[path] = (time.monotonic(), rows)
    return path, rows


def ref_range(uri, ref, line_fallback=False):
    line = ref.get("line")
    if not isinstance(line, int) or line < 1:
        return None
    content = documents.get(uri, "").splitlines()
    source_line = content[line - 1] if line <= len(content) else ""
    start = ref.get("start_column")
    end = ref.get("end_column")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(source_line):
        symbol = ref.get("symbol_name")
        if not symbol or source_line[start:end] == symbol:
            start = len(source_line[:start].encode("utf-16-le")) // 2
            end = len(source_line[:end].encode("utf-16-le")) // 2
            return {"start": {"line": line - 1, "character": start},
                    "end": {"line": line - 1, "character": end}}
    name = str(ref.get("symbol_name") or ref.get("name") or "")
    haystack, needle = source_line.lower(), name.lower()
    start = haystack.find(needle) if needle else -1
    if start < 0 or haystack.find(needle, start + 1) >= 0:
        if not line_fallback:
            return None
        start, name = 0, ""
    end = len(source_line[:start + len(name)].encode("utf-16-le")) // 2
    start = len(source_line[:start].encode("utf-16-le")) // 2
    return {"start": {"line": line - 1, "character": start},
            "end": {"line": line - 1, "character": end}}


def code_lenses(uri):
    path, rows = references(uri)
    if path is None:
        return []
    result = []
    for ref in rows:
        location = ref_range(uri, ref, line_fallback=True)
        if not location:
            continue
        target = ref.get("target")
        destination = f"{target['file_path']}:{target.get('start_line') or 1}" if target else ref.get("resolution", "unresolved")
        result.append({"range": location, "command": {
            "title": f"Doctus: {ref['type']} {ref['name']} → {destination}",
            "command": "doctus.openGraph",
            "arguments": [graph_url(path, ref["line"])]}})
    return result


def hover(uri, position):
    path, rows = references(uri)
    if path is None:
        return None
    for ref in rows:
        location = ref_range(uri, ref)
        if not location or position.get("line") != location["start"]["line"]:
            continue
        column = position.get("character", -1)
        if not location["start"]["character"] <= column <= location["end"]["character"]:
            continue
        target = ref.get("target")
        target_text = f"\n\nTarget: {markdown_text(target['file_path'])}:{target.get('start_line') or 1}" if target else ""
        url = graph_url(path, ref["line"])
        return {"contents": {"kind": "markdown", "value":
                f"**{markdown_text(ref['type'])} {markdown_text(ref['name'])}** · {markdown_text(ref.get('resolution', 'unresolved'))}"
                f"{target_text}\n\n[Open in Doctus graph]({url})"}, "range": location}
    return None


def handle(message):
    global next_request_id
    method = message.get("method")
    if method is None:
        return  # Response to our window/showDocument request.
    params = message.get("params") or {}
    if method == "textDocument/didOpen":
        document = params.get("textDocument", {})
        documents[document.get("uri")] = document.get("text", "")
    elif method == "textDocument/didChange":
        uri = params.get("textDocument", {}).get("uri")
        changes = params.get("contentChanges", [])
        if changes:
            documents[uri] = changes[-1].get("text", "")
    elif method == "textDocument/didClose":
        documents.pop(params.get("textDocument", {}).get("uri"), None)
    elif method == "textDocument/didSave":
        path = source_path(params.get("textDocument", {}).get("uri", ""))
        cache.pop(path, None)
    if "id" not in message:
        return
    request_id = message["id"]
    try:
        if method == "initialize":
            result = {"capabilities": {"textDocumentSync": 1, "hoverProvider": True,
                                       "codeLensProvider": {"resolveProvider": False},
                                       "executeCommandProvider": {"commands": ["doctus.openGraph"]}},
                      "serverInfo": {"name": "Doctus", "version": "0.1.0"}}
        elif method == "textDocument/codeLens":
            result = code_lenses(params["textDocument"]["uri"])
        elif method == "textDocument/hover":
            result = hover(params["textDocument"]["uri"], params["position"])
        elif method == "workspace/executeCommand":
            arguments = params.get("arguments") or []
            if params.get("command") != "doctus.openGraph" or not arguments or not str(arguments[0]).startswith(WEB_URL + "/?"):
                raise ValueError("Unknown command")
            send({"jsonrpc": "2.0", "id": next_request_id, "method": "window/showDocument",
                  "params": {"uri": arguments[0], "external": True}})
            next_request_id += 1
            result = None
        elif method == "shutdown":
            result = None
        else:
            result = None
        send({"jsonrpc": "2.0", "id": request_id, "result": result})
    except Exception as error:
        send({"jsonrpc": "2.0", "id": request_id,
              "error": {"code": -32000, "message": f"Doctus: {type(error).__name__}"}})


def main():
    while message := receive():
        if message.get("method") == "exit":
            break
        handle(message)


if __name__ == "__main__":
    main()
