"""Aggregiert einen Lauf zu report_data.json fuer den visuellen Bericht (build_report.py)."""

from __future__ import annotations

import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from analyze import ci_bootstrap, cohens_dz, load, metrics, perm_test

ROOT = Path(__file__).resolve().parent.parent
ARMS = ["none", "local", "mcp"]

# (Schluessel, Anzeigename, bessere Richtung: +1 hoeher ist besser, -1 niedriger ist besser, Einheit)
DIMENSIONS = [
    ("rubric", "Antwortqualität", 1, "Rubrikwert"),
    ("rubric_specific", "Qualität ohne erratbare Punkte", 1, "Rubrikwert ohne Punkte, die auch ohne Werkzeuge meist getroffen werden"),
    ("usable", "Nutzbarkeit", 1, "Anteil ≥ 50 % Rubrik"),
    ("wall_s", "Geschwindigkeit", -1, "Sekunden je Antwort"),
    ("tokens_total", "Token-Verbrauch", -1, "Tokens je Antwort"),
    ("cite_file_rate", "Belegtreue (Dateien)", 1, "Anteil existierender Dateien"),
    ("tool_used", "Werkzeug genutzt", 1, "Anteil Sitzungen mit ≥ 1 Aufruf"),
    ("tool_calls", "Werkzeugaufrufe", -1, "Aufrufe je Antwort"),
    ("completed", "Ohne erzwungenen Abschluss", 1, "Anteil"),
]


def mean(v):
    v = [x for x in v if x is not None]
    return st.mean(v) if v else None


