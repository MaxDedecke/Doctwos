import os

from cobol import data_division, divisions, embedded, lexer, source_format
from cobol.model import DataItem, FileDescriptor

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _parse(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, div_errors = divisions.scan(tokens)
    items, fds, dd_errors = data_division.parse(program, tokens)
    return program, items, fds, div_errors + dd_errors


def _parse_fixture(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return _parse(text, fmt)


def test_file_section_fd_becomes_file_descriptor_and_parents_its_record():
    _, items, fds, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    assert fds == [FileDescriptor("EMPLOYEE-FILE", 5, 5)]
    record = next(i for i in items if i.name == "EMPLOYEE-RECORD")
    assert record.level == 1
    assert record.parent == "EMPLOYEE-FILE"


def test_group_hierarchy_via_level_numbers():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    group_a = next(i for i in items if i.name == "GROUP-A")
    assert group_a.parent is None
    codes = [i for i in items if i.name == "WS-CODE"]
    assert len(codes) == 2
    assert {c.parent for c in codes} == {"GROUP-A", "GROUP-B"}


def test_same_field_name_in_two_groups_stays_distinct_items():
    # Genau das, was OF/IN-Qualifizierung in COBOL erst noetig macht: zwei
    # WS-CODE-Items mit eigener PIC-Klausel, nicht verschmolzen.
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    codes = {c.parent: c.picture for c in items if c.name == "WS-CODE"}
    assert codes == {"GROUP-A": "X(2)", "GROUP-B": "X(4)"}


def test_picture_clause_reconstructed_across_paren_tokens():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    emp_id = next(i for i in items if i.name == "EMP-ID")
    assert emp_id.picture == "9(6)"


def test_redefines_clause_captured():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    ws_alt = next(i for i in items if i.name == "WS-ALT")
    assert ws_alt.redefines == "WS-TABLE"
    assert ws_alt.picture == "X(500)"


def test_occurs_depending_on_captured_across_line_break():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    entry = next(i for i in items if i.name == "WS-ENTRY")
    assert entry.occurs == 1
    assert entry.occurs_depending_on == "WS-COUNT"


def test_condition_name_level_88_parents_to_preceding_item():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    flag = next(i for i in items if i.name == "WS-EOF-FLAG")
    condition = next(i for i in items if i.name == "WS-EOF")
    assert condition.level == 88
    assert condition.parent == flag.name
    assert condition.value == "Y"


def test_value_clause_on_elementary_item():
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    flag = next(i for i in items if i.name == "WS-EOF-FLAG")
    assert flag.value == "N"
    assert flag.picture == "X"


def test_pic_clause_does_not_swallow_trailing_period():
    # Regression: "PIC X(30)." darf den Punkt nicht mit in den PIC-String
    # ziehen - sonst verschiebt sich der ganze weitere Scan (gefundener und
    # behobener Bug waehrend der Entwicklung).
    _, items, _, errors = _parse_fixture("06_data_qualified.cbl")
    assert errors == []
    emp_name = next(i for i in items if i.name == "EMP-NAME")
    assert emp_name.picture == "X(30)"
    assert "GROUP-A" in [i.name for i in items]
    assert "WS-COUNT" in [i.name for i in items]


def test_no_data_division_reports_error_without_crashing():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NODATA.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           STOP RUN.\n"
    )
    _, items, fds, errors = _parse(text)
    assert items == []
    assert fds == []
    assert errors != []


def test_dynamic_call_fixture_still_parses_working_storage_field():
    # 09_dynamic_call.cbl existiert schon fuer procedure.py - hier zur
    # Kontrolle, dass data_division.py dieselbe Datei ohne Fehler liest.
    _, items, _, errors = _parse_fixture("09_dynamic_call.cbl")
    assert errors == []
    assert items == [DataItem("WS-PGM", 1, 5, 5, parent=None, picture="X(8)", value="SUBPROG")]
