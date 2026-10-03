#!/usr/bin/env python3
"""Stellt die Chat-Fragen aus eval_chat_cases.json und prüft Antwort und Quellen gegen die Checkliste (O-354).

    DOCTUS_USER=admin DOCTUS_PASSWORD=... python3 scripts/eval_chat.py --profile 21 [--only Q1,Q3] [--out ergebnis.json]

Das Profil wird nur für diese Anfragen übergeben (`llm_profile_id`); das aktive Profil bleibt unverändert.
Exit-Code 1, wenn ein Prüfpunkt verfehlt wird.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CASES = Path(__file__).resolve().parent.parent / "backend" / "tests" / "fixtures" / "eval_chat_cases.json"


def ask(session, base, project_id, question, profile):
    started = time.monotonic()
    response = session.post(f"{base}/chat", json={"message": question, "mode": "evidence", "project_id": project_id,
                                                  "llm_profile_id": profile, "temperature": 0.2}, stream=True, timeout=900)
    response.raise_for_status()
    answer, sources, tools, completed = "", [], 0, {}
    for raw in response.iter_lines(decode_unicode=True):
        if not raw or not raw.startswith("data:"):
            continue
        event = json.loads(raw[5:])
        kind = event.get("type")
        if kind == "answer":
            answer += event.get("content", "")
        elif kind == "sources":
            sources = event.get("sources", [])
        elif kind == "tool_call":
            tools += 1
        elif kind == "telemetry" and event.get("event") == "completed":
            completed = event.get("metrics", {})
    return {"answer": answer, "sources": sources, "tool_calls": tools, "seconds": round(time.monotonic() - started, 1), "metrics": completed}


def score(case, result):
    checks, answer, items = case["checks"], result["answer"], []
    for pattern in checks.get("answer_all", []):
        items.append((f"Antwort nennt /{pattern}/", re.search(pattern, answer) is not None))
    if checks.get("answer_any"):
        items.append(("Antwort kennzeichnet Unaufgelöstes", any(re.search(p, answer, re.I) for p in checks["answer_any"])))
    if checks.get("no_claim"):
        items.append(("Antwort behauptet nichts Falsches", re.search(checks["no_claim"], answer) is None))
    if checks.get("cites"):
        def cited(want):
            return any(src.get("file") == want["file"] and src.get("lines") and not (src["lines"][1] < want["lines"][0] or src["lines"][0] > want["lines"][1])
                       for src in result["sources"])
        items.append(("Quelle trifft erwartete Zeilen", any(cited(want) for want in checks["cites"])))
    items.append(("Antwort nicht leer, nicht „nicht belastbar belegt“", bool(answer.strip()) and "nicht belastbar belegt" not in answer))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=os.environ.get("DOCTUS_URL", "http://localhost:8000"))
    parser.add_argument("--profile", type=int, required=True)
    parser.add_argument("--only", default="")
    parser.add_argument("--out")
    args = parser.parse_args()
    user, password = os.environ.get("DOCTUS_USER"), os.environ.get("DOCTUS_PASSWORD")
    if not user or not password:
        sys.exit("DOCTUS_USER und DOCTUS_PASSWORD fehlen")
    session = requests.Session()
    session.post(f"{args.url}/auth/login", json={"username": user, "password": password}, timeout=30).raise_for_status()
    projects = {item["name"]: item["id"] for item in session.get(f"{args.url}/projects", timeout=30).json()}
    wanted = {item for item in args.only.split(",") if item}
    report, failed = [], 0
    for case in json.loads(CASES.read_text(encoding="utf-8"))["cases"]:
        if wanted and case["id"] not in wanted:
            continue
        result = ask(session, args.url, projects[case["project"]], case["question"], args.profile)
        items = score(case, result)
        missed = [name for name, ok in items if not ok]
        failed += bool(missed)
        print(f"{'PASS' if not missed else 'FAIL'} {case['id']} {case['label']}: {len(items) - len(missed)}/{len(items)} Prüfpunkte, "
              f"{result['tool_calls']} Tools, {result['seconds']} s" + (f" | verfehlt: {missed}" if missed else ""))
        report.append({"id": case["id"], "items": items, **result})
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
