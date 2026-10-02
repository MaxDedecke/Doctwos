"""Kapitel 7 und 8 -> results/report_data_ch78.json (v4 und v4.1: Evidenz-Pack durch den Server)."""
import json, statistics as st
from report_late import ld, hold, dev, HT, DT, KEYS, idx, means, cells, eff, item_table, usage, examples, ROOT
from analyze import metrics


def block(rows_by, spec, tasks, ex_ids, base_pairs):
    m = {k: idx(r, None, spec) for k, r in rows_by.items()}
    out = {"means": {k: means(x) for k, x in m.items()}, "cells": {k: cells(x, tasks) for k, x in m.items()},
           "items": item_table(rows_by, spec), "usage": {k: usage(r, spec) for k, r in rows_by.items()},
           "errors": {k: sum(r["status"] != "ok" for r in r_) for k, r_ in rows_by.items()},
           "usable_n": {k: round(sum(x["usable"] for x in v.values())) for k, v in m.items()},
           "n": {k: len(v) for k, v in m.items()},
           "examples": examples(rows_by, spec, ex_ids), "eff": {}}
    for a, b in base_pairs:
        out["eff"][f"{a}_{b}"] = [eff(m[a], m[b], k) for k in KEYS]
    pre = {}
    for k, rows in rows_by.items():
        first = [r["tool_calls"][0] for r in rows if r["tool_calls"] and r["tool_calls"][0].get("prefetch")]
        if first:
            pre[k] = {"chars": st.mean(c["chars"] for c in first), "s": st.mean(c["s"] for c in first),
                      "truncated": sum(c["truncated"] for c in first), "n": len(first)}
    out["prefetch"] = pre
    return out


def build():
    c4 = ld("ch4_qwen.jsonl")
    hold_rows = {"local": [r for r in c4 if r["arm"] == "local"], "v2": [r for r in c4 if r["arm"] == "mcp"], "v3": ld("ch6_qwen_v3.jsonl"),
                 "v4": ld("ch7_qwen_v4.jsonl"), "v41": ld("ch8_qwen_v41_hold.jsonl")}
    dev_rows = {"v2": [r for r in ld("ch3_qwen_final.jsonl") if r["arm"] == "mcp"], "v3": ld("ch5_z5.jsonl"), "v41": ld("ch8_qwen_v41_dev.jsonl")}
    return {"hold": block(hold_rows, hold, HT, ["H-C1-INTEREST", "H-J2-JWTFILTER", "H-C4-REPORT", "H-C3-USERADD"],
                          [("v4", "v3"), ("v41", "v4"), ("v41", "v3"), ("v41", "v2"), ("v41", "local")]),
            "dev": block(dev_rows, dev, DT, ["C3-POSTING", "C1-SIGNON", "J2-LOCKOUT"], [("v41", "v3"), ("v41", "v2")]),
            "hold_tasks": [{"id": t["id"], "category": t["category"], "prompt": t["prompt"]} for t in hold["tasks"]]}


if __name__ == "__main__":
    d = build()
    (ROOT / "results" / "report_data_ch78.json").write_text(json.dumps(d, ensure_ascii=False))
    for part in ("hold", "dev"):
        print(part, {k: {a: round(b, 3) for a, b in v.items()} for k, v in d[part]["means"].items()})
        print(" usable", d[part]["usable_n"], "n", d[part]["n"], "errors", d[part]["errors"], "prefetch", d[part]["prefetch"])
        for name, es in d[part]["eff"].items():
            print(" ", name, [(e["key"], round(e["diff"], 3), round(e["lo"], 3), round(e["hi"], 3), round(e["p"], 4)) for e in es if e["key"] in ("rubric", "usable", "wall_s", "tokens_total")])
