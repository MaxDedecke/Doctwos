"""Kapitel 7 -> results/report_data_ch7.json (v4: Evidenz-Pack durch den Server, Hold-out)."""
import json, statistics as st
from report_late import ld, hold, dev, HT, KEYS, idx, means, cells, eff, item_table, usage, examples, ROOT
from analyze import metrics


def build():
    c4 = [r for r in ld("ch4_qwen.jsonl")]
    v2 = [r for r in c4 if r["arm"] == "mcp"]
    loc = [r for r in c4 if r["arm"] == "local"]
    v3 = ld("ch6_qwen_v3.jsonl")
    v4 = ld("ch7_qwen_v4.jsonl")
    m = {"v2": idx(v2, None, hold), "v3": idx(v3, None, hold), "v4": idx(v4, None, hold), "local": idx(loc, None, hold)}
    rows = {"local": loc, "v2": v2, "v3": v3, "v4": v4}
    out = {
        "means": {k: means(x) for k, x in m.items()},
        "cells": {k: cells(x, HT) for k, x in m.items()},
        "eff_v4_v3": [eff(m["v4"], m["v3"], k) for k in KEYS],
        "eff_v4_v2": [eff(m["v4"], m["v2"], k) for k in KEYS],
        "eff_v4_local": [eff(m["v4"], m["local"], k) for k in KEYS],
        "items": item_table(rows, hold),
        "usage": {k: usage(r, hold) for k, r in rows.items()},
        "errors": {k: sum(r["status"] != "ok" for r in r_) for k, r_ in rows.items()},
        "examples": examples(rows, hold, ["H-C1-INTEREST", "H-J2-JWTFILTER", "H-C5-COPYBOOK", "H-J1-PASSWORDRULE"]),
        "prefetch_chars": st.mean(r["tool_calls"][0]["chars"] for r in v4 if r["tool_calls"]),
        "prefetch_s": st.mean(r["tool_calls"][0]["s"] for r in v4 if r["tool_calls"]),
        "prefetch_truncated": sum(1 for r in v4 if r["tool_calls"] and r["tool_calls"][0]["truncated"]),
    }
    return out


if __name__ == "__main__":
    d = build()
    (ROOT / "results" / "report_data_ch7.json").write_text(json.dumps(d, ensure_ascii=False))
    for k, v in d["means"].items():
        print(k, {a: round(b, 3) for a, b in v.items()})
    for name in ("eff_v4_v3", "eff_v4_v2", "eff_v4_local"):
        for e in d[name]:
            print(name, e["key"], round(e["diff"], 3), round(e["lo"], 3), round(e["hi"], 3), "p=%.4f" % e["p"])
    print("errors", d["errors"], "prefetch", d["prefetch_chars"], d["prefetch_s"], d["prefetch_truncated"])
