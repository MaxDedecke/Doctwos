from cobol.parse import parse_copybook


def test_copybook_without_division_headers_produces_copybook_and_data_item_entities():
    text = (
        "       01  EMPLOYEE-RECORD.\n"
        "           05  EMP-ID          PIC 9(6).\n"
        "           05  EMP-NAME        PIC X(30).\n"
    )
    result = parse_copybook(text, "/repo/copy/WSFIELDS.cpy")

    assert result.program_name == "WSFIELDS"
    assert not result.errors

    types = [e.type for e in result.entities]
    assert types == ["copybook", "data_item", "data_item", "data_item"]

    root = result.entities[0]
    assert root.name == "WSFIELDS"
    assert root.parent_name is None
    assert root.qualified_name == "WSFIELDS"

    record = next(e for e in result.entities if e.name == "EMPLOYEE-RECORD")
    assert record.parent_name == "WSFIELDS"
    assert record.qualified_name == "WSFIELDS.EMPLOYEE-RECORD"

    field = next(e for e in result.entities if e.name == "EMP-ID")
    assert field.parent_name == "EMPLOYEE-RECORD"
    assert field.qualified_name == "WSFIELDS.EMPLOYEE-RECORD.EMP-ID"
    assert field.meta["picture"] == "9(6)"


def test_copybook_name_derived_from_filename_without_extension():
    result = parse_copybook("01 X PIC 9.\n", "/some/path/order-fields.copy")
    assert result.program_name == "ORDER-FIELDS"


def test_copybook_has_no_edges_and_chunks_whole_file():
    text = "01  A.\n    05  B PIC X.\n" * 5
    result = parse_copybook(text, "x.cpy")

    assert result.edges == []
    assert result.chunks
    assert all(c.meta.get("copybook") == "X" for c in result.chunks)
    # Verkettung der Chunks ergibt exakt den Originaltext zurueck (keine
    # verlorene/duplizierte Zeile) - derselbe Check wie fuer chunking.py.
    reconstructed = "\n".join(c.content for c in result.chunks)
    assert reconstructed.splitlines() == text.splitlines()


def test_copybook_copy_statement_is_retained_as_own_edge():
    result = parse_copybook(
        "01 LOCAL-FIELD PIC X.\nCOPY SHARED.\n",
        "wrapper.cpy",
        copybook_index={"SHARED": ["shared.cpy"]},
    )

    edge = next(edge for edge in result.edges if edge.type == "COPY")
    assert edge.src_name == "WRAPPER"
    assert edge.dst_name == "SHARED"
    assert edge.resolution == "resolved"


def test_empty_copybook_produces_no_entities_and_no_crash():
    result = parse_copybook("", "empty.cpy")
    assert result.entities == []
    assert result.errors


def test_tab_indented_copybook_is_not_cut_in_the_middle_of_a_token():
    """CardDemo CUSTREC.cpy: Tab-Expansion schiebt Code hinter Spalte 72."""
    text = (
        "      *\n"
        "      * Copyright\n"
        "      *\n"
        "\t01  CUSTOMER-RECORD.\n"
        "\t\t     05  CUST-ID                                 PIC 9(09).\n"
        "\t\t     05  CUST-FICO-CREDIT-SCORE                  PIC 9(03).\n"
        "             05  FILLER                                  PIC X(168).      \n"
    )
    result = parse_copybook(text, "/repo/cpy/CUSTREC.cpy")

    assert not result.errors
    assert not [d for d in result.diagnostics if d.severity == "error"]
    fields = {e.name: e.meta.get("picture") for e in result.entities if e.type == "data_item"}
    assert fields["CUST-FICO-CREDIT-SCORE"] == "9(03)"
    assert fields["FILLER"] == "X(168)"


def test_sequence_numbers_after_column_72_are_still_ignored():
    text = (
        "       01  EMPLOYEE-RECORD.                                             00000100\n"
        "           05  EMP-ID          PIC 9(6).                                00000200\n"
    )
    result = parse_copybook(text, "/repo/copy/SEQ.cpy")
    assert not result.errors
    assert any(e.name == "EMP-ID" and e.meta["picture"] == "9(6)" for e in result.entities)


def _error_diagnostics(result):
    return [d for d in result.diagnostics if d.severity == "error"]


def test_comment_mentioning_procedure_division_does_not_hide_the_missing_header():
    """CardDemo CSUTLDPY.cpy: der Kommentar „Procedure Division Copybook“ ist keine Kopfzeile."""
    text = (
        "      *Procedure Division Copybook for DATE related code\n"
        "       EDIT-DATE-CCYYMMDD.\n"
        "           SET WS-EDIT-DATE-IS-INVALID   TO TRUE\n"
        "           .\n"
        "       EDIT-YEAR-CCYY.\n"
        "           MOVE 1 TO WS-X\n"
        "           .\n"
    )
    result = parse_copybook(text, "/repo/cpy/CSUTLDPY.cpy")
    assert not _error_diagnostics(result)
    assert {e.name for e in result.entities if e.type == "paragraph"} == {
        "EDIT-DATE-CCYYMMDD", "EDIT-YEAR-CCYY",
    }


def test_procedure_copybook_with_exec_sql_has_no_data_placeholder_entities():
    """CardDemo CSDB2RPY.cpy: EXEC-Block in einem Procedure-Copybook ohne Kopfzeile."""
    text = (
        "       9998-PRIMING-QUERY.\n"
        "           EXEC SQL\n"
        "                SELECT 1\n"
        "                  INTO :WS-DUMMY-DB2-INT\n"
        "                  FROM SYSIBM.SYSDUMMY1\n"
        "           END-EXEC\n"
        "           MOVE SQLCODE        TO WS-DISP-SQLCODE\n"
        "           .\n"
    )
    result = parse_copybook(text, "/repo/cpy/CSDB2RPY.cpy")
    assert not _error_diagnostics(result)
    names = {e.name for e in result.entities}
    assert "ANTLR-EXEC-PLACEHOLDER" not in names
    assert "9998-PRIMING-QUERY" in names
