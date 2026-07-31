import os

from cobol import data_division, divisions, embedded, lexer, source_format, xref

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _edges(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, div_errors = divisions.scan(tokens)
    items, _, dd_errors = data_division.parse(program, tokens)
    edges, xref_errors = xref.scan(program, tokens, items)
    return program, edges, div_errors + dd_errors + xref_errors


def _edges_from_fixture(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return _edges(text, fmt)


def test_qualified_reference_resolves_via_of_to_the_right_group():
    # Drei WS-CODE-Bezuege ueber zwei Statements: "MOVE 'AB' TO WS-CODE OF
    # GROUP-A" (1) und "MOVE WS-CODE OF GROUP-B TO WS-CODE OF GROUP-A" (2) -
    # alle drei ueber OF eindeutig disambiguiert.
    _, edges, errors = _edges_from_fixture("06_data_qualified.cbl")
    assert errors == []
    uses_ws_code = [e for e in edges if e.dst_name == "WS-CODE"]
    assert len(uses_ws_code) == 3
    assert all(e.resolution == "resolved" for e in uses_ws_code)


def test_group_name_itself_is_also_a_uses_edge():
    _, edges, errors = _edges_from_fixture("06_data_qualified.cbl")
    assert errors == []
    group_a_uses = [e for e in edges if e.dst_name == "GROUP-A"]
    assert len(group_a_uses) == 2
    assert all(e.type == "USES" and e.resolution == "resolved" for e in group_a_uses)


def test_condition_name_reference_resolves():
    _, edges, errors = _edges_from_fixture("06_data_qualified.cbl")
    assert errors == []
    condition_use = next(e for e in edges if e.dst_name == "WS-EOF")
    assert condition_use.resolution == "resolved"
    assert condition_use.src_name == "MAIN-PARA"


def test_ambiguous_reference_without_qualifier_stays_unresolved():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AMBIG.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  GROUP-A.\n"
        "           05  WS-CODE     PIC X(2).\n"
        "       01  GROUP-B.\n"
        "           05  WS-CODE     PIC X(4).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           MOVE 'AB' TO WS-CODE.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    ws_code_use = next(e for e in edges if e.dst_name == "WS-CODE")
    assert ws_code_use.resolution == "unresolved"


def test_unambiguous_reference_resolves_without_qualifier():
    # WS-PGM kommt zweimal vor: "MOVE 'SUBPROG' TO WS-PGM." und
    # "CALL WS-PGM." - Letzteres erzeugt zusaetzlich zur CALL-Kante
    # (procedure.py) auch eine USES-Kante, weil WS-PGM als Datenfeld
    # tatsaechlich gelesen wird, um den dynamischen Aufrufziel-Namen zu liefern.
    _, edges, errors = _edges_from_fixture("09_dynamic_call.cbl")
    assert errors == []
    ws_pgm_uses = [e for e in edges if e.dst_name == "WS-PGM" and e.type == "USES"]
    assert len(ws_pgm_uses) == 2
    assert all(e.resolution == "resolved" and e.src_name == "MAIN-PARA" for e in ws_pgm_uses)


def test_paragraph_name_is_never_mistaken_for_a_data_item():
    # PERFORM-Ziele/Section-Namen duerfen nicht als Datenfeld-Nutzung
    # auftauchen, selbst wenn ein Feld zufaellig denselben Namen traegt.
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. COLLIDE.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-FIELD            PIC X(5).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           PERFORM WS-FIELD.\n"
        "           STOP RUN.\n"
        "       WS-FIELD.\n"
        "           DISPLAY 'X'.\n"
    )
    _, edges, errors = _edges(text)
    assert errors == []
    assert all(e.type != "USES" for e in edges)


def test_no_data_items_produces_no_uses_edges_without_crashing():
    # Keine DATA DIVISION: data_division.py meldet das bereits als Fehler,
    # xref.py selbst legt keinen weiteren obendrauf und crasht nicht.
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NODATA.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           DISPLAY 'HELLO'.\n"
        "           STOP RUN.\n"
    )
    _, edges, errors = _edges(text)
    assert edges == []
    assert errors == ["Keine DATA DIVISION gefunden - Datenfelder nicht durchsucht."]


def test_no_procedure_division_reports_error_without_crashing():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NOPROC.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-FIELD PIC X(5).\n"
    )
    lines = source_format.split_logical_lines(text, "fixed")
    masked, _ = embedded.mask(lines)
    tokens = lexer.tokenize(masked)
    program, _ = divisions.scan(tokens)
    items, _, _ = data_division.parse(program, tokens)
    edges, errors = xref.scan(program, tokens, items)

    assert edges == []
    assert errors != []
