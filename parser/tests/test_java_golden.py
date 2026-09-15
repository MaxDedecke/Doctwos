from __future__ import annotations

import json
from pathlib import Path

from java.parse import parse_java_file
from update_java_goldens import GOLDEN_ROOT, FIXTURE_ROOT, snapshot


def test_java_fixture_results_match_goldens() -> None:
    fixtures = sorted(FIXTURE_ROOT.rglob("*.java"))
    assert fixtures, "Java fixture corpus is empty"

    for fixture in fixtures:
        relative = fixture.relative_to(FIXTURE_ROOT)
        result = parse_java_file(fixture.read_text(encoding="utf-8"), relative.as_posix())
        golden_path = GOLDEN_ROOT / relative.with_suffix(".json")

        assert golden_path.exists(), f"Missing golden for {relative}; run tests/update_java_goldens.py"
        expected = json.loads(golden_path.read_text(encoding="utf-8"))
        assert snapshot(result) == expected, f"Java parse output changed for {relative}"
