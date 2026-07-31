"""
F-033: Golden-File-Regressionstest für `parse.parse_program()`.

Vergleicht `ParseResult` für jede Fixture unter `cobol_corpus/fixtures/`
gegen die erwartete Serialisierung unter `cobol_corpus/golden/`. Der
`path`-Parameter ist bewusst repo-relativ konstant (`cobol_corpus/fixtures/
<name>`), unabhängig vom tatsächlichen Aufrufort - sonst wären die Golden
Files nicht portabel zwischen lokalem Lauf und CI (Plan §6.1 Regel 3,
"byte-stabil reproduzierbar").

Golden Files werden über `scripts/regenerate_cobol_golden.py` (Repo-Root)
erzeugt, nie von Hand editiert.
"""

import dataclasses
import json
import os

import pytest

from cobol.parse import parse_program

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")
GOLDEN = os.path.join(os.path.dirname(__file__), "cobol_corpus", "golden")

FIXTURE_NAMES = sorted(f for f in os.listdir(FIXTURES) if f.endswith(".cbl"))


def _parse_result_dict(fixture_name: str) -> dict:
    with open(os.path.join(FIXTURES, fixture_name)) as f:
        text = f.read()
    logical_path = f"cobol_corpus/fixtures/{fixture_name}"
    return dataclasses.asdict(parse_program(text, logical_path))


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_parse_program_matches_golden_file(fixture_name):
    actual = _parse_result_dict(fixture_name)

    golden_name = fixture_name.rsplit(".", 1)[0] + ".json"
    with open(os.path.join(GOLDEN, golden_name)) as f:
        expected = json.load(f)

    assert actual == expected


def test_every_fixture_has_a_golden_file():
    golden_names = {f for f in os.listdir(GOLDEN) if f.endswith(".json")}
    expected_names = {f.rsplit(".", 1)[0] + ".json" for f in FIXTURE_NAMES}
    assert golden_names == expected_names
