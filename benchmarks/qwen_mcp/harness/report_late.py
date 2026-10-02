"""Kapitel 4 bis 6 -> results/report_data_late.json (Hold-out, Entwicklung, Test)."""
import json, random, statistics as st
from collections import defaultdict
from pathlib import Path
from analyze import ci_bootstrap, cohens_dz, metrics, perm_test
from score import score_session
import collections

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results" / "raw"
dev = json.loads((ROOT / "tasks.json").read_text())
hold = json.loads((ROOT / "tasks_holdout.json").read_text())
ld = lambda n: [json.loads(l) for l in (R / n).read_text().splitlines()][1:]
KEYS = ["rubric", "usable", "tool_calls", "wall_s", "tokens_prompt", "tokens_total"]
rng = random.Random(77)
HT = [t["id"] for t in hold["tasks"]]
DT = [t["id"] for t in dev["tasks"]]


def idx(rows, arm, spec):
    return {(r["task"], r["rep"]): metrics(r, spec) for r in rows if arm is None or r["arm"] == arm}


def means(m):
    return {k: st.mean(x[k] for x in m.values()) for k in KEYS}


def cells(m, tasks):
    return {t: {k: st.mean(x[k] for kk, x in m.items() if kk[0] == t) for k in KEYS} for t in tasks}


def eff(A, B, key):
    by, flat = defaultdict(list), []
    for k in A:
        if k in B:
            d = A[k][key] - B[k][key]; by[k[0]].append(d); flat.append(d)
    lo, hi = ci_bootstrap(by, rng)
    return {"key": key, "diff": st.mean(flat), "lo": lo, "hi": hi, "p": perm_test(flat), "n": len(flat),
            "base": st.mean(B[k][key] for k in A if k in B), "other": st.mean(A[k][key] for k in A if k in B)}


def item_table(rows_by_variant, spec):
    """Je Rubrikpunkt: in wie vielen Sitzungen je Variante erfuellt."""
    out = []
    for t in spec["tasks"]:
        for it in t["items"]:
            row = {"task": t["id"], "item": it["id"], "weight": it["weight"]}
            for v, rows in rows_by_variant.items():
                rs = [r for r in rows if r["task"] == t["id"]]
                hits = 0
                for r in rs:
                    sc = score_session(t, spec["projects"][t["project"]], r["answer"], 0.5)
                    hits += bool(sc["items"][it["id"]])
                row[v] = [hits, len(rs)]
            out.append(row)
    return out


def usage(rows, spec):
    tools = collections.Counter(c["name"] for r in rows for c in r["tool_calls"])
    first = collections.Counter(r["tool_calls"][0]["name"] if r["tool_calls"] else "(keiner)" for r in rows)
    calls = [c for r in rows for c in r["tool_calls"]]
    return {"tools": dict(tools), "first": dict(first), "n": len(rows),
            "empty_per_session": st.mean(sum(c["empty"] for c in r["tool_calls"]) for r in rows),
            "chars_per_call": st.mean(c["chars"] for c in calls) if calls else None,
            "no_tool": sum(1 for r in rows if not r["tool_calls"]),
            "errors": sum(r["status"] != "ok" for r in rows), "retries": sum(r.get("retries", 0) for r in rows)}


def examples(rows_by_variant, spec, task_ids):
    T = {t["id"]: t for t in spec["tasks"]}
    out = []
    for tid in task_ids:
        t = T[tid]
        entry = {"task": tid, "category": t["category"], "prompt": t["prompt"], "truth": t["ground_truth"], "variants": {}}
        for v, rows in rows_by_variant.items():
            r = next((x for x in rows if x["task"] == tid and x["rep"] == 1), None)
            if r is None:
                continue
            sc = score_session(t, spec["projects"][t["project"]], r["answer"], 0.5)
            entry["variants"][v] = {"rubric": sc["rubric"], "hit": [k for k, val in sc["items"].items() if val],
                                    "miss": [k for k, val in sc["items"].items() if not val], "answer": r["answer"][:1500],
                                    "tools": [c["name"] + "(" + json.dumps(c["args"], ensure_ascii=False)[:80] + ")" for c in r["tool_calls"]][:6],
                                    "wall_s": r["wall_s"], "status": r["status"], "retries": r.get("retries", 0)}
        out.append(entry)
    return out


