"""Auswertung: gepaarte Effekte mit Bootstrap-Konfidenzintervallen und exakten Permutationstests.

Aufruf: python harness/analyze.py results/raw/<run>.jsonl [--out results/<run>_report.md]
Reine Standardbibliothek (kein numpy/scipy noetig).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import statistics as st
from collections import defaultdict
from pathlib import Path

from score import score_session

ROOT = Path(__file__).resolve().parent.parent
BOOT = 10000


def load(path: Path):
    meta, rows = {}, []
    for line in path.read_text().splitlines():
        d = json.loads(line)
        if "_meta" in d:
            meta = d["_meta"]
        else:
            rows.append(d)
    return meta, rows


def metrics(row: dict, spec: dict) -> dict:
    task = next(t for t in spec["tasks"] if t["id"] == row["task"])
    project = spec["projects"][task["project"]]
    s = score_session(task, project, row["answer"], spec["scoring"]["usable_threshold"])
    calls = row["tool_calls"]
    return {
        "rubric": s["rubric"],
        "usable": 1.0 if s["usable"] else 0.0,
        "completed": 1.0 if row["status"] == "ok" and not row["forced_final"] else 0.0,
        "answered": 1.0 if row["status"] == "ok" else 0.0,
        "wall_s": row["wall_s"],
        "tokens_total": row["prompt_tokens"] + row["completion_tokens"],
        "tokens_prompt": row["prompt_tokens"],
        "tokens_completion": row["completion_tokens"],
        "tool_calls": float(len(calls)),
        "tool_used": 1.0 if calls else 0.0,
        "tool_errors": float(sum(c["error"] for c in calls)),
        "tool_empty": float(sum(c["empty"] for c in calls)),
        "tool_out_chars": float(row["tool_output_chars"]),
        "turns": float(row["turns"]),
        "cite_file_rate": s["cite_file_rate"],
        "cite_line_rate": s["cite_line_rate"],
        "cite_n": float(s["cite_n"]),
        "items": s["items"],
    }


def ci_bootstrap(diffs_by_task: dict[str, list[float]], rng: random.Random):
    """Cluster-Bootstrap: Aufgaben werden gezogen, innerhalb der Aufgabe die Wiederholungen."""
    tasks = list(diffs_by_task)
    stats = []
    for _ in range(BOOT):
        pick = [rng.choice(tasks) for _ in tasks]
        vals = []
        for t in pick:
            vals += [rng.choice(diffs_by_task[t]) for _ in diffs_by_task[t]]
        stats.append(sum(vals) / len(vals))
    stats.sort()
    return stats[int(0.025 * BOOT)], stats[int(0.975 * BOOT)]


def perm_test(diffs: list[float]) -> float:
    """Exakter Vorzeichen-Permutationstest (zweiseitig) auf den Mittelwert gepaarter Differenzen."""
    d = [x for x in diffs if x != 0]
    if not d:
        return 1.0
    obs = abs(sum(d))
    n = len(d)
    if n > 20:
        rng = random.Random(1)
        hits = sum(abs(sum(x * rng.choice((-1, 1)) for x in d)) >= obs - 1e-12 for _ in range(100000))
        return (hits + 1) / 100001
    hits = sum(abs(sum(s * x for s, x in zip(signs, d))) >= obs - 1e-12 for signs in itertools.product((-1, 1), repeat=n))
    return hits / 2**n


def cohens_dz(diffs: list[float]) -> float | None:
    if len(diffs) < 2:
        return None
    sd = st.stdev(diffs)
    return (st.mean(diffs) / sd) if sd else None


def fmt(x, nd=2):
    return "–" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    spec = json.loads((ROOT / "tasks.json").read_text())
    meta, rows = load(Path(args.file))
    data = defaultdict(dict)  # (task, rep) -> arm -> metrics
    arms = sorted({r["arm"] for r in rows}, key=["none", "local", "mcp"].index)
    for r in rows:
        data[(r["task"], r["rep"])][r["arm"]] = metrics(r, spec)

    lines = [f"# Auswertung {meta.get('run_id', Path(args.file).stem)}", ""]
    lines += [f"Modell `{meta.get('model')}` (Digest {meta.get('model_digests', {}).get(meta.get('model'), '?')}), "
              f"Ollama {meta.get('ollama_version')}, Optionen `{json.dumps(meta.get('options'))}`, "
              f"{len(rows)} Sitzungen, Pilot: {meta.get('pilot')}.", ""]

    # 1. Deskriptiv je Arm
    keys = [("rubric", "Rubrikwert (0–1)"), ("usable", "nutzbar (Rubrik ≥ Schwelle)"), ("answered", "Antwort geliefert"),
            ("completed", "ohne erzwungenen Abschluss"), ("wall_s", "Wandzeit s"), ("tokens_total", "Tokens gesamt"),
            ("tokens_prompt", "Tokens Prompt (summiert)"), ("tokens_completion", "Tokens Antwort"),
            ("tool_calls", "Werkzeugaufrufe"), ("tool_used", "Werkzeug überhaupt genutzt"), ("tool_errors", "Werkzeugfehler"), ("tool_empty", "leere Treffer"),
            ("tool_out_chars", "Werkzeugausgabe Zeichen"), ("cite_file_rate", "Beleg: Datei existiert"),
            ("cite_line_rate", "Beleg: Zeile plausibel")]
    lines += ["## 1. Kennzahlen je Arm (Mittelwert [Median])", "", "| Kennzahl | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for k, label in keys:
        cells = []
        for a in arms:
            v = [m[a][k] for m in data.values() if a in m and m[a][k] is not None]
            cells.append(f"{fmt(st.mean(v))} [{fmt(st.median(v))}]" if v else "–")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    # 2. Gepaarte Effekte
    rng = random.Random(7)
    pairs = [("mcp", "local"), ("mcp", "none"), ("local", "none")]
    lines += ["## 2. Gepaarte Effekte (Differenz = erster − zweiter Arm)", "",
              "95-%-KI per Cluster-Bootstrap über Aufgaben (10 000 Ziehungen); p aus exaktem Vorzeichen-Permutationstest über alle (Aufgabe, Wiederholung)-Paare, "
              "nicht für Mehrfachvergleiche korrigiert. d_z = standardisierter gepaarter Effekt.", ""]
    for a, b in pairs:
        if a not in arms or b not in arms:
            continue
        lines += [f"### {a} − {b}", "", "| Kennzahl | Ø Differenz | 95-%-KI | p | d_z | n Paare | relativ |", "|---|---|---|---|---|---|---|"]
        for k, label in keys:
            by_task = defaultdict(list)
            flat = []
            base = []
            for (task, rep), m in data.items():
                if a in m and b in m and m[a][k] is not None and m[b][k] is not None:
                    d = m[a][k] - m[b][k]
                    by_task[task].append(d)
                    flat.append(d)
                    base.append(m[b][k])
            if not flat:
                continue
            lo, hi = ci_bootstrap(by_task, rng)
            rel = (st.mean(flat) / st.mean(base) * 100) if st.mean(base) else None
            lines.append(f"| {label} | {fmt(st.mean(flat), 3)} | [{fmt(lo, 3)}; {fmt(hi, 3)}] | {fmt(perm_test(flat), 4)} | "
                         f"{fmt(cohens_dz(flat))} | {len(flat)} | {fmt(rel, 0) + ' %' if rel is not None else '–'} |")
        lines.append("")

    # 3. Je Aufgabe
    tasks = [t["id"] for t in spec["tasks"] if any(r["task"] == t["id"] for r in rows)]
    lines += ["## 3. Rubrikwert und Zeit je Aufgabe (Mittel über Wiederholungen)", "",
              "| Aufgabe | " + " | ".join(f"{a} Rubrik" for a in arms) + " | " + " | ".join(f"{a} s" for a in arms) + " |",
              "|---|" + "---|" * (2 * len(arms))]
    for t in tasks:
        cells = []
        for k in ("rubric", "wall_s"):
            for a in arms:
                v = [m[a][k] for (tt, _), m in data.items() if tt == t and a in m]
                cells.append(fmt(st.mean(v)) if v else "–")
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    lines.append("")

    # 4. Item-Ebene
    lines += ["## 4. Erfüllte Rubrikitems (Anteil der Sitzungen)", "", "| Aufgabe / Item | " + " | ".join(arms) + " |", "|---|" + "---|" * len(arms)]
    for t in spec["tasks"]:
        if t["id"] not in tasks:
            continue
        for it in t["items"]:
            cells = []
            for a in arms:
                v = [m[a]["items"][it["id"]] for (tt, _), m in data.items() if tt == t["id"] and a in m]
                cells.append(f"{sum(v)}/{len(v)}" if v else "–")
            lines.append(f"| {t['id']} · {it['id']} | " + " | ".join(cells) + " |")
    lines.append("")

    # 5. Werkzeugnutzung
    usage = defaultdict(lambda: defaultdict(int))
    for r in rows:
        for c in r["tool_calls"]:
            usage[r["arm"]][c["name"]] += 1
    lines += ["## 5. Werkzeugnutzung (Aufrufe gesamt)", ""]
    for a in arms:
        if usage[a]:
            lines.append(f"- **{a}**: " + ", ".join(f"{n} ×{c}" for n, c in sorted(usage[a].items(), key=lambda x: -x[1])))
    trunc = sum(c["truncated"] for r in rows for c in r["tool_calls"])
    lines += ["", f"Auf {TOOL_CAP_NOTE} gekürzte Werkzeugausgaben insgesamt: {trunc}.", ""]
    report = "\n".join(lines)
    out = Path(args.out) if args.out else ROOT / "results" / (Path(args.file).stem + "_report.md")
    out.write_text(report)
    print(report)
    print("\n->", out)


TOOL_CAP_NOTE = "das Zeichenlimit"

if __name__ == "__main__":
    main()
