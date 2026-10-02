"""Baut den eigenstaendigen HTML-Bericht aus report_data.json und narrative.json.

Aufruf: python harness/build_report.py results/report_data.json results/narrative.json results/report.html
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data, narrative, out = (Path(a) for a in sys.argv[1:4])
tpl = (ROOT / "harness" / "report_template.html").read_text()
safe = lambda s: s.replace("</", "<\\/")
html = tpl.replace("__DATA__", safe(data.read_text())).replace("__NARRATIVE__", safe(narrative.read_text()))
out.write_text(html)
print("->", out, len(html) // 1024, "KB")
