"""Kapitel 2: gleiche Sitzungen wie run.py, aber mit der Codex CLI (gpt-6-luna, Reasoning medium).

Schreibt dasselbe JSONL-Format wie run.py, damit analyze.py/report_data.py unveraendert funktionieren.
Aufruf (auf dem Host, nicht im Container):
  set -a; . ./.env.local; set +a; python3 harness/run_codex.py --reps 5 --out codex_run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEX_HOME = Path.home() / ".codex_bench"
CORPUS = CODEX_HOME / "corpus"  # neutrale Kopie ausserhalb des Repositorys
MODEL = "gpt-6-luna"
EFFORT = "medium"
SESSION_TIMEOUT = 600
MCP_URL = os.getenv("MCP_URL", "http://localhost:8000/mcp")
LEAK_RX = re.compile(r"benchmarks|Doctwos|tasks\.json|ground_truth|\.env|/home/|/mnt/|\.\./|/tmp/claude", re.I)

SYSTEM_BASE = (
    "Du bist ein Assistent fuer die Analyse von Quellcode. Beantworte die Frage praezise auf Deutsch. "
    "Nenne konkrete Datei- und Zeilenbelege (Datei:Zeile), Programm-, Methoden- und Feldnamen aus dem Code. "
    "Erfinde nichts: Was du nicht belegen kannst, kennzeichnest du ausdruecklich als unbelegt. "
    "Die Antwort ist eine zusammenhaengende Erklaerung, keine Rueckfrage."
)
ARM_HINTS = {
    "none": "Dir stehen keine Werkzeuge zur Verfuegung. Antworte aus deinem Wissen.",
    "local": (
        "Du hast Shell-Zugriff (nur lesend) im Wurzelverzeichnis des Quellcode-Checkouts; es enthaelt: {root_listing}. "
        "Lies den relevanten Code, bevor du antwortest."
    ),
    "mcp": (
        "Du hast die Doctus-MCP-Werkzeuge fuer ein indexiertes Projekt (Suche, Entitaeten, Call-Flow, Datenzugriff). "
        "Die project_id der Frage ist {project_id}. Nutze die Werkzeuge, bevor du antwortest."
    ),
}
COMMON = [
    "codex", "exec", "-m", MODEL, "-c", f'model_reasoning_effort="{EFFORT}"', "-c", 'web_search="disabled"',
    "--skip-git-repo-check", "--ephemeral", "--json", "-s", "read-only",
] + [x for f in ("apps", "plugins", "browser_use", "computer_use", "image_generation", "memories", "goals",
                 "skill_search", "tool_suggest") for x in ("--disable", f)]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def manifest(tasks_file: str = "tasks.json") -> dict:
    return {"tasks_sha256": sha256(ROOT / tasks_file), "protocol_sha256": sha256(ROOT / "PROTOCOL_CH2.md")}


def is_empty_result(text: str) -> bool:
    t = text.strip()
    if not t:
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


def parse_events(lines: list[str]) -> dict:
    rec = {"tool_calls": [], "tool_output_chars": 0, "answer": "", "prompt_tokens": 0, "completion_tokens": 0,
           "cached_tokens": 0, "reasoning_tokens": 0, "turns": 1, "leak_flag": False, "leak_cmds": [], "error": None,
           "agent_messages": 0}
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        t, it = d.get("type"), d.get("item", {})
        if t == "turn.completed":
            u = d.get("usage", {})
            rec["prompt_tokens"] += u.get("input_tokens", 0)
            rec["completion_tokens"] += u.get("output_tokens", 0)
            rec["cached_tokens"] += u.get("cached_input_tokens", 0)
            rec["reasoning_tokens"] += u.get("reasoning_output_tokens", 0)
        elif t in ("error", "turn.failed"):
            rec["error"] = (d.get("message") or json.dumps(d.get("error")))[:300]
        elif t == "item.completed" and it.get("type") == "agent_message":
            rec["answer"] = it.get("text", "")
            rec["agent_messages"] += 1
        elif t == "item.completed" and it.get("type") == "mcp_tool_call":
            res = it.get("result") or {}
            text = "\n".join(c.get("text", "") for c in res.get("content", []) if isinstance(c, dict))
            err = bool(it.get("error")) or it.get("status") == "failed" or bool(res.get("is_error") or res.get("isError"))
            rec["tool_calls"].append({"name": it.get("tool"), "args": it.get("arguments"), "chars": len(text), "error": err,
                                      "empty": (not err) and is_empty_result(text), "truncated": False, "s": 0})
            rec["tool_output_chars"] += len(text)
        elif t == "item.completed" and it.get("type") == "command_execution":
            out = it.get("aggregated_output") or ""
            code = it.get("exit_code")
            cmd = it.get("command", "")
            empty = (code == 1 and not out.strip()) or (code == 0 and not out.strip())
            rec["tool_calls"].append({"name": "shell", "args": {"command": cmd}, "chars": len(out),
                                      "error": code not in (0, 1, None), "empty": empty, "truncated": False, "s": 0})
            rec["tool_output_chars"] += len(out)
            if LEAK_RX.search(cmd.replace(str(CORPUS), "")):
                rec["leak_flag"] = True
                rec["leak_cmds"].append(cmd[:200])
    rec["turns"] = 1 + len(rec["tool_calls"])
    return rec


def run_session(task: dict, arm: str, rep: int, project: dict, empty_dir: Path) -> dict:
    corpus = CORPUS / project["corpus"].split("/")[-1]
    root_listing = ", ".join(sorted(f"{c.name}{'/' if c.is_dir() else ''}" for c in corpus.iterdir()))
    hint = ARM_HINTS[arm].format(project_id=project["project_id"], root_listing=root_listing)
    prompt = f"{SYSTEM_BASE} {hint}\n\n{task['prompt']}"
    cmd = list(COMMON)
    cwd = empty_dir
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME)}
    if arm == "local":
        cwd = corpus
    else:
        cmd += ["--disable", "shell_tool", "--disable", "unified_exec"]
    if arm == "mcp":
        cmd += ["-c", f'mcp_servers.doctus.url="{MCP_URL}"', "-c", 'mcp_servers.doctus.bearer_token_env_var="MCP_TOKEN"']
    else:
        env.pop("MCP_TOKEN", None)
    cmd.append(prompt)
    t0 = time.monotonic()
    status = "ok"
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=SESSION_TIMEOUT, stdin=subprocess.DEVNULL)
        lines = p.stdout.splitlines()
        if p.returncode != 0 and not lines:
            status = f"error:exit{p.returncode}:{p.stderr.strip()[-160:]}"
    except subprocess.TimeoutExpired as exc:
        lines = (exc.stdout or b"").decode(errors="replace").splitlines() if isinstance(exc.stdout, bytes) else (exc.stdout or "").splitlines()
        status = "timeout"
    wall = round(time.monotonic() - t0, 2)
    ev = parse_events(lines)
    if status == "ok" and ev["error"] and not ev["answer"]:
        status = f"error:{ev['error'][:160]}"
    if status == "ok" and not ev["answer"]:
        status = "empty_answer"
    return {"task": task["id"], "arm": arm, "rep": rep, "seed": None, "status": status, "turns": ev["turns"],
            "prompt_tokens": ev["prompt_tokens"], "completion_tokens": ev["completion_tokens"], "llm_s": 0.0, "tool_s": 0.0,
            "tool_calls": ev["tool_calls"], "tool_output_chars": ev["tool_output_chars"], "forced_final": False,
            "answer": ev["answer"].strip(), "wall_s": wall, "cached_tokens": ev["cached_tokens"],
            "reasoning_tokens": ev["reasoning_tokens"], "leak_flag": ev["leak_flag"], "leak_cmds": ev["leak_cmds"]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--arms", default="none,local,mcp")
    ap.add_argument("--tasks", default="")
    ap.add_argument("--out", default="codex_run")
    ap.add_argument("--only", default="")
    ap.add_argument("--tasks-file", default="tasks.json", help="Aufgabendatei (Standard: tasks.json)")
    ap.add_argument("--lock", default="", help="JSON-Festlegung (manifest_chN.json) statt des Standard-Locks")
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--pilot", action="store_true")
    args = ap.parse_args()
    if args.freeze:
        (ROOT / "manifest_ch2.lock").write_text(json.dumps(manifest(), indent=2) + "\n")
        print("manifest_ch2.lock geschrieben:", manifest())
        return
    if args.lock:
        frozen = json.loads((ROOT / args.lock).read_text())
        if frozen.get("tasks_sha256") != sha256(ROOT / args.tasks_file):
            raise SystemExit("Aufgabendatei passt nicht zur Festlegung " + args.lock)
    lock = ROOT / "manifest_ch2.lock"
    if not args.lock and not args.pilot and (not lock.exists() or json.loads(lock.read_text()) != manifest(args.tasks_file)):
        raise SystemExit("manifest_ch2.lock fehlt oder passt nicht -- erst einfrieren (--freeze).")

    spec = json.loads((ROOT / args.tasks_file).read_text())
    tasks = [t for t in spec["tasks"] if not args.tasks or t["id"] in args.tasks.split(",")]
    arms = args.arms.split(",")
    out_path = ROOT / "results" / "raw" / f"{args.out}.jsonl"
    version = subprocess.run(["codex", "--version"], capture_output=True, text=True).stdout.strip()
    meta = {"model": MODEL, "reasoning_effort": EFFORT, "agent": version, "options": {"reasoning_effort": EFFORT, "session_timeout": SESSION_TIMEOUT},
            "ollama_version": None, "model_digests": {}, "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **manifest(args.tasks_file),
            "run_id": args.out, "pilot": args.pilot, "chapter": 2}
    out_path.write_text(json.dumps({"_meta": meta}) + "\n")

    rng = random.Random(20261002)
    plan = []
    for rep in range(1, args.reps + 1):
        for task in tasks:
            order = arms[:]
            rng.shuffle(order)
            plan += [(task, arm, rep) for arm in order]
    if args.only:
        t_id, o_arm, o_rep = args.only.split(":")
        plan = [(next(t for t in spec["tasks"] if t["id"] == t_id), o_arm, int(o_rep))]

    with tempfile.TemporaryDirectory(prefix="codex_empty_", dir=str(CODEX_HOME)) as tmp:
        for i, (task, arm, rep) in enumerate(plan, 1):
            rec = run_session(task, arm, rep, spec["projects"][task["project"]], Path(tmp))
            with out_path.open("a") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"[{i}/{len(plan)}] {task['id']:<16} {arm:<5} rep{rep} {rec['status'][:14]:<14} {rec['wall_s']:>6.1f}s "
                  f"tools={len(rec['tool_calls'])} tok={rec['prompt_tokens']}+{rec['completion_tokens']}"
                  f"{' LEAK' if rec['leak_flag'] else ''}", flush=True)
    print("fertig:", out_path)


if __name__ == "__main__":
    main()
