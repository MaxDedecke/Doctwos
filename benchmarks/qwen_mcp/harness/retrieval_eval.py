"""Modellfreie Messung des MCP-Auffindens (Kapitel 9, Stufe 2).

Spielt die Werkzeugaufrufe nach, die das Modell in den Läufen tatsächlich gestellt hat (`search_code`,
`search_knowledge`, `answer_context`), gegen den laufenden Doctus-Server und prüft, ob das Ergebnis die
erwartete Datei bzw. Einheit der Aufgabe enthält. Dazu wird jede Aufgabe als Frage an `answer_context`
gestellt (ohne Symbole), wie es ein Agent tut, der kein Symbol kennt.

Aufruf (Token in .env.local):
  set -a; . ./.env.local; set +a
  python3 harness/retrieval_eval.py --split dev|control|holdout|all [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")


class Mcp:
    def __init__(self) -> None:
        r = self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                   "clientInfo": {"name": "retrieval-eval", "version": "1"}}})
        self.sid = r.headers.get("Mcp-Session-Id")
        r.read()
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}).read()

    def _post(self, body: dict):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                   "Authorization": "Bearer " + os.environ["MCP_TOKEN"]}
        if getattr(self, "sid", None):
            headers["Mcp-Session-Id"] = self.sid
        return urllib.request.urlopen(urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers), timeout=180)

    def call(self, tool: str, args: dict) -> str:
        body = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}}).read().decode()
        text = body[body.index("{", body.index("data:")):] if "data:" in body else body
        result = json.loads(text)["result"]
        return "\n".join(c.get("text", "") for c in result.get("content", []))


def load_splits() -> dict:
    return json.loads((ROOT / "retrieval_expect.json").read_text())


def recorded_calls(raw_files: list[Path]) -> dict[str, set[tuple[str, str]]]:
    """Aufgabe -> {(Werkzeug, Argumente als JSON)}, nur die Suchwerkzeuge des MCP-Arms."""
    out: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for path in raw_files:
        for line in path.read_text().splitlines()[1:]:
            r = json.loads(line)
            if r["arm"] != "mcp":
                continue
            for c in r["tool_calls"]:
                if c["name"] in {"search_code", "search_knowledge", "answer_context"} and not c.get("prefetch"):
                    out[r["task"]].add((c["name"], json.dumps(c["args"], sort_keys=True, ensure_ascii=False)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["dev", "control", "holdout", "all"])
    ap.add_argument("--tasks-file", action="append", default=[])
    ap.add_argument("--raw", action="append", default=[])
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    expect = load_splits()
    tasks: dict[str, dict] = {}
    for name in args.tasks_file or ["tasks_team.json"]:
        spec = json.loads((ROOT / name).read_text())
        for t in spec["tasks"]:
            tasks[t["id"]] = {**t, "project_id": spec["projects"][t["project"]]["project_id"]}
    wanted = [tid for tid, e in expect["tasks"].items() if args.split == "all" or e["split"] == args.split]
    raw = [ROOT / p for p in (args.raw or ["results/raw/ch9_qwen8b_plain.jsonl", "results/raw/ch9_pod_qwen3-8b-q4_32k.jsonl"])]
    recorded = recorded_calls([p for p in raw if p.exists()])
    mcp = Mcp()

    rows = []
    for tid in wanted:
        task, want = tasks[tid], re.compile(expect["tasks"][tid]["expect"], re.IGNORECASE)
        pid = task["project_id"]
        # 1) Frage ohne Symbol an answer_context (wie ein Agent ohne Namenskenntnis)
        text = mcp.call("answer_context", {"project_id": pid, "question": task["prompt"], "max_chars": 8000})
        rows.append({"task": tid, "split": expect["tasks"][tid]["split"], "tool": "answer_context(Frage)", "hit": bool(want.search(text)), "chars": len(text)})
        # 2) die Aufrufe, die das Modell tatsächlich gestellt hat
        for tool, raw_args in sorted(recorded.get(tid, ())):
            a = json.loads(raw_args)
            a["project_id"] = pid
            try:
                text = mcp.call(tool, a)
            except Exception as exc:  # Werkzeugfehler zählen als Fehlschlag
                text = f"FEHLER {exc}"
            rows.append({"task": tid, "split": expect["tasks"][tid]["split"], "tool": tool, "hit": bool(want.search(text)), "chars": len(text), "args": raw_args[:120]})

    print(f"{'Werkzeug':<24}{'Aufrufe':>8}{'Treffer':>9}{'Quote':>7}")
    for tool in ("answer_context(Frage)", "search_code", "search_knowledge", "answer_context"):
        x = [r for r in rows if r["tool"] == tool]
        if x:
            print(f"{tool:<24}{len(x):>8}{sum(r['hit'] for r in x):>9}{sum(r['hit'] for r in x) / len(x):>7.0%}")
    print("\nJe Aufgabe (Treffer/Aufrufe): Frage→answer_context | search_code | search_knowledge")
    for tid in wanted:
        def cell(tool):
            x = [r for r in rows if r["task"] == tid and r["tool"] == tool]
            return f"{sum(r['hit'] for r in x)}/{len(x)}" if x else "-"
        print(f"  {tid:<18} [{expect['tasks'][tid]['split']:<7}] {cell('answer_context(Frage)'):>4} | {cell('search_code'):>5} | {cell('search_knowledge'):>5}")
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