def build(path: Path) -> dict:
    spec = json.loads((ROOT / "tasks.json").read_text())
    meta, rows = load(path)
    sessions = []
    for r in rows:
        m = metrics(r, spec)
        sessions.append({
            "task": r["task"], "arm": r["arm"], "rep": r["rep"], "status": r["status"],
            **{k: m[k] for k in ("rubric", "usable", "completed", "wall_s", "tokens_total", "tokens_prompt",
                                  "tokens_completion", "tool_calls", "tool_used", "tool_errors", "tool_empty", "tool_out_chars",
                                  "turns", "cite_file_rate", "cite_line_rate", "cite_n")},
            "items": m["items"], "forced_final": r["forced_final"], "llm_s": r["llm_s"], "tool_s": r["tool_s"],
        })
    tasks = [t for t in spec["tasks"] if any(s["task"] == t["id"] for s in sessions)]

    # Sensitivitaet (explorativ, nachtraeglich): Punkte, die der Arm ohne Werkzeuge in >= 60 % seiner Laeufe trifft,
    # sind mit Allgemeinwissen erratbar. Der "spezifische" Rubrikwert laesst sie weg.
    guessable = set()
    for t in tasks:
        none_runs = [s for s in sessions if s["task"] == t["id"] and s["arm"] == "none"]
        for it in t["items"]:
            if none_runs and sum(s["items"][it["id"]] for s in none_runs) / len(none_runs) >= 0.6:
                guessable.add((t["id"], it["id"]))
    for s in sessions:
        t = next(x for x in tasks if x["id"] == s["task"])
        keep = [it for it in t["items"] if (t["id"], it["id"]) not in guessable]
        tot = sum(it["weight"] for it in keep)
        s["rubric_specific"] = (sum(it["weight"] for it in keep if s["items"][it["id"]]) / tot) if tot else None

    cells = {}
    for t in tasks:
        for a in ARMS:
            ss = [s for s in sessions if s["task"] == t["id"] and s["arm"] == a]
            if not ss:
                continue
            cells[f"{t['id']}|{a}"] = {k: mean([s[k] for s in ss]) for k in
                                       ("rubric", "rubric_specific", "usable", "wall_s", "tokens_total", "tool_calls", "tool_used", "cite_file_rate", "completed", "tool_errors", "tool_empty")}
            cells[f"{t['id']}|{a}"]["n"] = len(ss)
            cells[f"{t['id']}|{a}"]["rubric_sd"] = st.pstdev([s["rubric"] for s in ss]) if len(ss) > 1 else 0
            cells[f"{t['id']}|{a}"]["wall_sd"] = st.pstdev([s["wall_s"] for s in ss]) if len(ss) > 1 else 0

    arm_means = {a: {k: mean([s[k] for s in sessions if s["arm"] == a])
                     for k in ("rubric", "rubric_specific", "usable", "wall_s", "tokens_total", "tokens_prompt", "tokens_completion",
                               "tool_calls", "tool_used", "tool_errors", "tool_empty", "cite_file_rate", "cite_line_rate", "completed", "turns")}
                 for a in ARMS if any(s["arm"] == a for s in sessions)}

    paired = defaultdict(dict)
    for s in sessions:
        paired[(s["task"], s["rep"])][s["arm"]] = s
    rng = random.Random(7)
    effects = {}
    for a, b in (("mcp", "local"), ("mcp", "none"), ("local", "none")):
        eff = []
        for key, label, direction, unit in DIMENSIONS:
            by_task, flat, base = defaultdict(list), [], []
            for (task, _rep), m in paired.items():
                if a in m and b in m and m[a][key] is not None and m[b][key] is not None:
                    d = m[a][key] - m[b][key]
                    by_task[task].append(d)
                    flat.append(d)
                    base.append(m[b][key])
            if not flat:
                continue
            lo, hi = ci_bootstrap(by_task, rng)
            bm = st.mean(base)
            eff.append({
                "key": key, "label": label, "direction": direction, "unit": unit,
                "mean_a": mean([m[a][key] for m in paired.values() if a in m and m[a][key] is not None]),
                "mean_b": bm, "diff": st.mean(flat), "lo": lo, "hi": hi, "p": perm_test(flat),
                "dz": cohens_dz(flat), "n": len(flat),
                "rel": (st.mean(flat) / bm) if bm else None,
                "rel_lo": (lo / bm) if bm else None, "rel_hi": (hi / bm) if bm else None,
            })
        effects[f"{a}-{b}"] = eff

    speed = []
    for t in tasks:
        row = {"task": t["id"], "category": t["category"], "project": t["project"]}
        for a in ARMS:
            c = cells.get(f"{t['id']}|{a}")
            row[a] = c["wall_s"] if c else None
        speed.append(row)

    tool_usage = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for c in r["tool_calls"]:
            tool_usage[r["arm"]][c["name"]] += 1

    item_hits = []
    for t in tasks:
        for it in t["items"]:
            row = {"task": t["id"], "item": it["id"], "weight": it["weight"]}
            for a in ARMS:
                v = [s["items"][it["id"]] for s in sessions if s["task"] == t["id"] and s["arm"] == a]
                row[a] = (sum(v), len(v)) if v else None
            item_hits.append(row)

    examples = []
    for t in tasks:
        for a in ARMS:
            raw = next((r for r in rows if r["task"] == t["id"] and r["arm"] == a and r["rep"] == 1), None)
            if raw:
                sc = next(s for s in sessions if s["task"] == t["id"] and s["arm"] == a and s["rep"] == 1)
                examples.append({"task": t["id"], "arm": a, "rubric": sc["rubric"], "answer": raw["answer"][:1800],
                                 "tools": [f"{c['name']}({json.dumps(c['args'], ensure_ascii=False)[:90]})" for c in raw["tool_calls"]][:8]})

    return {
        "meta": meta, "tasks": [{"id": t["id"], "category": t["category"], "project": t["project"], "prompt": t["prompt"],
                                  "ground_truth": t["ground_truth"], "items": t["items"]} for t in tasks],
        "guessable": sorted(f"{a}:{b}" for a, b in guessable),
        "sessions": sessions, "cells": cells, "arm_means": arm_means, "effects": effects, "speed": speed,
        "tool_usage": {a: dict(v) for a, v in tool_usage.items()}, "item_hits": item_hits, "examples": examples,
        "truncated_outputs": sum(c["truncated"] for r in rows for c in r["tool_calls"]),
        "n_sessions": len(sessions),
    }


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "results" / "report_data.json"
    data = build(src)
    out.write_text(json.dumps(data, ensure_ascii=False))
    print("->", out, data["n_sessions"], "Sitzungen")
