"""Auswertung Kapitel 9 (Team-Aufgaben): Gruppen, gepaarte Differenzen mit Bootstrap über Aufgaben, Rohdaten für den Bericht.
Aufruf: python3 harness/analyze_ch9.py results/raw/ch9_qwen8b_plain.jsonl [Ausgabe.json]"""
import collections, json, random, statistics as st, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from score import score_session

def analyze(raw: Path) -> dict:
    spec = json.loads((ROOT / "tasks_team.json").read_text()); T = {t["id"]: t for t in spec["tasks"]}
    lines = [json.loads(l) for l in raw.read_text().splitlines()]; meta, rows = lines[0]["_meta"], lines[1:]
    sess = []
    for r in rows:
        t = T[r["task"]]; s = score_session(t, spec["projects"][t["project"]], r["answer"], 0.5)
        sess.append({"task": r["task"], "arm": r["arm"], "rep": r["rep"], "rubric": s["rubric"], "usable": s["usable"], "items": s["items"],
                     "tools": [c["name"] for c in r["tool_calls"]], "empty_results": sum(c["empty"] for c in r["tool_calls"]),
                     "wall_s": r["wall_s"], "tokens": r["prompt_tokens"] + r["completion_tokens"], "status": r["status"]})
    arms = {}
    for a in ("none", "local", "mcp"):
        x = [s for s in sess if s["arm"] == a]
        arms[a] = {"n": len(x), "rubric": st.mean(s["rubric"] for s in x), "usable": sum(s["usable"] for s in x),
                   "tools": st.mean(len(s["tools"]) for s in x), "with_tool": sum(bool(s["tools"]) for s in x),
                   "wall_s": st.mean(s["wall_s"] for s in x), "tokens": st.mean(s["tokens"] for s in x)}
    per = {t: {a: st.mean(s["rubric"] for s in sess if s["task"] == t and s["arm"] == a) for a in arms} for t in T}
    rng = random.Random(1); diffs = {}
    for a, b in (("mcp", "local"), ("mcp", "none"), ("local", "none")):
        d = [per[t][a] - per[t][b] for t in T]; bs = sorted(st.mean(rng.choices(d, k=len(d))) for _ in range(5000))
        diffs[f"{a}-{b}"] = {"mean": st.mean(d), "lo": bs[125], "hi": bs[4874], "better": sum(x > .02 for x in d), "same": sum(abs(x) <= .02 for x in d), "worse": sum(x < -.02 for x in d)}
    mcp_calls = collections.Counter(n for s in sess if s["arm"] == "mcp" for n in s["tools"])
    return {"meta": {k: meta.get(k) for k in ("model", "options", "run_id")}, "arms": arms, "per_task": per, "diffs": diffs, "sessions": sess,
            "tasks": {t: {"project": T[t]["project"], "category": T[t]["category"]} for t in T},
            "mcp_tools": dict(mcp_calls), "mcp_empty": sum(s["empty_results"] for s in sess if s["arm"] == "mcp"), "mcp_calls": sum(len(s["tools"]) for s in sess if s["arm"] == "mcp")}

if __name__ == "__main__":
    out = analyze(Path(sys.argv[1]))
    if len(sys.argv) > 2: Path(sys.argv[2]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for a, v in out["arms"].items(): print(f'{a:<6} n={v["n"]} Rubrik {v["rubric"]:.3f} brauchbar {v["usable"]}/{v["n"]} Werkzeuge {v["tools"]:.1f} mit {v["with_tool"]} Zeit {v["wall_s"]:.0f}s Tokens {v["tokens"]:.0f}')
    for k, v in out["diffs"].items(): print(f'{k:<11} {v["mean"]:+.3f} [{v["lo"]:+.3f}, {v["hi"]:+.3f}] {v["better"]}/{v["same"]}/{v["worse"]}')
    for t, v in out["per_task"].items(): print(f'{t:<18}', " / ".join(f"{v[a]:.2f}" for a in ("none", "local", "mcp")))
    print("MCP-Werkzeuge:", out["mcp_tools"], "leer:", out["mcp_empty"], "von", out["mcp_calls"], "| Status nicht ok:", sum(s["status"] != "ok" for s in out["sessions"]))
