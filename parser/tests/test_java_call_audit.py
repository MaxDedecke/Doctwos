from __future__ import annotations

import json
from pathlib import Path

from audit_java_calls import audit_java_calls


CORPUS_ROOT = Path(__file__).parent / "java_call_corpus"


def test_java_call_audit_matches_versioned_resolution_report() -> None:
    expected = json.loads((CORPUS_ROOT / "report.json").read_text(encoding="utf-8"))

    assert audit_java_calls(CORPUS_ROOT) == expected
