"""SLL scheitert an Subskripten/Referenzmodifikation; die Grammatik-Sicht blendet sie aus.

Ohne diese Normalisierung wiederholt `build_tree()` das ganze Programm in LL(*) (bei einem
4.000-Zeilen-Programm 130 s statt 9 s). Die Tests sichern, dass nur die Grammatik-Sicht
länge- und zeilentreu verändert wird und dass der schnelle Pfad tatsächlich genügt.
"""

from antlr4.atn.PredictionMode import PredictionMode

from cobol import antlr_bridge
from cobol.antlr_bridge import _blank_subscripts
from cobol.parse import parse_program

PROCEDURE = "       PROCEDURE DIVISION.\n"


def _blank(body: str) -> str:
    return _blank_subscripts(PROCEDURE + body)[len(PROCEDURE) :]


def test_reference_modification_and_subscripts_become_plain_names():
    assert _blank("MOVE A(1:5) TO B(I).\n") == "MOVE A" + " " * 5 + " TO B" + " " * 3 + ".\n"
    assert _blank("IF WS-X (I + 1) EQUAL SPACES\n") == "IF WS-X " + " " * 7 + " EQUAL SPACES\n"


def test_layout_is_preserved_for_multiline_groups():
    body = "MOVE DFHCOMMAREA(LENGTH OF X + 1:\n   LENGTH OF Y) TO Z.\n"
    result = _blank(body)

    assert len(result) == len(body)
    assert [i for i, c in enumerate(result) if c == "\n"] == [
        i for i, c in enumerate(body) if c == "\n"
    ]
    assert "(" not in result and ":" not in result


def test_conditions_arithmetic_functions_and_literals_are_left_alone():
    for body in (
        "PERFORM UNTIL (I > 3)\n",
        "COMPUTE A = (B + C) * D.\n",
        "MOVE FUNCTION LENGTH(X) TO N.\n",
        "DISPLAY 'A(1:2)'.\n",
        "IF A AND (B OR C)\n",
    ):
        assert _blank(body) == body


def test_data_division_is_never_touched():
    text = "       WORKING-STORAGE SECTION.\n       01 X PIC X(10).\n" + PROCEDURE + "GOBACK.\n"
    assert _blank_subscripts(text) == text
    assert _blank_subscripts("       01 X PIC X(10).\n") == "       01 X PIC X(10).\n"


def test_subscripted_program_parses_in_sll_without_a_ll_fallback(monkeypatch):
    modes = []
    original = antlr_bridge._parse

    def counting_parse(text, mode):
        modes.append(mode)
        return original(text, mode)

    monkeypatch.setattr(antlr_bridge, "_parse", counting_parse)
    source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. SUBSCR.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 T.\n"
        "          05 E PIC X(5) OCCURS 10.\n"
        "       01 I PIC 9(4).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           IF E(I) EQUAL SPACES\n"
        "              MOVE T(1:LENGTH OF T) TO E(I)\n"
        "           END-IF.\n"
        "           CALL 'NEXTPGM'.\n"
        "           GOBACK.\n"
    )

    result = parse_program(source, "subscr.cbl")

    assert modes == [PredictionMode.SLL]
    assert not [d for d in result.diagnostics if d.code == "COBOL85_PARSER_ERROR"]
    assert any(edge.type == "CALL" and edge.dst_name == "NEXTPGM" for edge in result.edges)


def test_ibm_json_and_xml_statements_do_not_derail_the_grammar():
    source = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. IBMSTMT.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01 WS-A PIC X(20).\n"
        "       01 WS-J.\n"
        "          05 WS-J1 PIC X(5).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           CALL 'BEFORE'.\n"
        "           JSON GENERATE WS-A FROM WS-J\n"
        "               ON EXCEPTION DISPLAY 'ERR'\n"
        "           END-JSON.\n"
        "           XML PARSE WS-A PROCESSING PROCEDURE PARSE-H\n"
        "               ON EXCEPTION DISPLAY 'X'\n"
        "           END-XML.\n"
        "           CALL 'AFTER'.\n"
        "       SECOND-PARA.\n"
        "           GOBACK.\n"
    )

    result = parse_program(source, "ibmstmt.cbl")

    assert not [d for d in result.diagnostics if d.code == "COBOL85_PARSER_ERROR"]
    paragraphs = {entity.name: entity for entity in result.entities if entity.type == "paragraph"}
    assert set(paragraphs) == {"MAIN-PARA", "SECOND-PARA"}
    assert paragraphs["SECOND-PARA"].start_line == 18
    assert {e.dst_name for e in result.edges if e.type == "CALL"} == {"BEFORE", "AFTER"}
