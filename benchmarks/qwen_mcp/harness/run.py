"""Qwen-8B-MCP-Benchmark: fuehrt gepaarte Agenten-Sitzungen gegen lokales Ollama aus.

Arme (gleicher Prompt, gleiches Modell, gleiche Sampling-Parameter):
  none   Kontrollboden: keine Werkzeuge (Wissen des Modells allein)
  local  Kontrolle: lokale Dateiwerkzeuge (list_dir, grep, read_file) auf dem gepinnten Checkout
  mcp    Behandlung: die Doctus-MCP-Werkzeuge (Streamable HTTP, Bearer-Token)

Aufruf (im Backend-Image, damit `mcp` und `httpx` vorhanden sind):
  docker run --rm --network host --env-file .env.local -v $PWD:/bench -w /bench \
      --entrypoint python doctus-backend-api:latest harness/run.py --reps 3
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OLLAMA = os.getenv("OLLAMA_URL", "http://localhost:11434")
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
MODEL = os.getenv("BENCH_MODEL", "qwen3:8b")
OPTIONS = {"temperature": 0.3, "top_p": 0.9, "num_ctx": int(os.getenv("BENCH_NUM_CTX", "8192")), "num_predict": int(os.getenv("BENCH_NUM_PREDICT", "1500"))}
THINK = os.getenv("BENCH_THINK", "0") == "1"
EXCLUDE_TOOLS = {t for t in os.getenv("BENCH_EXCLUDE_TOOLS", "").split(",") if t}
PREFETCH = os.getenv("BENCH_PREFETCH", "0") == "1"  # Server fuehrt den Evidenz-Pack als ersten Werkzeugschritt selbst aus (wie der Chat)
MAX_TURNS = 10
TOOL_OUTPUT_CAP = 6000  # Zeichen; fuer alle Arme gleich
CONTEXT_SOFT_LIMIT = OPTIONS["num_ctx"] - 1700

SYSTEM_BASE = (
    "Du bist ein Assistent fuer die Analyse von Quellcode. Beantworte die Frage praezise auf Deutsch. "
    "Nenne konkrete Datei- und Zeilenbelege (Datei:Zeile), Programm-, Methoden- und Feldnamen aus dem Code. "
    "Erfinde nichts: Was du nicht belegen kannst, kennzeichnest du ausdruecklich als unbelegt. "
    "Die Antwort ist eine zusammenhaengende Erklaerung, keine Rueckfrage."
)
ARM_HINTS = {
    "none": "Dir stehen keine Werkzeuge zur Verfuegung. Antworte aus deinem Wissen.",
    "local": (
        "Du hast Werkzeuge fuer den lokalen Quellcode-Checkout (list_dir, grep, read_file). "
        "Pfade sind relativ zum Wurzelverzeichnis des Repositorys; es enthaelt: {root_listing}. "
        "Lies den relevanten Code, bevor du antwortest."
    ),
    "mcp": (
        "Du hast die Doctus-MCP-Werkzeuge fuer ein indexiertes Projekt (Suche, Entitaeten, Call-Flow, Datenzugriff). "
        "Die project_id der Frage ist {project_id}. Nutze die Werkzeuge, bevor du antwortest."
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(tasks_file: str = "tasks.json") -> dict:
    return {"tasks_sha256": sha256(ROOT / tasks_file), "protocol_sha256": sha256(ROOT / "PROTOCOL.md")}


def environment() -> dict:
    def sh(cmd: str) -> str:
        try:
            return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20).stdout.strip()
        except Exception:
            return ""

    tags = httpx.get(f"{OLLAMA}/api/tags", timeout=20).json().get("models", [])
    digests = {m["name"]: m.get("digest", "")[:12] for m in tags}
    return {
        "model": MODEL,
        "model_digests": digests,
        "options": OPTIONS,
        "max_turns": MAX_TURNS,
        "tool_output_cap": TOOL_OUTPUT_CAP,
        "think": THINK,
        "excluded_tools": sorted(EXCLUDE_TOOLS),
        "mcp_url": MCP_URL,
        "ollama_version": httpx.get(f"{OLLAMA}/api/version", timeout=20).json().get("version"),
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


# --------------------------------------------------------------------------- lokale Werkzeuge

LOCAL_TOOLS = [
    {"type": "function", "function": {
        "name": "list_dir", "description": "Listet Dateien und Unterverzeichnisse eines Verzeichnisses.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relativer Pfad, leer = Wurzel"}}}}},
    {"type": "function", "function": {
        "name": "grep", "description": "Sucht ein Regex-Muster (ohne Beachtung der Gross-/Kleinschreibung) in Dateien unterhalb eines Pfads. Liefert Datei:Zeile:Text.",
        "parameters": {"type": "object", "properties": {
            "pattern": {"type": "string"}, "path": {"type": "string", "description": "Relativer Pfad, leer = Wurzel"},
            "max_results": {"type": "integer", "description": "Standard 40"}}, "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Liest Zeilen einer Datei (hoechstens 250 Zeilen pro Aufruf), mit Zeilennummern.",
        "parameters": {"type": "object", "properties": {
            "path": {"type": "string"}, "start_line": {"type": "integer", "description": "Standard 1"},
            "end_line": {"type": "integer", "description": "Standard start_line+199"}}, "required": ["path"]}}},
]


class LocalTools:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _safe(self, rel: str) -> Path:
        p = (self.root / (rel or "").lstrip("/")).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValueError("Pfad ausserhalb des Repositorys")
        return p

    def call(self, name: str, args: dict) -> str:
        if name == "list_dir":
            p = self._safe(args.get("path", ""))
            if not p.is_dir():
                raise ValueError("kein Verzeichnis")
            return "\n".join(sorted(f"{c.name}{'/' if c.is_dir() else ''}" for c in p.iterdir()))
        if name == "grep":
            p = self._safe(args.get("path", ""))
            if not p.exists():
                raise ValueError(f"Pfad existiert nicht: {args.get('path', '')}")
            rx = re.compile(args["pattern"], re.IGNORECASE)
            limit = int(args.get("max_results") or 40)
            out = []
            files = [p] if p.is_file() else (f for f in sorted(p.rglob("*")) if f.is_file())
            for f in files:
                try:
                    for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                        if rx.search(line):
                            out.append(f"{f.relative_to(self.root)}:{i}:{line.strip()[:200]}")
                            if len(out) >= limit:
                                return "\n".join(out) + f"\n[... auf {limit} Treffer begrenzt]"
                except OSError:
                    continue
            return "\n".join(out) or "(keine Treffer)"
        if name == "read_file":
            p = self._safe(args["path"])
            if not p.is_file():
                raise ValueError("keine Datei")
            start = max(1, int(args.get("start_line") or 1))
            end = min(int(args.get("end_line") or start + 199), start + 249)
            lines = p.read_text(errors="replace").splitlines()
            return "\n".join(f"{i}: {lines[i - 1]}" for i in range(start, min(end, len(lines)) + 1)) or "(leer)"
        raise ValueError(f"unbekanntes Werkzeug {name}")


# --------------------------------------------------------------------------- MCP

class McpTools:
    def __init__(self):
        self.session = None
        self._stack = None
        self.tools: list[dict] = []

    async def __aenter__(self):
        from contextlib import AsyncExitStack
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        self._stack = AsyncExitStack()
        r, w, _ = await self._stack.enter_async_context(
            streamablehttp_client(MCP_URL, headers={"Authorization": "Bearer " + os.environ["MCP_TOKEN"]})
        )
        self.session = await self._stack.enter_async_context(ClientSession(r, w))
        await self.session.initialize()
        listed = await self.session.list_tools()
        self.tools = [
            {"type": "function", "function": {"name": t.name, "description": t.description or "", "parameters": t.inputSchema}}
            for t in listed.tools if t.name not in EXCLUDE_TOOLS
        ]
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def call(self, name: str, args: dict) -> tuple[str, bool]:
        res = await self.session.call_tool(name, args)
        text = "\n".join(getattr(c, "text", "") for c in res.content)
        return text, bool(res.isError)


def is_empty_result(text: str) -> bool:
    t = text.strip()
    if not t or t == "(keine Treffer)":
        return True
    try:
        data = json.loads(t)
    except ValueError:
        return False
    if isinstance(data, dict):
        for key in ("results", "entities", "nodes", "edges", "items", "chunks"):
            if key in data and isinstance(data[key], list):
                return len(data[key]) == 0 and not data.get("candidates")
    return False


# --------------------------------------------------------------------------- Sitzung

async def ollama_chat(client: httpx.AsyncClient, messages: list[dict], tools: list[dict] | None, seed: int) -> dict:
    body = {"model": MODEL, "messages": messages, "stream": False, "think": THINK,
            "options": {**OPTIONS, "seed": seed}, "keep_alive": -1}
    if tools:
        body["tools"] = tools
    r = await client.post(f"{OLLAMA}/api/chat", json=body)
    r.raise_for_status()
    return r.json()


async def run_session(client, task: dict, arm: str, rep: int, project: dict, mcp: McpTools | None) -> dict:
    seed = 1000 + rep
    root = ROOT / project["corpus"]
    root_listing = ", ".join(sorted(f"{c.name}{'/' if c.is_dir() else ''}" for c in root.iterdir()))
    system = SYSTEM_BASE + " " + ARM_HINTS[arm].format(project_id=project["project_id"], root_listing=root_listing)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": task["prompt"]}]
    local = LocalTools(ROOT / project["corpus"]) if arm == "local" else None
    tools = LOCAL_TOOLS if arm == "local" else (mcp.tools if arm == "mcp" else None)

    rec = {"task": task["id"], "arm": arm, "rep": rep, "seed": seed, "status": "ok", "turns": 0,
           "prompt_tokens": 0, "completion_tokens": 0, "llm_s": 0.0, "tool_s": 0.0,
           "tool_calls": [], "tool_output_chars": 0, "forced_final": False, "answer": "", "retries": 0}
    t0 = time.monotonic()
    last_prompt_tokens = 0
    try:
        if PREFETCH and arm == "mcp":
            args = {"project_id": project["project_id"], "question": task["prompt"], "max_chars": 5000}
            ts = time.monotonic()
            text, error = await mcp.call("answer_context", args)
            dt = time.monotonic() - ts
            raw_len = len(text)
            if raw_len > TOOL_OUTPUT_CAP:
                text = text[:TOOL_OUTPUT_CAP] + "\n[... Ausgabe gekuerzt]"
            rec["tool_s"] += dt
            rec["tool_output_chars"] += len(text)
            rec["tool_calls"].append({"name": "answer_context", "args": args, "chars": raw_len, "error": error,
                                      "empty": (not error) and is_empty_result(text), "truncated": raw_len > TOOL_OUTPUT_CAP,
                                      "s": round(dt, 3), "prefetch": True})
            messages.append({"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "answer_context", "arguments": args}}]})
            messages.append({"role": "tool", "tool_name": "answer_context", "content": text})
        for turn in range(MAX_TURNS + 1):
            force = turn == MAX_TURNS or last_prompt_tokens >= CONTEXT_SOFT_LIMIT
            if force and tools:
                rec["forced_final"] = True
                messages.append({"role": "user", "content": "Antworte jetzt mit dem bisher Gesammelten. Keine weiteren Werkzeugaufrufe."})
            resp = await ollama_chat(client, messages, None if force else tools, rec["seed"])
            rec["turns"] += 1
            rec["prompt_tokens"] += resp.get("prompt_eval_count", 0)
            rec["completion_tokens"] += resp.get("eval_count", 0)
            rec["llm_s"] += resp.get("total_duration", 0) / 1e9
            last_prompt_tokens = resp.get("prompt_eval_count", 0) + resp.get("eval_count", 0)
            msg = resp["message"]
            msg.pop("thinking", None)
            calls = msg.get("tool_calls") or []
            # Ollama verwirft Werkzeugaufrufe mit ungueltigem JSON (z. B. \' im Text) ohne Fehlermeldung und liefert dann
            # eine leere Nachricht. Ein Agent-Client wiederholt in diesem Fall mit einem Hinweis.
            if tools and not force and not calls and not msg.get("content", "").strip() and resp.get("eval_count", 0) > 20 and rec.get("retries", 0) < 2:
                rec["retries"] = rec.get("retries", 0) + 1
                messages.append({"role": "user", "content": "Dein letzter Werkzeugaufruf war kein gueltiges JSON und wurde verworfen. Rufe das Werkzeug erneut auf, mit kurzen Argumenten, ohne Anfuehrungszeichen im Text."})
                continue
            if not calls or force:
                rec["answer"] = re.sub(r"<think>.*?</think>", "", msg.get("content", ""), flags=re.S).strip()
                break
            messages.append(msg)
            for call in calls:
                name = call["function"]["name"]
                args = call["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                ts = time.monotonic()
                error = False
                try:
                    if arm == "mcp":
                        text, error = await mcp.call(name, args)
                    else:
                        text = local.call(name, args)
                except Exception as exc:  # Werkzeugfehler gehen an das Modell zurueck
                    text, error = f"Fehler: {type(exc).__name__}: {exc}", True
                dt = time.monotonic() - ts
                rec["tool_s"] += dt
                raw_len = len(text)
                truncated = raw_len > TOOL_OUTPUT_CAP
                if truncated:
                    text = text[:TOOL_OUTPUT_CAP] + "\n[... Ausgabe gekuerzt]"
                rec["tool_output_chars"] += len(text)
                rec["tool_calls"].append({"name": name, "args": args, "chars": raw_len, "error": error,
                                          "empty": (not error) and is_empty_result(text), "truncated": truncated,
                                          "s": round(dt, 3)})
                messages.append({"role": "tool", "tool_name": name, "content": text})
        else:
            rec["status"] = "no_answer"
    except Exception as exc:
        rec["status"] = f"error:{type(exc).__name__}:{exc}"[:200]
    rec["wall_s"] = round(time.monotonic() - t0, 2)
    rec["llm_s"] = round(rec["llm_s"], 2)
    rec["tool_s"] = round(rec["tool_s"], 2)
    if rec["status"] == "ok" and not rec["answer"]:
        rec["status"] = "empty_answer"
    return rec


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--arms", default="none,local,mcp")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="Einzelsitzung TASK:ARM:REP (Wiederholung nach Infrastrukturfehler)")
    ap.add_argument("--tasks-file", default="tasks.json", help="Aufgabendatei (Standard: tasks.json)")
    ap.add_argument("--lock", default="", help="JSON-Festlegung (manifest_chN.json) statt des Standard-Locks")
    ap.add_argument("--freeze", action="store_true", help="schreibt manifest.lock und beendet")
    ap.add_argument("--pilot", action="store_true", help="Ergebnisse als Pilot kennzeichnen (nicht fuer die Auswertung)")
    args = ap.parse_args()

    if args.freeze:
        (ROOT / "manifest.lock").write_text(json.dumps(manifest(), indent=2) + "\n")
        print("manifest.lock geschrieben:", manifest())
        return
    if args.lock:
        frozen = json.loads((ROOT / args.lock).read_text())
        if frozen.get("tasks_sha256") != sha256(ROOT / args.tasks_file):
            raise SystemExit("Aufgabendatei passt nicht zur Festlegung " + args.lock)
    lock = ROOT / "manifest.lock"
    if not args.lock and not args.pilot and (not lock.exists() or json.loads(lock.read_text()) != manifest(args.tasks_file)):
        raise SystemExit("manifest.lock fehlt oder passt nicht zu tasks.json/PROTOCOL.md -- erst einfrieren (--freeze).")

    spec = json.loads((ROOT / args.tasks_file).read_text())
    tasks = [t for t in spec["tasks"] if not args.tasks or t["id"] in args.tasks.split(",")]
    arms = args.arms.split(",")
    run_id = args.out or time.strftime("run_%Y%m%d_%H%M%S") + ("_pilot" if args.pilot else "")
    out_path = ROOT / "results" / "raw" / f"{run_id}.jsonl"
    env = environment()
    out_path.write_text(json.dumps({"_meta": {**env, **manifest(args.tasks_file), "run_id": run_id, "pilot": args.pilot}}) + "\n")

    rng = random.Random(20261002)
    plan = []
    for rep in range(1, args.reps + 1):
        for task in tasks:
            order = arms[:]
            rng.shuffle(order)  # Reihenfolge je Block zufaellig gegen Drift (Waerme, Cache)
            plan += [(task, arm, rep) for arm in order]

    if args.only:
        t_id, o_arm, o_rep = args.only.split(":")
        plan = [(next(t for t in spec["tasks"] if t["id"] == t_id), o_arm, int(o_rep))]

    async with httpx.AsyncClient(timeout=httpx.Timeout(900)) as client:
        mcp = McpTools() if "mcp" in arms else None
        if mcp:
            await mcp.__aenter__()
        try:
            # Aufwaermlauf (verworfen): Modelle laden, Verbindungen oeffnen
            await ollama_chat(client, [{"role": "user", "content": "Hallo"}], None, 1)
            for i, (task, arm, rep) in enumerate(plan, 1):
                project = spec["projects"][task["project"]]
                rec = await run_session(client, task, arm, rep, project, mcp)
                with out_path.open("a") as fh:
                    fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                print(f"[{i}/{len(plan)}] {task['id']:<16} {arm:<5} rep{rep} {rec['status']:<10} "
                      f"{rec['wall_s']:>6.1f}s turns={rec['turns']} tools={len(rec['tool_calls'])} "
                      f"tok={rec['prompt_tokens']}+{rec['completion_tokens']}", flush=True)
        finally:
            if mcp:
                await mcp.__aexit__(None, None, None)
    print("fertig:", out_path)


if __name__ == "__main__":
    asyncio.run(main())
