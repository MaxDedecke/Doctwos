#!/usr/bin/env python3
"""Prüft die versionierten Such-Erwartungen (O-277) gegen eine laufende Doctus-Instanz über MCP.

    DOCTUS_MCP_TOKEN=dct_mcp_... python3 scripts/eval_search.py [--url http://localhost:8000/mcp]

Exit-Code 1, sobald eine Erwartung verfehlt wird. Ein Treffer zählt, wenn Qualified Name und Datei
innerhalb der ersten `top` Ergebnisse stehen; Negativfälle müssen leer bleiben.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

CASES = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "eval_search_cases.json"


class Mcp:
    def __init__(self, url: str, token: str):
        self.url = url
        self.headers = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        response, _ = self._rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "eval-search", "version": "1"}})
        self.session = response.headers.get("mcp-session-id")
        requests.post(self.url, headers=self._headers(), json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=30)

    def _headers(self):
        return {**self.headers, **({"mcp-session-id": self.session} if getattr(self, "session", None) else {})}

    def _rpc(self, method, params, request_id=1):
        response = requests.post(self.url, headers=self._headers(), json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, timeout=120)
        response.raise_for_status()
        body = response.text
        if body.startswith("event"):
            body = next(line[5:] for line in body.splitlines() if line.startswith("data:"))
        return response, json.loads(body)

    def call(self, name, arguments):
        _, payload = self._rpc("tools/call", {"name": name, "arguments": arguments}, 2)
        result = payload.get("result") or {}
        if result.get("structuredContent") is not None:
            return result["structuredContent"]
        text = next((item.get("text") for item in result.get("content", []) if item.get("text")), "")
        try:
            return json.loads(text)
        except ValueError:
            return {"error": text}


def evaluate(case, response):
    expect = case["expect"]
    if "error" in response:
        return False, f"Fehler: {str(response['error'])[:120]}"
    rows = response.get("results") or response.get("candidates") or []
    if "resolution" in expect and response.get("resolution") != expect["resolution"]:
        return False, f"resolution={response.get('resolution')!r}, erwartet {expect['resolution']!r}"
    if expect.get("empty"):
        return (not rows), f"{len(rows)} Treffer, erwartet 0" if rows else "leer"
    passage = expect.get("passage")
    if passage:
        for rank, row in enumerate(rows[: passage["top"]], start=1):
            if row.get("file_path") == passage["file"] and passage["contains"] in (row.get("content") or ""):
                return True, f"Rang {rank}"
        return False, f"Passage {passage['contains']!r} in {passage['file']} nicht in den ersten {passage['top']} Treffern"
    if "absent" in expect:
        found = [row.get("file_path") for row in rows if expect["absent"].lower() in (row.get("content") or "").lower()]
        return (not found), f"{expect['absent']!r} fälschlich belegt in {found}" if found else f"{expect['absent']!r} nirgends belegt"
    hit = expect.get("hit")
    if hit:
        for rank, row in enumerate(rows[: hit["top"]], start=1):
            location = row.get("location") or row.get("file_path") or ""
            if row.get("qualified_name") == hit["qualified_name"] and location.startswith(hit["file"]):
                return True, f"Rang {rank}"
        return False, f"{hit['qualified_name']} nicht in den ersten {hit['top']} Treffern"
    return True, "ok"


def resolve_entity(client, project_id, name):
    response = client.call("research_project", {"project_id": project_id, "query": name})
    candidates = response.get("candidates") or []
    exact = [item for item in candidates if item.get("qualified_name") == name]
    return (exact or candidates)[0]["id"] if (exact or candidates) else None


def evaluate_fact(client, project_id, fact):
    if fact["kind"] == "search":
        arguments = {"project_id": project_id, "query": fact["query"], "limit": 10}
        return evaluate(fact, client.call(fact["tool"], arguments))
    if fact["kind"] == "source_line":
        low, high = max(1, fact["line"] - 1), fact["line"] + 1
        response = client.call("explain_symbol", {"project_id": project_id, "symbol": fact["symbol"], "start_line": low, "end_line": high})
        text = (response.get("source") or {}).get("text", "") if isinstance(response, dict) else ""
        wanted = [row for row in text.splitlines() if row.startswith(f"{fact['line']}:")]
        if not wanted:
            return False, f"Zeile {fact['line']} nicht geliefert ({str(response.get('error', ''))[:80] if isinstance(response, dict) else ''})"
        return fact["contains"] in wanted[0], wanted[0].strip()[:100]
    if fact["kind"] in {"annotation", "return_expression"}:
        response = client.call("get_code_entity", {"project_id": project_id, "symbol": fact["symbol"]})
        analysis = response.get("analysis") if isinstance(response, dict) else None
        if not analysis:
            return False, f"keine Analyse ({str(response.get('error', ''))[:80] if isinstance(response, dict) else ''})"
        expect = fact["expect"]
        if fact["kind"] == "annotation":
            for item in analysis.get("annotation_details", []):
                if item["name"] == expect["annotation"] and expect["contains"] in json.dumps(item["values"]):
                    return True, item["source"][:100]
            return False, f"@{expect['annotation']} mit {expect['contains']!r} nicht belegt"
        expressions = [item["expression"] for item in analysis.get("return_expressions", [])]
        return expect["contains"] in expressions, "; ".join(expressions)[:100]
    entity_id = resolve_entity(client, project_id, fact["entity"])
    if entity_id is None:
        return False, f"Entity {fact['entity']!r} nicht aufgelöst"
    expect, arguments = fact["expect"], {
        "project_id": project_id, "entity_id": entity_id, "hops": fact["hops"], "direction": fact["direction"],
        "scope": fact["scope"], "page_size": 15,
    }
    for _ in range(8):  # Seiten über den Cursor, bis die Kante gefunden oder der Fluss erschöpft ist
        flow = client.call("get_call_flow", arguments)
        if "error" in flow:
            return False, f"Fehler: {str(flow['error'])[:100]}"
        nodes = {node["id"]: node.get("qualified_name") for node in flow.get("nodes", [])}
        for edge in flow.get("edges", []):
            if edge["type"] == expect["type"] and edge["target_name"] == expect["target_name"]:
                if "target_qualified_name" in expect and nodes.get(edge.get("target")) != expect["target_qualified_name"]:
                    continue
                if "arguments" in expect:
                    given = (edge.get("resolution_evidence") or {}).get("argument_expressions")
                    if given != expect["arguments"]:
                        return False, f"Argumente {given}"
                return edge["resolution"] == expect["resolution"], f"{edge['type']} {edge['target_name']} {edge['resolution']}"
        if not flow.get("next_cursor"):
            break
        arguments["cursor"] = flow["next_cursor"]
    return False, f"Kante {expect['type']} {expect['target_name']} nicht im Fluss"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("DOCTUS_MCP_URL", "http://localhost:8000/mcp"))
    args = parser.parse_args()
    token = os.environ.get("DOCTUS_MCP_TOKEN")
    if not token:
        sys.exit("DOCTUS_MCP_TOKEN fehlt")
    catalogue = json.loads(CASES.read_text(encoding="utf-8"))
    client = Mcp(args.url, token)
    visible = client.call("list_visible_projects", {}).get("projects", [])
    project_ids = {item["name"]: item["id"] for item in visible}
    failed = 0
    for case in catalogue["cases"]:
        name = catalogue["projects"][case["project"]]["name"]
        if name not in project_ids:
            print(f"SKIP {case['id']}: Projekt {name!r} nicht sichtbar")
            continue
        arguments = {"project_id": project_ids[name], "query": case["query"]}
        if case["tool"] == "search_code":
            arguments["limit"] = 10
        elif case["tool"] == "search_knowledge":
            arguments["limit"] = 5
        ok, detail = evaluate(case, client.call(case["tool"], arguments))
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {case['id']} [{case['kind']}] {case['query']!r}: {detail}")
    total = len(catalogue["cases"])
    for fact in catalogue.get("facts", []):
        name = catalogue["projects"][fact["project"]]["name"]
        if name not in project_ids:
            print(f"SKIP {fact['id']}: Projekt {name!r} nicht sichtbar")
            continue
        total += 1
        ok, detail = evaluate_fact(client, project_ids[name], fact)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'} {fact['id']} [{fact['kind']}] {fact.get('case', '')}: {detail}")
    print(f"{total - failed} bestanden, {failed} verfehlt")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
