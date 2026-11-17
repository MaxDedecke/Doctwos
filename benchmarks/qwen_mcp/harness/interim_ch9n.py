"""Zwischenstand Kapitel 9 (neuer Stand): Gruppen je Konfiguration, Team- und Prüfaufgaben getrennt, gleiche Sitzungen vor/nach dem Umbau."""

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
    for t in spec["tasks"]:
        T[t["id"]] = t
    PR.update(spec["projects"])


def load(p):
    p = ROOT / p
    if not p.exists():
        return {}
    out = {}
    for line in p.read_text().splitlines()[1:]:
        r = json.loads(line)
        t = T[r["task"]]
        s = score_session(t, PR[t["project"]], r["answer"], 0.5)
        out[(r["task"], r["arm"], r["rep"])] = dict(
            rubric=s["rubric"],
            tools=[c["name"] for c in r["tool_calls"]],
            empty=sum(c["empty"] for c in r["tool_calls"]),
            wall=r["wall_s"],
            status=r["status"],
        )
    return out


OLD = {
    "local_8b_q4_8k": "results/raw/ch9_qwen8b_plain.jsonl",
    "pod_8b_q4_32k": "results/raw/ch9_pod_qwen3-8b-q4_32k.jsonl",
}


def table(title, new, old):
    print(f"\n{title}: {len(new)} Sitzungen")
    if not new:
        return
    print(
        f"{'Gruppe':<9}{'n':>4}  {'Rubrik':>7}  {'vorher*':>8}  {'brauchbar':>9}  {'Werkz.':>6}  {'leer':>8}  {'Zeit':>5}"
    )
    for arm, n in (("none", "ohne"), ("local", "Dateien"), ("mcp", "MCP")):
        ks = [k for k in new if k[1] == arm]
        if not ks:
            continue
        com = [k for k in ks if k in old]
        calls = sum(len(new[k]["tools"]) for k in ks)
        prev = f"{st.mean(old[k]['rubric'] for k in com):.3f}" if com else "-"
        print(
            f"{n:<9}{len(ks):>4}  {st.mean(new[k]['rubric'] for k in ks):>7.3f}  {prev:>8}  {sum(new[k]['rubric'] >= 0.5 for k in ks):>5}/{len(ks):<3}  {st.mean(len(new[k]['tools']) for k in ks):>6.1f}  {sum(new[k]['empty'] for k in ks):>3}/{calls:<4}  {st.mean(new[k]['wall'] for k in ks):>4.0f}s"
        )
    print(
        "  * vorher = dieselben Sitzungen (Aufgabe, Gruppe, Wiederholung, Seed) vor dem Umbau; nur beim Team-Satz vorhanden"
    )


for tag in sys.argv[1:]:
    team, hold = (
        load(f"results/raw/ch9n_{tag}_team.jsonl"),
        load(f"results/raw/ch9n_{tag}_holdout.jsonl"),
    )
    old = load(OLD[tag]) if tag in OLD else {}
    table(f"=== {tag} · Team-Aufgaben", team, old)
    table(f"=== {tag} · Prüfaufgaben (nie vor dem Umbau gemessen)", hold, {})
    c = collections.Counter(
        x for k, v in {**team, **hold}.items() if k[1] == "mcp" for x in v["tools"]
    )
    print(
        "  MCP-Werkzeuge:",
        dict(c.most_common()),
        "| Status nicht ok:",
        sum(v["status"] != "ok" for v in {**team, **hold}.values()),
    )
