#!/usr/bin/env python3
"""
scripts/regenerate_cobol_golden.py
=====================================
F-033: regeneriert `parser/tests/cobol_corpus/golden/*.json` aus dem
aktuellen `parser.cobol.parse.parse_program()`. Golden Files werden nie von
Hand editiert - nach jeder absichtlichen Verhaltensänderung im COBOL-Parser
hier neu erzeugen und den Diff im Commit mitprüfen (eine unabsichtliche
Änderung ist genau die Regression, die der CI-Job `parser-golden` fangen
soll).

Usage (vom Repo-Root, mit der parser-venv):
    .venv-parser/bin/python scripts/regenerate_cobol_golden.py
"""

import dataclasses
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "parser"))

from cobol.parse import parse_program  # noqa: E402

FIXTURES = os.path.join(REPO_ROOT, "parser", "tests", "cobol_corpus", "fixtures")
GOLDEN = os.path.join(REPO_ROOT, "parser", "tests", "cobol_corpus", "golden")


def main() -> None:
    os.makedirs(GOLDEN, exist_ok=True)
    for name in sorted(os.listdir(FIXTURES)):
        if not name.endswith(".cbl"):
            continue
        with open(os.path.join(FIXTURES, name)) as f:
            text = f.read()

        logical_path = f"cobol_corpus/fixtures/{name}"
        result = parse_program(text, logical_path)

        golden_name = name.rsplit(".", 1)[0] + ".json"
        with open(os.path.join(GOLDEN, golden_name), "w") as f:
            json.dump(dataclasses.asdict(result), f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"wrote {golden_name}")


if __name__ == "__main__":
    main()
