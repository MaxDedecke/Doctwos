"""Kapitel 3: Vorher/Nachher-Auswertung MCP v1 gegen MCP v2 -> results/report_data_ch3.json (fuer den HTML-Bericht)."""

import json
import random
import statistics as st
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from analyze import ci_bootstrap, cohens_dz, metrics, perm_test

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results" / "raw"
spec = json.loads((ROOT / "tasks.json").read_text())
TASKS = [t["id"] for t in spec["tasks"]]
CAT = {t["id"]: t["category"] for t in spec["tasks"]}
ALPHA = 0.0125
NI_MARGIN = -0.05
KEYS = ["rubric", "usable", "tool_calls", "wall_s", "tokens_prompt", "tokens_total", "turns"]


def load(name):
    return [json.loads(line) for line in (R / name).read_text().splitlines()][1:]


DATA = {
    "qwen": {"v1": load("main_run_final.jsonl"), "v2": load("ch3_qwen_final.jsonl"), "label": "Qwen3-8B (lokal)"},
    "luna": {"v1": load("codex_run.jsonl"), "v2": load("ch3_luna.jsonl"), "label": "GPT-6-Luna (Codex CLI)"},
}


def idx(rows, arm):
    return {(r["task"], r["rep"]): (metrics(r, spec), r) for r in rows if r["arm"] == arm}


def effect(A, B, key, rng):
    by, flat, base = defaultdict(list), [], []
    for k in A:
        if k in B:
            d = A[k][0][key] - B[k][0][key]
            by[k[0]].append(d)
            flat.append(d)
            base.append(B[k][0][key])
    lo, hi = ci_bootstrap(by, rng)
    bm = st.mean(base)
    return {"key": key, "diff": st.mean(flat), "lo": lo, "hi": hi, "p": perm_test(flat), "dz": cohens_dz(flat), "n": len(flat),
            "base": bm, "other": st.mean(A[k][0][key] for k in A if k in B), "rel": (st.mean(flat) / bm) if bm else None}


def verdict_lower_better(e):
    if e["hi"] < 0 and e["p"] < ALPHA:
        return "bestätigt"
    if e["lo"] > 0:
        return "Gegenrichtung (belegt)"
    return "nicht belegt" + (" (Punktschätzung in Gegenrichtung)" if e["diff"] > 0 else "")


