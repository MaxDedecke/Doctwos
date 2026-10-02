"""Kapitel 4: Hold-out-Auswertung (MCP v2 gegen lokal und ohne Werkzeuge) -> results/report_data_ch4.json"""
import json, random, statistics as st
from collections import defaultdict
from pathlib import Path
from analyze import ci_bootstrap, cohens_dz, metrics, perm_test

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results" / "raw"
spec = json.loads((ROOT / "tasks_holdout.json").read_text())
spec_dev = json.loads((ROOT / "tasks.json").read_text())
TASKS = [t["id"] for t in spec["tasks"]]
CAT = {t["id"]: t["category"] for t in spec["tasks"]}
KEYS = ["rubric", "usable", "tool_calls", "wall_s", "tokens_prompt"]
ALPHA, NI = 0.0125, -0.05
load = lambda n: [json.loads(l) for l in (R / n).read_text().splitlines()][1:]
D = {"qwen": load("ch4_qwen.jsonl"), "luna": load("ch4_luna.jsonl")}
DEV3 = {"qwen": load("ch3_qwen_final.jsonl"), "luna": load("ch3_luna.jsonl")}


def idx(rows, arm, sp):
    return {(r["task"], r["rep"]): metrics(r, sp) for r in rows if r["arm"] == arm}


def eff(A, B, key, rng):
    by, flat = defaultdict(list), []
    for k in A:
        if k in B:
            d = A[k][key] - B[k][key]; by[k[0]].append(d); flat.append(d)
    lo, hi = ci_bootstrap(by, rng)
    return {"key": key, "diff": st.mean(flat), "lo": lo, "hi": hi, "p": perm_test(flat), "dz": cohens_dz(flat), "n": len(flat),
            "base": st.mean(B[k][key] for k in A if k in B), "other": st.mean(A[k][key] for k in A if k in B)}


def build():
    rng = random.Random(41)
    out = {"models": {}}
    for m, rows in D.items():
        arms = {a: idx(rows, a, spec) for a in ("none", "local", "mcp")}
        means = {a: {k: st.mean(x[k] for x in A.values()) for k in KEYS + ["tool_used", "completed"]} for a, A in arms.items()}
        cells = {t: {a: {k: st.mean(x[k] for kk, x in A.items() if kk[0] == t) for k in KEYS} for a, A in arms.items()} for t in TASKS}
        effects = {"mcp-local": [eff(arms["mcp"], arms["local"], k, rng) for k in KEYS],
                   "mcp-none": [eff(arms["mcp"], arms["none"], k, rng) for k in KEYS]}
        e = {x["key"]: x for x in effects["mcp-local"]}
        dev_mcp = [metrics(r, spec_dev) for r in DEV3[m] if r["arm"] == "mcp"]
        out["models"][m] = {"means": means, "cells": cells, "effects": effects,
                            "dev_mcp_rubric": st.mean(x["rubric"] for x in dev_mcp), "dev_mcp_calls": st.mean(x["tool_calls"] for x in dev_mcp),
                            "dev_local_rubric": st.mean(metrics(r, spec_dev)["rubric"] for r in DEV3[m] if r["arm"] == "local"),
                            "n_sessions": len(rows), "errors": sum(r["status"] != "ok" for r in rows)}
        # H4: Mehraufwand an Aufrufen bei ganzen Programmen gegenueber Einzelmethoden
        whole = ["H-C1-INTEREST", "H-C3-USERADD", "H-C4-REPORT"]
        single = ["H-C2-MENU", "H-J1-PASSWORDRULE", "H-J2-JWTFILTER", "H-J3-NOTIFICATION", "H-J5-SCHEDTASK"]
        def extra(group):
            return st.mean(arms["mcp"][k]["tool_calls"] - arms["local"][k]["tool_calls"] for k in arms["mcp"] if k[0] in group and k in arms["local"])
        out["models"][m]["h4"] = {"whole_program": extra(whole), "single_method": extra(single)}
        # Ratenerrat: Anteil der "none"-Punkte
        out["models"][m]["none_rubric"] = means["none"]["rubric"]
    return out


if __name__ == "__main__":
    d = build()
    (ROOT / "results" / "report_data_ch4.json").write_text(json.dumps(d, ensure_ascii=False))
    for m, x in d["models"].items():
        print("\n", m, "Sitzungen", x["n_sessions"], "Fehler", x["errors"])
        for a, v in x["means"].items():
            print(f"   {a:6s}", {k: round(val, 2) for k, val in v.items()})
        for name, es in x["effects"].items():
            print("  ", name)
            for e in es:
                print(f"     {e['key']:14s} Δ={e['diff']:9.3f} [{e['lo']:9.3f};{e['hi']:9.3f}] p={e['p']:.4f} n={e['n']}")
        print("   Dev (6 alte Fragen, MCP v2) Rubrik", round(x["dev_mcp_rubric"], 2), "→ neue Fragen", round(x["means"]["mcp"]["rubric"], 2), "| local alt", round(x["dev_local_rubric"], 2), "→", round(x["means"]["local"]["rubric"], 2))
        print("   H4 Mehraufrufe MCP-lokal: ganze Programme", round(x["h4"]["whole_program"], 2), "Einzelmethoden", round(x["h4"]["single_method"], 2))
        print("   je Frage Rubrik (none/local/mcp):", {t.replace('H-',''): tuple(round(c[a]['rubric'],2) for a in ('none','local','mcp')) for t, c in x["cells"].items()})
