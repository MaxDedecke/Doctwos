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

import pytest

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
    fixture_names = {f[:-len(".cbl")] for f in os.listdir(FIXTURES) if f.endswith(".cbl")}
    assert {case.fixture for case in MATRIX} == fixture_names
    assert len(MATRIX) == len(MATRIX_BY_FIXTURE), "doppelter Fixture-Name in MATRIX"


def test_known_bugs_carry_a_ticket_reference():
    for case in MATRIX:
        if case.status == "bekannter Fehler":
            assert case.ticket, f"{case.fixture}: 'bekannter Fehler' ohne ticket-Feld"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "O-123: eingerückte >>SOURCE FORMAT FREE-Direktive wird von "
        "source_format.detect_format() als Fixed erkannt, siehe "
        "docs/MAINFRAME_KOMPATIBILITAET.md. Golden File "
        "16_source_format_free_directive_indented.json pinnt das aktuell "
        "falsche Verhalten. Wird dieser Test grün: Matrix-Status in "
        "cobol_corpus/matrix.py auf 'unterstützt'/'teilweise' setzen, "
        "diesen Marker entfernen, Golden File neu erzeugen."
    ),
)
def test_o123_indented_source_format_free_directive_is_recognized():
    fixture = "16_source_format_free_directive_indented.cbl"
    text = _read_fixture(fixture)
    result = parse_program(text, f"cobol_corpus/fixtures/{fixture}")

    assert result.source_format == "free"
    assert result.program_name == "INDENTDIR"
    assert result.errors == []


@pytest.mark.xfail(
    strict=True,
    reason=(
        "O-124: >>IF 1 = 1 / >>ELSE erzeugt CALLs aus aktivem UND "
        "inaktivem Zweig bei leerer Fehlerliste, siehe "
        "docs/MAINFRAME_KOMPATIBILITAET.md. Golden File "
        "17_conditional_compilation_true_branch.json pinnt das aktuell "
        "falsche Verhalten. Wird dieser Test grün: Matrix-Status in "
        "cobol_corpus/matrix.py auf 'unterstützt'/'teilweise' setzen, "
        "diesen Marker entfernen, Golden File neu erzeugen."
    ),
)
def test_o124_inactive_branch_of_known_true_condition_is_excluded():
    fixture = "17_conditional_compilation_true_branch.cbl"
    text = _read_fixture(fixture)
    result = parse_program(text, f"cobol_corpus/fixtures/{fixture}")

    call_targets = sorted(edge.dst_name for edge in result.edges if edge.type == "CALL")
    assert call_targets == ["ACTIVE"]
    assert result.errors == []