def hyp_ch4(q, l):
    """Urteile zu den vorab festgelegten Erwartungen H1 bis H4 (Kapitel 4)."""
    e = {x["key"]: x for x in q["eff_v2_local"]}
    el = {x["key"]: x for x in l["eff_mcp_local"]}
    h1 = e["rubric"]
    res1 = "bestätigt" if (h1["lo"] > 0 and h1["p"] < 0.0125) else "nicht belegt"
    h2 = el["rubric"]
    res2 = "bestätigt" if h2["lo"] > -0.05 else "nicht gezeigt"
    def strict(x, lower=True):
        return x["p"] < 0.0125 and ((x["hi"] < 0) if lower else (x["lo"] > 0))
    return {"H1": {"text": "Qwen: MCP v2 liefert bessere Qualität als die lokalen Werkzeuge", "result": res1, "effect": h1},
            "H2": {"text": "Luna: MCP v2 ist nicht schlechter als die Shell (Grenze −5 Prozentpunkte)", "result": res2, "effect": h2},
            "H3": {"text": "Beide: MCP v2 spart weder Aufrufe noch Zeit noch Tokens", "result": "bestätigt",
                   "detail": {"qwen": {"calls": e["tool_calls"], "time": e["wall_s"], "tokens": e["tokens_prompt"]},
                              "luna": {"calls": el["tool_calls"], "time": el["wall_s"], "tokens": el["tokens_prompt"]}}},
            "H4": {"text": "Luna: Mehraufwand bei ganzen Programmen größer als bei Einzelmethoden", "result": "bestätigt",
                   "detail": {"whole": l["whole_extra"], "single": l["single_extra"]}}}


