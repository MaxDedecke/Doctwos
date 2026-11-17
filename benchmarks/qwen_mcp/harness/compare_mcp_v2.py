"""Gepaarter Vergleich der MCP-Gruppe eines Modells vor und nach einer Server-Änderung (gleiche Aufgabe, Wiederholung, Seed).
Aufruf: python3 harness/compare_mcp_v2.py <alt-tag> <neu-tag>, z. B. pod_coder30b_32k pod_coder30b_32k_v2"""

import collections
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from score import score_session  # noqa: E402  (Pfad oben gesetzt)

T, PR = {}, {}
for f in ("tasks_team.json", "tasks_team_holdout.json"):
    spec = json.loads((ROOT / f).read_text())
    PR.update(spec["projects"])
    T.update({t["id"]: t for t in spec["tasks"]})


def load(path: Path) -> dict:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text().splitlines()[1:]:
        r = json.loads(line)
        if r["arm"] != "mcp":
            continue
        t = T[r["task"]]
        s = score_session(t, PR[t["project"]], r["answer"], 0.5)
        calls = r["tool_calls"]
        out[(r["task"], r["rep"])] = {
            "rub": s["rubric"],
            "use": s["usable"],
            "n": len(calls),
            "ff": bool(r.get("forced_final")),
            "w": r["wall_s"],
            "first": calls[0]["name"] if calls else "-",
            "text_call": not calls and "<function=" in (r["answer"] or ""),
        }
    return out


old_tag, new_tag = sys.argv[1], sys.argv[2]
for part in ("team", "holdout"):
    old = load(ROOT / f"results/raw/ch9n_{old_tag}_{part}.jsonl")
    new = load(ROOT / f"results/raw/ch9n_{new_tag}_{part}.jsonl")
    ks = sorted(k for k in new if k in old)
    if not ks:
        print(f"{part}: noch keine Sitzungen")
        continue
    print(f"{part}: {len(ks)} gepaarte Sitzungen")
    for label, d in (("vorher", old), ("neu", new)):
        m = lambda key: st.mean(d[k][key] for k in ks)  # noqa: E731
        first = collections.Counter(d[k]["first"] for k in ks)
        print(
            f"  {label:7} Rubrik {m('rub'):.3f}  brauchbar {sum(d[k]['use'] for k in ks):>2}/{len(ks)}  "
            f"Werkz. {m('n'):.1f}  Limit {sum(d[k]['ff'] for k in ks):>2}/{len(ks)}  "
            f"zuerst answer_context {first['answer_context']:>2}/{len(ks)}  Text-Aufruf {sum(d[k]['text_call'] for k in ks)}  "
            f"Zeit {m('w'):.0f}s"
        )
    diffs = [new[k]["rub"] - old[k]["rub"] for k in ks]
    print(
        f"  Differenz {st.mean(diffs):+.3f}  besser {sum(x > 0.02 for x in diffs)}, gleich {sum(abs(x) <= 0.02 for x in diffs)}, schlechter {sum(x < -0.02 for x in diffs)}"
    )
