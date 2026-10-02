"""Baut den kombinierten Bericht (Modellvergleich + Kapitel 1 Qwen + Kapitel 2 Luna).

Aufruf: python harness/build_combined.py out.html  (liest results/report_data*.json, narrative*.json, cross.json)
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "results"
out = Path(sys.argv[1])
chapters = []
for tag, chap in (("", {
        "model": "Qwen3-8B", "short": "Qwen3-8B", "eyebrow": "Kapitel 1 · Qwen3-8B lokal in Ollama",
        "title": "Kapitel 1: Qwen3-8B, lokal auf der 8-GB-GPU",
        "armLabel": {"none": "ohne Werkzeuge", "local": "lokale Dateitools", "mcp": "mit MCP"},
        "footer": "Modell qwen3:8b · Ollama · Kontext 8192 · Temperatur 0,3 · eigener Harness"}),
        ("_ch2", {
        "model": "GPT-6-Luna (medium)", "short": "Luna", "eyebrow": "Kapitel 2 · Codex CLI mit gpt-6-luna, Reasoning medium",
        "title": "Kapitel 2: GPT-6-Luna in der Codex CLI",
        "armLabel": {"none": "ohne Werkzeuge", "local": "lokale Shell", "mcp": "mit MCP"},
        "footer": "Modell gpt-6-luna · Reasoning medium · Codex CLI 0.160.0 · Cloud"})):
    chapters.append({"D": json.loads((R / f"report_data{tag}.json").read_text()),
                     "N": json.loads((R / f"narrative{tag}.json").read_text()), "chap": chap})
payload = {"chapters": chapters, "cross": json.loads((R / "cross.json").read_text())}
if (R / "report_data_ch3.json").exists():
    payload["ch3"] = {"D": json.loads((R / "report_data_ch3.json").read_text()), "N": json.loads((R / "narrative_ch3.json").read_text())}
template = sys.argv[2] if len(sys.argv) > 2 else "report_combined_template.html"
tpl = (ROOT / "harness" / template).read_text()
if (R / "narrative_v2.json").exists() and "v2" in template:
    payload["v2"] = json.loads((R / "narrative_v2.json").read_text())
    if (R / "narrative_late.json").exists() and (R / "report_data_late.json").exists():
        late = json.loads((R / "narrative_late.json").read_text())
        v2 = payload["v2"]
        v2["title"], v2["lead"], v2["top"], v2["next"] = late["title"], late["lead"], late["top"], late["next"]
        v2["method"] = v2["method"] + late["method_add"]
        v2["limits"] = v2["limits"] + late["limits_add"]
        v2["late"] = late
        payload["lateData"] = json.loads((R / "report_data_late.json").read_text())
        if (R / "narrative_ch78.json").exists() and (R / "report_data_ch78.json").exists():
            n78 = json.loads((R / "narrative_ch78.json").read_text())
            v2["title"], v2["lead"], v2["top"], v2["next"] = n78["title"], n78["lead"], n78["top"], n78["next"]
            v2["method"] = v2["method"] + n78["method_add"]
            v2["limits"] = v2["limits"] + n78["limits_add"]
            v2["ch78"] = n78
            payload["ch78"] = json.loads((R / "report_data_ch78.json").read_text())
html = tpl.replace("__CHAPTERS__", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
out.write_text(html)
print("->", out, len(html) // 1024, "KB")