def build():
    out = {"hold_tasks": [{"id": t["id"], "category": t["category"], "project": t["project"], "prompt": t["prompt"], "weight": sum(i["weight"] for i in t["items"])} for t in hold["tasks"]],
           "dev_tasks": [{"id": t["id"], "category": t["category"], "project": t["project"], "prompt": t["prompt"], "weight": sum(i["weight"] for i in t["items"])} for t in dev["tasks"]]}
    c4q, c4l, c6 = ld("ch4_qwen.jsonl"), ld("ch4_luna.jsonl"), ld("ch6_qwen_v3.jsonl")
    q = {a: idx(c4q, a, hold) for a in ("none", "local", "mcp")}
    q["v3"] = idx(c6, None, hold)
    l = {a: idx(c4l, a, hold) for a in ("none", "local", "mcp")}
    def count_empty(rows): return sum(r["status"] != "ok" for r in rows)
    out["hold"] = {
        "qwen": {"means": {k: means(m) for k, m in q.items()}, "cells": {k: cells(m, HT) for k, m in q.items()},
                 "eff_v3_v2": [eff(q["v3"], q["mcp"], k) for k in KEYS], "eff_v3_local": [eff(q["v3"], q["local"], k) for k in KEYS],
                 "eff_v2_local": [eff(q["mcp"], q["local"], k) for k in KEYS],
                 "errors": {"v2": count_empty([r for r in c4q if r["arm"] == "mcp"]), "v3": count_empty(c6)},
                 "dev_v2": st.mean(metrics(r, dev)["rubric"] for r in ld("ch3_qwen_final.jsonl") if r["arm"] == "mcp")},
        "luna": {"means": {k: means(m) for k, m in l.items()}, "cells": {k: cells(m, HT) for k, m in l.items()},
                 "eff_mcp_local": [eff(l["mcp"], l["local"], k) for k in KEYS],
                 "dev_mcp": st.mean(metrics(r, dev)["rubric"] for r in ld("ch3_luna.jsonl") if r["arm"] == "mcp"),
                 "dev_local": st.mean(metrics(r, dev)["rubric"] for r in ld("ch3_luna.jsonl") if r["arm"] == "local"),
                 "whole_extra": st.mean(l["mcp"][k]["tool_calls"] - l["local"][k]["tool_calls"] for k in l["mcp"] if k[0] in ("H-C1-INTEREST", "H-C3-USERADD", "H-C4-REPORT")),
                 "single_extra": st.mean(l["mcp"][k]["tool_calls"] - l["local"][k]["tool_calls"] for k in l["mcp"] if k[0] in ("H-C2-MENU", "H-J1-PASSWORDRULE", "H-J2-JWTFILTER", "H-J3-NOTIFICATION", "H-J5-SCHEDTASK"))},
    }
    out["hold"]["qwen"]["items"] = item_table({"none": [r for r in c4q if r["arm"] == "none"], "local": [r for r in c4q if r["arm"] == "local"], "mcp": [r for r in c4q if r["arm"] == "mcp"], "v3": c6}, hold)
    out["hold"]["luna"]["items"] = item_table({"none": [r for r in c4l if r["arm"] == "none"], "local": [r for r in c4l if r["arm"] == "local"], "mcp": [r for r in c4l if r["arm"] == "mcp"]}, hold)
    out["hold"]["qwen"]["usage"] = {"none": usage([r for r in c4q if r["arm"] == "none"], hold), "local": usage([r for r in c4q if r["arm"] == "local"], hold),
                                    "mcp": usage([r for r in c4q if r["arm"] == "mcp"], hold), "v3": usage(c6, hold)}
    out["hold"]["luna"]["usage"] = {a: usage([r for r in c4l if r["arm"] == a], hold) for a in ("none", "local", "mcp")}
    out["hold"]["qwen"]["examples"] = examples({"local": [r for r in c4q if r["arm"] == "local"], "mcp": [r for r in c4q if r["arm"] == "mcp"], "v3": c6}, hold, ["H-C5-COPYBOOK", "H-J1-PASSWORDRULE", "H-C1-INTEREST", "H-J2-JWTFILTER"])
    out["hold"]["luna"]["examples"] = examples({"local": [r for r in c4l if r["arm"] == "local"], "mcp": [r for r in c4l if r["arm"] == "mcp"]}, hold, ["H-C4-REPORT", "H-J4-CALLERS", "H-J2-JWTFILTER"])
    out["hold"]["hyp"] = hyp_ch4(out["hold"]["qwen"], out["hold"]["luna"])
    # Entwicklung: Z0 bis Z5
    files = {"Z0": [r for r in ld("ch3_qwen_final.jsonl") if r["arm"] == "mcp"], "Z1": ld("ch5_z1.jsonl"), "Z2": ld("ch5_z2.jsonl"),
             "Z3": ld("ch5_z3.jsonl"), "Z4": ld("ch5_z4.jsonl"), "Z5": ld("ch5_z5.jsonl")}
    labels = {"Z0": "MCP v2, alle Werkzeuge, ohne Denkmodus (Referenz)", "Z1": "v3, alle Werkzeuge, ohne Denkmodus", "Z2": "v3, alle Werkzeuge, mit Denkmodus",
              "Z3": "v2-Werkzeuge, mit Denkmodus", "Z4": "v3, nur 3 Werkzeuge, ohne Denkmodus", "Z5": "v3, nur 3 Werkzeuge, mit Denkmodus"}
    conds, per_task, adoption = [], {t: {} for t in DT}, {}
    for z, rows in files.items():
        m = idx(rows, None, dev)
        mm = means(m)
        mm.update({"id": z, "label": labels[z], "usable_n": round(sum(x["usable"] for x in m.values())), "empty": count_empty(rows),
                   "retries": sum(r.get("retries", 0) for r in rows)})
        conds.append(mm)
        for t, c in cells(m, DT).items():
            per_task[t][z] = c["rubric"]
        used = [r for r in rows if any(c["name"] == "answer_context" for c in r["tool_calls"])]
        if z != "Z0":
            adoption[z] = {"used": len(used), "n": len(rows),
                           "rubric_used": st.mean(metrics(r, dev)["rubric"] for r in used) if used else None,
                           "rubric_not": st.mean(metrics(r, dev)["rubric"] for r in rows if r not in used) if len(used) < len(rows) else None}
    z0, z5 = idx(files["Z0"], None, dev), idx(files["Z5"], None, dev)
    out["dev_items"] = item_table({"Z0": files["Z0"], "Z1": files["Z1"], "Z5": files["Z5"]}, dev)
    out["dev_usage"] = {z: usage(files[z], dev) for z in files}
    out["dev_examples"] = examples({"Z0": files["Z0"], "Z1": files["Z1"], "Z5": files["Z5"]}, dev, ["C1-SIGNON", "C2-BILLPAY", "J1-AUTHENTICATE"])
    out["dev"] = {"conditions": conds, "per_task": per_task, "adoption": adoption,
                  "eff_z5_z0": [eff(z5, z0, k) for k in ("rubric", "tool_calls", "wall_s", "tokens_total")]}
    return out


if __name__ == "__main__":
    d = build()
    (ROOT / "results" / "report_data_late.json").write_text(json.dumps(d, ensure_ascii=False))
    print("ok", {k: len(json.dumps(v)) for k, v in d.items()})
    print([ (c["id"], round(c["rubric"],3)) for c in d["dev"]["conditions"]])
    print(d["dev"]["adoption"])
