"""Regenerate the checked-in Java ParseResult snapshots."""

from __future__ import annotations

import json
from pathlib import Path
import sys


PARSER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PARSER_DIR))

from core.model import ParseResult  # noqa: E402
from java.parse import parse_java_file  # noqa: E402


FIXTURE_ROOT = Path(__file__).resolve().parent / "java_corpus" / "fixtures"
GOLDEN_ROOT = Path(__file__).resolve().parent / "java_corpus" / "golden"


def snapshot(result: ParseResult) -> dict:
    return {
        "entities": [
            {
                "type": entity.type,
                "name": entity.name,
                "qualified_name": entity.qualified_name,
                "parent_qualified_name": entity.parent_qualified_name,
                "start_line": entity.start_line,
                "end_line": entity.end_line,
                "meta": entity.meta,
            }
            for entity in result.entities
        ],
        "chunks": [
            {
                "content": chunk.content,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "meta": chunk.meta,
            }
            for chunk in result.chunks
        ],
        "diagnostics": [
            {
                "code": diagnostic.code,
                "severity": diagnostic.severity,
                "phase": diagnostic.phase,
                "message": diagnostic.message,
                "line": diagnostic.line,
                "column": diagnostic.column,
            }
            for diagnostic in result.diagnostics
        ],
    }


def main() -> None:
    fixtures = sorted(FIXTURE_ROOT.rglob("*.java"))
    for fixture in fixtures:
        relative = fixture.relative_to(FIXTURE_ROOT)
        result = parse_java_file(fixture.read_text(encoding="utf-8"), relative.as_posix())
        golden = GOLDEN_ROOT / relative.with_suffix(".json")
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(
            json.dumps(snapshot(result), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"Aktualisiert: {len(fixtures)} Java-Golden-Files in {GOLDEN_ROOT}")


if __name__ == "__main__":
    main()
