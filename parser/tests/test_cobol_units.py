"""Übersetzungseinheiten (cobol/units.py): je Programm der obersten Ebene ein eigener Parse-Lauf."""

from cobol.parse import parse_program
from cobol.source_format import split_logical_lines
from cobol.units import containing, split

# Ein COPY in einem noch offenen EVALUATE/PERFORM-Block brachte die Grammatik bisher aus dem Tritt (siehe
# antlr_bridge.mask_for_grammar); danach gingen alle folgenden Programme der Datei verloren.
TWO_PROGRAMS_FIRST_BROKEN = """IDENTIFICATION DIVISION.
PROGRAM-ID. FIRSTPROG.
PROCEDURE DIVISION.
MAIN-PARA.
    PERFORM UNTIL WS-DONE = 1
        EVALUATE WS-KEY
            WHEN "A"
                DISPLAY "A"
            WHEN OTHER
                COPY ASSERT-FAILED REPLACING MSG BY =="unexpected"==.
        END-EVALUATE
        MOVE 1 TO WS-DONE
    END-PERFORM
    GOBACK.
END PROGRAM FIRSTPROG.

IDENTIFICATION DIVISION.
PROGRAM-ID. SECONDPROG.
PROCEDURE DIVISION.
MAIN-PARA.
    PERFORM WORK-PARA
    GOBACK.
WORK-PARA.
    DISPLAY 'WORK'.
END PROGRAM SECONDPROG.
"""

NESTED = """IDENTIFICATION DIVISION.
PROGRAM-ID. OUTER.
PROCEDURE DIVISION.
    GOBACK.
    IDENTIFICATION DIVISION.
    PROGRAM-ID. INNER.
    PROCEDURE DIVISION.
        GOBACK.
    END PROGRAM INNER.
END PROGRAM OUTER.
IDENTIFICATION DIVISION.
PROGRAM-ID. SIBLING.
PROCEDURE DIVISION.
    GOBACK.
END PROGRAM SIBLING.
*> trailing comment
"""


def _lines(text):
    return split_logical_lines(text, "free")


def test_nested_programs_stay_in_the_unit_of_their_outer_program():
    units = split(_lines(NESTED))
    assert [(u[0].phys_start_line, u[-1].phys_end_line) for u in units] == [(1, 10), (11, 16)]
    assert containing(_lines(NESTED), 6)[0].phys_start_line == 1


def test_a_single_program_without_end_program_is_one_unit():
    lines = _lines(
        "IDENTIFICATION DIVISION.\nPROGRAM-ID. ONLY.\nPROCEDURE DIVISION.\n    GOBACK.\n"
    )
    assert split(lines) == [lines]


def test_a_broken_program_does_not_swallow_the_next_program():
    result = parse_program(TWO_PROGRAMS_FIRST_BROKEN, "two.cbl")
    programs = {e.name: (e.start_line, e.end_line) for e in result.entities if e.type == "program"}
    assert set(programs) == {"FIRSTPROG", "SECONDPROG"}
    assert programs["SECONDPROG"][0] == 17
    paragraphs = {e.qualified_name for e in result.entities if e.type == "paragraph"}
    assert {"SECONDPROG.MAIN-PARA", "SECONDPROG.WORK-PARA"} <= paragraphs
    perform = [e for e in result.edges if e.type == "PERFORM" and e.dst_name == "WORK-PARA"]
    assert perform and perform[0].src_start_line == 21
    assert not any(d.severity == "error" and d.line >= 17 for d in result.diagnostics)


def test_copy_inside_an_open_block_does_not_end_the_sentence():
    result = parse_program(TWO_PROGRAMS_FIRST_BROKEN, "two.cbl")
    assert not [d for d in result.diagnostics if d.severity == "error"]
    main = next(e for e in result.entities if e.qualified_name == "FIRSTPROG.MAIN-PARA")
    assert (main.start_line, main.end_line) == (4, 14)