def build():
    rng = random.Random(23)
    out = {"models": {}, "alpha": ALPHA, "ni_margin": NI_MARGIN}
    for m, d in DATA.items():
        v1m, v1l = idx(d["v1"], "mcp"), idx(d["v1"], "local")
        v2m, v2l = idx(d["v2"], "mcp"), idx(d["v2"], "local")
        arms = {"mcp1": v1m, "mcp2": v2m, "local": v2l, "local_alt": v1l, "none": idx(d["v1"], "none")}
        means = {a: {k: st.mean(x[0][k] for x in A.values()) for k in KEYS} for a, A in arms.items()}
        cells = {}
        for t in TASKS:
            cells[t] = {a: {k: st.mean(x[0][k] for kk, x in A.items() if kk[0] == t) for k in KEYS} for a, A in arms.items()}
        eff = {name: [effect(A, B, k, rng) for k in KEYS] for name, (A, B) in {
            "v2-v1": (v2m, v1m), "v2-local": (v2m, v2l), "drift": (v2l, v1l)}.items()}
        e = {x["key"]: x for x in eff["v2-v1"]}
        verdicts = {
            "H1": {"text": "Weniger Werkzeugaufrufe als MCP v1", "result": verdict_lower_better(e["tool_calls"]), "effect": e["tool_calls"]},
            "H2": {"text": "Nicht langsamer als MCP v1", "result": verdict_lower_better(e["wall_s"]).replace("bestätigt", "schneller (belegt)").replace("Gegenrichtung (belegt)", "langsamer (belegt)"), "effect": e["wall_s"]},
            "H3": {"text": "Weniger Eingabe-Tokens als MCP v1", "result": verdict_lower_better(e["tokens_prompt"]), "effect": e["tokens_prompt"]},
        }
        q = e["rubric"]
        if m == "qwen":
            res = "bestätigt" if (q["lo"] > 0 and q["p"] < ALPHA) else "nicht belegt"
            verdicts["H4"] = {"text": "Qualität besser als MCP v1", "result": res, "effect": q}
        else:
            res = "bestätigt" if q["lo"] > NI_MARGIN else f"Nichtunterlegenheit nicht gezeigt (untere Grenze {q['lo'] * 100:+.1f} PP)"
            verdicts["H4"] = {"text": "Qualität nicht schlechter als MCP v1 (Grenze −5 PP)", "result": res, "effect": q}
        # Nutzungsmuster
        rows2 = [r for r in d["v2"] if r["arm"] == "mcp"]
        rows1 = [r for r in d["v1"] if r["arm"] == "mcp"]
        def tool_counts(rows):
            c = Counter(x["name"] for r in rows for x in r["tool_calls"])
            return dict(c)
        explain = defaultdict(list)
        for r in rows2:
            explain[r["task"]].append(sum(1 for x in r["tool_calls"] if x["name"] == "explain_symbol"))
        calls_by_task = {t: {a: cells[t][a]["tool_calls"] for a in ("mcp1", "mcp2", "local")} for t in TASKS}
        first = Counter(r["tool_calls"][0]["name"] for r in rows2 if r["tool_calls"])
        out["models"][m] = {
            "label": d["label"], "means": means, "cells": cells, "effects": eff, "verdicts": verdicts,
            "usage": {"tools_v1": tool_counts(rows1), "tools_v2": tool_counts(rows2), "first_tool_v2": dict(first),
                      "explain_per_task": {t: st.mean(v) for t, v in explain.items()},
                      "empty_per_session": {"v1": st.mean(sum(c["empty"] for c in r["tool_calls"]) for r in rows1),
                                            "v2": st.mean(sum(c["empty"] for c in r["tool_calls"]) for r in rows2)},
                      "chars_per_call_v2": st.mean(c["chars"] for r in rows2 for c in r["tool_calls"]) if rows2 else None,
                      "chars_per_call_v1": st.mean(c["chars"] for r in rows1 for c in r["tool_calls"]) if rows1 else None},
            "sessions": [{"task": r["task"], "arm": ("mcp2" if r["arm"] == "mcp" else "local"), "rubric": metrics(r, spec)["rubric"], "wall_s": r["wall_s"]} for r in d["v2"]]
                        + [{"task": r["task"], "arm": "mcp1", "rubric": metrics(r, spec)["rubric"], "wall_s": r["wall_s"]} for r in rows1],
        }
    # Serverzeiten aus dem MCP-Audit (alle Aufrufe seit Einfuehrung von explain_symbol)
    sql = ("select tool_name, count(*), round(avg(duration_ms)), round((percentile_cont(0.95) within group (order by duration_ms))::numeric), "
           "round(avg(result_payload_bytes)) from mcp_tool_audit_logs where status='success' and created_at >= '2026-10-02 14:20:00+00' group by 1 order by 2 desc")
    res = subprocess.run(["docker", "exec", "doctus-db", "psql", "-U", "admin", "-d", "doctus", "-At", "-F", "|", "-c", sql], capture_output=True, text=True).stdout
    out["audit"] = [dict(zip(("tool", "n", "avg_ms", "p95_ms", "avg_bytes"), line.split("|"))) for line in res.strip().splitlines()]
    return out


if __name__ == "__main__":
    data = build()
    (ROOT / "results" / "report_data_ch3.json").write_text(json.dumps(data, ensure_ascii=False))
    for m, d in data["models"].items():
        print("\n", m)
        for h, v in d["verdicts"].items():
            e = v["effect"]
            print(f"  {h} {v['text']}: {v['result']}  (Δ={e['diff']:.3f} [{e['lo']:.3f};{e['hi']:.3f}] p={e['p']:.4f})")
        print("  explain je Aufgabe", {t: round(x, 1) for t, x in d["usage"]["explain_per_task"].items()})
        print("  Werkzeuge v2", d["usage"]["tools_v2"], "erste", d["usage"]["first_tool_v2"])
        print("  Zeichen je Aufruf v1/v2", round(d["usage"]["chars_per_call_v1"]), round(d["usage"]["chars_per_call_v2"]), "leer je Sitzung", {k: round(v, 2) for k, v in d["usage"]["empty_per_session"].items()})
    print("\n", data["audit"])
