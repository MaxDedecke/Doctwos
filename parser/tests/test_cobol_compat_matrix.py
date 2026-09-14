"""
O-118: Kompatibilitätsmatrix je Compilerfamilie/-version und Merkmal.

Zwei Dinge, getrennt von den reinen Byte-Stabilitätstests in
test_cobol_golden.py:

1. Jedes Fixture im Korpus trägt genau einen Matrix-Eintrag
   (cobol_corpus/matrix.py) mit einem Status - das verhindert, dass neue
   Fixtures "unsichtbar" bleiben oder alte Einträge verwaist zurückbleiben.
2. Die beiden aus docs/MAINFRAME_KOMPATIBILITAET.md übernommenen,
   reproduzierten Direktivenfehler (O-123, O-124) bekommen je einen
   xfail(strict=True)-Test, der das KORREKTE Verhalten festhält - nicht das
   aktuell falsche, das schon per Golden File gepinnt ist
   (test_cobol_golden.py::test_parse_program_matches_golden_file). Wird der
   Bug behoben, schlägt der xfail unerwartet erfolgreich fehl ("XPASS") und
   macht CI rot, bis Matrix-Status und Marker aktualisiert sind - so bleibt
   ein Fix nicht unbemerkt halb dokumentiert.
"""

import importlib.util
import os
import sys

from cobol.parse import parse_program

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")

# cobol_corpus/ ist bewusst kein Package (kein __init__.py, wie der Rest von
# parser/tests/) - matrix.py deshalb pfadbasiert laden, analog zu FIXTURES/
# GOLDEN in test_cobol_golden.py statt einen Package-Import zu erzwingen.
_matrix_path = os.path.join(os.path.dirname(__file__), "cobol_corpus", "matrix.py")
_spec = importlib.util.spec_from_file_location("cobol_corpus_matrix", _matrix_path)
_matrix_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _matrix_module  # dataclass() braucht das Modul in sys.modules
_spec.loader.exec_module(_matrix_module)
MATRIX = _matrix_module.MATRIX
MATRIX_BY_FIXTURE = _matrix_module.MATRIX_BY_FIXTURE


def _read_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_every_fixture_has_exactly_one_matrix_entry():
    fixture_names = {f[: -len(".cbl")] for f in os.listdir(FIXTURES) if f.endswith(".cbl")}
    assert {case.fixture for case in MATRIX} == fixture_names
    assert len(MATRIX) == len(MATRIX_BY_FIXTURE), "doppelter Fixture-Name in MATRIX"


def test_known_bugs_carry_a_ticket_reference():
    for case in MATRIX:
        if case.status == "bekannter Fehler":
            assert case.ticket, f"{case.fixture}: 'bekannter Fehler' ohne ticket-Feld"


def test_o123_indented_source_format_free_directive_is_recognized():
    fixture = "16_source_format_free_directive_indented.cbl"
    text = _read_fixture(fixture)
    result = parse_program(text, f"cobol_corpus/fixtures/{fixture}")

    assert result.source_format == "free"
    assert result.program_name == "INDENTDIR"
    # Das Fixture enthält absichtlich keine DATA DIVISION. Entscheidend für
    # O-123 ist, dass die Formatdirektive nicht mehr die Programmstruktur
    # zerstört; die verbliebene fachlich korrekte Diagnose gehört nicht dazu.
    assert result.errors == ["Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht."]


def test_o124_inactive_branch_of_known_true_condition_is_excluded():
    fixture = "17_conditional_compilation_true_branch.cbl"
    text = _read_fixture(fixture)
    result = parse_program(text, f"cobol_corpus/fixtures/{fixture}")

    call_targets = sorted(edge.dst_name for edge in result.edges if edge.type == "CALL")
    assert call_targets == ["ACTIVE"]
    assert result.errors == []


def test_o124_unknown_define_keeps_both_calls_as_conditional_evidence():
    text = "\n".join(
        (
            "identification division.",
            "program-id. CONDITIONAL.",
            "procedure division.",
            "main-para.",
            ">>IF FEATURE",
            '    call "ENABLED".',
            ">>ELSE",
            '    call "DISABLED".',
            ">>END-IF",
        )
    )
    result = parse_program(text, "conditional.cbl")

    assert sorted(edge.dst_name for edge in result.edges if edge.type == "CALL") == [
        "DISABLED",
        "ENABLED",
    ]
    conditions = {
        edge.dst_name: edge.meta["condition"] for edge in result.edges if edge.type == "CALL"
    }
    assert conditions == {"ENABLED": "FEATURE", "DISABLED": "NOT (FEATURE)"}
