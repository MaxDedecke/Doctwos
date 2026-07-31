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


def test_empty_copybook_produces_no_entities_and_no_crash():
    result = parse_copybook("", "empty.cpy")
    assert result.entities == []
    assert result.errors
