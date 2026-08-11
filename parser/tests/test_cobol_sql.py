import os

from cobol import data_division, divisions, embedded, sql, source_format

FIXTURES = os.path.join(os.path.dirname(__file__), "cobol_corpus", "fixtures")


def _scan(text: str, fmt: str = "fixed"):
    lines = source_format.split_logical_lines(text, fmt)
    masked, blocks = embedded.mask(lines)
    program, _ = divisions.scan(masked)
    items, _, _ = data_division.parse(program, masked)
    sql_blocks, edges, sql_errors = sql.scan(program, blocks, items)
    return program, sql_blocks, edges, sql_errors


def _scan_from_fixture(name: str, fmt: str = "fixed"):
    with open(os.path.join(FIXTURES, name)) as f:
        text = f.read()
    return _scan(text, fmt)


def test_declare_cursor_captures_name_table_and_host_variable():
    _, blocks, edges, errors = _scan_from_fixture("07_exec_sql.cbl")
    assert errors == []

    declare = blocks[0]
    assert declare.name == "SQL-BLOCK@10"
    assert declare.statement_type == "DECLARE_CURSOR"
    assert declare.cursor_name == "EMP-CURSOR"
    assert declare.tables == ["EMPLOYEE"]
    assert declare.host_variables == ["WS-DEPT-ID"]


def test_open_and_close_are_classified_with_cursor_name_and_no_host_variables():
    _, blocks, _, _ = _scan_from_fixture("07_exec_sql.cbl")

    open_block = blocks[1]
    assert open_block.statement_type == "OPEN"
    assert open_block.cursor_name == "EMP-CURSOR"
    assert open_block.host_variables == []

    close_block = blocks[3]
    assert close_block.statement_type == "CLOSE"
    assert close_block.cursor_name == "EMP-CURSOR"


def test_fetch_extracts_both_host_variables_in_order():
    _, blocks, _, _ = _scan_from_fixture("07_exec_sql.cbl")

    fetch = blocks[2]
    assert fetch.statement_type == "FETCH"
    assert fetch.cursor_name == "EMP-CURSOR"
    assert fetch.host_variables == ["WS-EMP-ID", "WS-EMP-NAME"]
    assert fetch.tables == []


def test_host_variables_resolve_against_unique_matching_data_items():
    _, _, edges, _ = _scan_from_fixture("07_exec_sql.cbl")

    assert len(edges) == 3
    assert all(e.type == "USES" for e in edges)
    assert all(e.resolution == "resolved" for e in edges)
    assert all(e.scope == "EXECSQL" for e in edges)

    declare_edge = edges[0]
    assert declare_edge.src_name == "SQL-BLOCK@10"
    assert declare_edge.dst_name == "WS-DEPT-ID"
    assert declare_edge.src_start_line == 10
    assert declare_edge.src_end_line == 15

    fetch_edges = edges[1:]
    assert [e.dst_name for e in fetch_edges] == ["WS-EMP-ID", "WS-EMP-NAME"]
    assert all(e.src_name == "SQL-BLOCK@19" for e in fetch_edges)


def test_host_variable_without_matching_data_item_is_unresolved():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. NOMATCH.\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC SQL\n"
        "               SELECT EMP-NAME INTO :WS-UNKNOWN FROM EMPLOYEE\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    )
    _, blocks, edges, errors = _scan(text)
    assert errors == []
    assert blocks[0].statement_type == "SELECT"
    assert blocks[0].host_variables == ["WS-UNKNOWN"]
    assert edges[0].resolution == "unresolved"
    assert edges[0].dst_name == "WS-UNKNOWN"


def test_ambiguous_data_item_name_stays_unresolved_no_guessing():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. AMBIGSQL.\n"
        "       DATA DIVISION.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  GROUP-A.\n"
        "           05  WS-CODE     PIC X(2).\n"
        "       01  GROUP-B.\n"
        "           05  WS-CODE     PIC X(4).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC SQL\n"
        "               SELECT DEPT-NAME INTO :WS-CODE FROM DEPARTMENT\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    )
    _, _, edges, errors = _scan(text)
    assert errors == []
    assert edges[0].resolution == "unresolved"
    assert edges[0].dst_name == "WS-CODE"


def test_insert_into_extracts_table_not_host_variable():
    text = (
        "       IDENTIFICATION DIVISION.\n"
        "       PROGRAM-ID. INSERTER.\n"
        "       WORKING-STORAGE SECTION.\n"
        "       01  WS-EMP-ID           PIC 9(6).\n"
        "       01  WS-EMP-NAME         PIC X(30).\n"
        "       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n"
        "           EXEC SQL\n"
        "               INSERT INTO EMPLOYEE (EMP-ID, EMP-NAME)\n"
        "               VALUES (:WS-EMP-ID, :WS-EMP-NAME)\n"
        "           END-EXEC.\n"
        "           STOP RUN.\n"
    )
    _, blocks, _, errors = _scan(text)
    assert errors == []
    assert blocks[0].statement_type == "INSERT"
    assert blocks[0].tables == ["EMPLOYEE"]
    assert blocks[0].host_variables == ["WS-EMP-ID", "WS-EMP-NAME"]


def test_non_sql_dialect_block_is_ignored():
    _, blocks, edges, errors = _scan_from_fixture("08_exec_cics.cbl")
    assert errors == []
    assert blocks == []
    assert edges == []


def test_no_exec_block_produces_no_sql_blocks_without_crashing():
    _, blocks, edges, errors = _scan_from_fixture("01_minimal.cbl")
    assert errors == []
    assert blocks == []
    assert edges == []
